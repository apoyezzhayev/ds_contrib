# AUTOGENERATED! DO NOT EDIT! File to edit: ../../../nbs/tools/gscloud_browser.ipynb.

# %% ../../../nbs/tools/gscloud_browser.ipynb 3
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from itertools import repeat
from pathlib import Path
from typing import Iterable, Literal
from urllib.parse import urlparse

from dotenv import load_dotenv
from google import resumable_media
from google.cloud import storage
from google.cloud.storage import Blob
from google.oauth2 import service_account
from nbdev import show_doc
from pydantic import PathNotADirectoryError
from tqdm.auto import tqdm

from ds_contrib.core.paths import (
    Directory,
    PathLike,
    list_paths,
    prepare_paths_for_transfer,
)
from ...core.utils import Iterifiable, listify

# %% auto 0
__all__ = ['logger', 'URL', 'URI', 'GSBrowserContext', 'GSBrowserContextDTO', 'is_uri', 'is_url', 'GSBrowser']

# %% ../../../nbs/tools/gscloud_browser.ipynb 4
logger = logging.getLogger(__name__)

# %% ../../../nbs/tools/gscloud_browser.ipynb 7
URL = str
URI = str


class GSBrowserContextDTO:
    def __init__(
        self,
        path: Path | str,
        prev: GSBrowserContextDTO | None = None,
        is_dir: bool | None = None,
    ):
        self._is_dir = str(path).endswith("/") if is_dir is None else is_dir
        self._path: Path = Path(path)
        self._prev: GSBrowserContextDTO | None = prev

    @property
    def bucket(self) -> str:
        return self._path.parts[0]

    def set_prev(self, prev: GSBrowserContextDTO):
        self._prev = prev

    @property
    def prefix(self) -> str | None:
        if len(self._path.parts) == 1:
            return None
        else:
            return "/".join(self._path.parts[1:]) + ("/" if self._is_dir else "")

    @property
    def path(self) -> str:
        return str(self._path) + ("/" if self._is_dir else "")

    def is_dir(self) -> bool:
        return self._is_dir

    def __repr__(self):
        return (
            f"GSBrowserContext:\n"
            f"\tbucket | {self.bucket}\n"
            f"\tprefix | {self.prefix}\n"
            f"\tis_dir | {self.is_dir()}\n"
            f"\tback | {self._prev.path if self._prev else None}\n"
        )

    @property
    def uri(self) -> URI:
        return f"gs://{self.path}"

    @property
    def url(self) -> URL:
        return f"https://storage.cloud.google.com/{self.path}"

    @property
    def public_url(self) -> URL:
        return f"https://storage.googleapis.com/{self.path}"

    @property
    def parent(self) -> GSBrowserContextDTO | None:
        if len(self._path.parts) == 1:
            return GSBrowserContextDTO(self._path, is_dir=True)
        else:
            return GSBrowserContextDTO(self._path.parent, is_dir=True, prev=self)

    def back(self) -> GSBrowserContextDTO | None:
        return self._prev

    @classmethod
    def from_url(
        cls,
        url: URL,
        is_dir: bool | None = None,
        scheme: str = "https",
        netloc: Iterifiable[str] = None,
    ):
        url_dto = urlparse(url, scheme=scheme)
        if url_dto.scheme != scheme:
            raise ValueError(f"url must be a `{scheme}`, got `{url_dto.scheme}`")
        netloc = (
            listify(netloc)
            if netloc
            else ["storage.googleapis.com", "storage.cloud.google.com"]
        )
        if url_dto.netloc not in netloc:
            raise ValueError(f"url must be a `{netloc}`, got {url_dto.netloc}")
        if len(url_dto.path) < 2:
            raise ValueError(f"url must have a prefix")
        return cls(url_dto.path[1:], is_dir=is_dir)

    @classmethod
    def from_uri(cls, uri: URI, is_dir: bool | None = None, scheme="gs"):
        uri_dto = urlparse(uri, scheme=scheme)
        if uri_dto.scheme != scheme:
            raise ValueError(f"uri must be a `{scheme}`, got `{uri_dto.scheme}`")
        if len(uri_dto.netloc) == 0:
            raise ValueError(f"uri must have at least a bucket")
        return cls("/".join((uri_dto.netloc, uri_dto.path)), is_dir=is_dir)


GSBrowserContext = GSBrowserContextDTO | None | str | Path | URL | URI

# %% ../../../nbs/tools/gscloud_browser.ipynb 14
def is_uri(path: str):
    providers = ("gs://", "s3://")
    return any(path.startswith(provider) for provider in providers)


def is_url(path: str):
    return path.startswith("http://") or path.startswith("https://")

# %% ../../../nbs/tools/gscloud_browser.ipynb 16
from ...core.paths import shared_root


class GSBrowser:
    # TODO(H): add asynchronous and batch network I/O
    def __init__(
        self,
        project: str,
        credentials: PathLike,
        default_context: GSBrowserContext = None,
        downloads_dir: Directory | None = None,
    ):
        """Google Storage Browser

        Object for browsing Google Storage buckets and internal data, downloading/uploading files and folders

        Parameters
        ----------
        project : str
            Google Cloud project name
        credentials : PathLike
            path to service account credentials file in json format
        default_context : GSBrowserContextDTO | None, optional
            starting root path (prefix) in GSBrowser, by default None
        downloads_dir : PathLike, optional
            default directory used for downloads, by default None
            - if None, then temporary directory is created, remove it after usage with `cleanup` method
            - if Path, then persistent directory is created, remove it manually if necessary, if Path does not exist, it will be created
        """
        credentials = service_account.Credentials.from_service_account_file(credentials)
        self.storage_client: storage.Client = storage.Client(
            project=project, credentials=credentials
        )
        # self._context: GSBrowserContext = default(default_context, GSBrowserContext())
        self._context: GSBrowserContextDTO | None = (
            default_context  # TODO: add handling of all types of contexts
        )
        self._buckets = None
        self._downloads_dir = (
            downloads_dir if downloads_dir else Directory(Path.cwd(), temporary=True)
        )

    @property
    def downloads_path(self) -> Path:
        """Lazy init of downloads_dir, if download dir is not specified in init, then temporary directory is created, remove it after usage with `cleanup` method

        Returns
        -------
        Path
            to local downloads directory
        """
        return self._downloads_dir.path

    @property
    def downloads_dir(self) -> Directory:
        return self._downloads_dir

    def is_absolute(self, path: str):
        if path.startswith("/"):
            raise ValueError(f"path must start from bucket not a `/` got `{path}`")
        if self._buckets is None:  # lazy load
            self._buckets = set({b.name for b in self.list_buckets()})
        parts = Path(path).parts
        if len(parts) == 0:
            return False
        else:
            return parts[0] in self._buckets

    def context(self) -> GSBrowserContextDTO | None:
        """Current context (cwd/pwd)

        Returns
        -------
        GSBrowserContextDTO | None
            current context
        """
        return self._context

    def list_buckets(self) -> list[storage.Bucket]:
        """List all buckets in the project

        Returns
        -------
        list[storage.Bucket]
        """
        buckets = list(self.storage_client.list_buckets())
        return buckets

    def cd(self, path: GSBrowserContext, check_existence=True):
        """Change current context to `path`,

        analogous to `cd` in bash

        Parameters
        ----------
        path : GSBrowserContext
            path to change context to
        check_existence : bool, optional
            if True, then check if the prefix exists in Google Storage, otherwise raise FileNotFoundError,
        """
        self._set_context(path, check_existence)

    def back(self):
        """Return to previous context"""
        if self._context is not None:
            self._context = self._context.back()

    @property
    def cwd(self) -> str:
        """Return current context path

        Returns
        -------
        str
        """
        return self._context.path

    def _set_context(
        self,
        context: GSBrowserContext,
        check_existence: bool = False,
        is_dir: bool = True,
    ):
        new_context = self.parse_context(context, is_dir=is_dir)
        if check_existence and not self.is_present(new_context):
            raise FileNotFoundError(f"No such file or directory: {context.path}")
        if self._context:
            new_context.set_prev(self._context)
        self._context = new_context

    def parse_context(
        self, context: GSBrowserContext, is_dir: bool = None
    ) -> GSBrowserContextDTO:
        """Parse context from str, Path, URI, URL, GSBrowserContextDTO or None to GSBrowserContextDTO

        Parameters
        ----------
        context : GSBrowserContext
            context to parse
        is_dir : bool, optional
            if True then consider context as directory, if False then consider context as file,
            if None then infer from the prefix (if it ends with `/`), by default None
            WARNING: if context is Path type, then leading `/` is ignored, so it is impossible to infer if it is a file
                or directory and `is_dir` must be specified

        Returns
        -------
        GSBrowserContextDTO
            parsed context

        Raises
        ------
        ValueError
            if context is not GSBrowserContext, URI, URL or str
        ValueError
            if context is str and is not absolute path starting from bucket or current context is not set
        """
        if context is None:
            return self._context
        if isinstance(context, GSBrowserContextDTO):
            return context
        elif isinstance(context, (str, PathLike)):
            context = str(context)
            is_dir = is_dir if is_dir is not None else context.endswith("/")
            if is_url(context):
                return GSBrowserContextDTO.from_url(context, is_dir=is_dir)
            elif is_uri(context):
                return GSBrowserContextDTO.from_uri(context, is_dir=is_dir)
            else:
                if self.is_absolute(context):
                    return GSBrowserContextDTO(context, is_dir=is_dir)
                else:
                    if self._context is None:
                        raise ValueError(
                            f"Context must be absolute path starting from bucket or current context must be set, "
                            f"got context: `{context}`"
                            f"and current context: {self._context}"
                        )
                    # use resolution in PosixPath format (e.g. emulate `/`)
                    path = (Path("/") / Path(self._context.path) / context).resolve()
                    # Back to URI format
                    path = str(path)[1:]
                    return GSBrowserContextDTO(path, is_dir=is_dir)
        else:
            raise ValueError(
                f"context must be GSBrowserContext, URI, URL or str got {type(context)}"
            )

    def is_present(self, context: GSBrowserContext = None) -> bool:
        """Check if the prefix exists in Google Storage

        Parameters
        ----------
        context : GSBrowserContext, optional
            context to check, if None, then current context is used, by default None

        Returns
        -------
        bool
            True if the prefix exists in Google Storage, otherwise False
        """
        blobs = self.list_blobs(context=context, as_dir=False, max_results=1)
        is_files = next(blobs, None) is not None
        is_subdirs = len(blobs.prefixes) > 0
        return is_files or is_subdirs

    # TODO: add max_results and pagination
    def list_blobs(
        self,
        context: GSBrowserContext = None,
        fields: str = None,
        recursive: bool = False,
        as_dir=None,
        max_results: int = None,
    ) -> Iterable[storage.Blob]:
        """List blobs in prefix directory

        usually used internally or for very specific scenarios, use `list` method instead


        Parameters
        ----------
        context : GSBrowserContext, optional
            prefix directory, root of the hierarchy, if None then current context is used, by default None
        fields : str, optional
            fields to return, see https://googleapis.dev/python/storage/latest/blobs.html#google.cloud.storage.blob.Blob, by default None
        recursive : bool, optional
            if True then list blobs recursively, by default False
        as_dir : _type_, optional
            if True then list blobs as directories, if False then list blobs as files, if None then infer from the prefix (if it ends with `/`), by default None
        max_results : int, optional
            maximum number of results to return, by default None
        """

        # list subdirectories in prefix directory with depth = 1
        context = self.parse_context(context, is_dir=as_dir)

        delimiter = "/" if not recursive else None
        blobs = self.storage_client.list_blobs(
            context.bucket,
            prefix=context.prefix,
            delimiter=delimiter,
            fields=fields,
            max_results=max_results,
        )
        return blobs

    def list(
        self,
        context: GSBrowserContext = None,
        fields: str = None,
        recursive: bool = False,
        as_dir=None,
        max_results: int = None,
    ) -> dict[str, list[GSBrowserContextDTO]]:
        """List blobs as GSBrowserContextDTO files and folders in prefix directory

        analogous to `ls` in bash

        Parameters
        ----------
        context : GSBrowserContext, optional
            prefix directory, root of the hierarchy, if None then current context is used, by default None
        fields : str, optional
            fields to return, see https://googleapis.dev/python/storage/latest/blobs.html#google.cloud.storage.blob.Blob, by default None
        recursive : bool, optional
            if True then list blobs recursively, by default False, Warning: if True, then all blobs are listed and then filtered, may be slow
        as_dir : _type_, optional
            if True then consider prefix as directory, during listing subfolders and files will be returned,
            if False then consider prefix as file, if it is a directory, then return only this directory GSBrowserContextDTO,
            if None then infer from the prefix (if it ends with `/`), by default None
        max_results : int, optional
            maximum number of results to return, if None then all results are returned, by default None

        Returns
        -------
        dict[str, list[GSBrowserContextDTO]]
            dictionary with keys `files` and `folders` with lists of GSBrowserContextDTO files and folders respectively
        """
        context = self.parse_context(context, is_dir=as_dir)

        # if check_existence:
        #     if not self.is_present(context):
        #         raise FileNotFoundError(f'No such file or directory: {context}')

        blobs = self.list_blobs(
            context=context,
            fields=fields,
            recursive=recursive,
            as_dir=as_dir,
            max_results=max_results,
        )

        # Important!: Consume blobs iterator.
        # We assume that there is no direct files inside prefix, only subdirectories
        # Use list to consume iterator
        bucket = Path(blobs.bucket.name)
        files = []
        subdirectories = []

        for blob in blobs:
            if blob.name.endswith("/"):
                subdirectories.append(
                    GSBrowserContextDTO(bucket / blob.name, is_dir=True)
                )
            else:
                files.append(GSBrowserContextDTO(bucket / blob.name, is_dir=False))

        # Prefixes are available then
        subdirectories.extend(
            [
                GSBrowserContextDTO(bucket / sub_prefix, is_dir=True)
                for sub_prefix in blobs.prefixes
            ]
        )
        return {"files": files, "folders": subdirectories}

    def _prepare_path(self, path: PathLike, blob: Blob) -> Path:
        if path is None:
            resolved_path: Path = self.downloads_path / blob.bucket.name / blob.name
        else:
            resolved_path = Path(path)
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        return resolved_path

    def download_blob(
        self,
        blob: Blob,
        destination_file_name: PathLike = None,
        existing_handling: Literal["skip", "overwrite", "raise"] = "skip",
    ):
        """Download blob to local file

        usually for internal usage, use `download_file` or `download_files` instead

        Parameters
        ----------
        blob : Blob
            blob to download
        destination_file_name : PathLike, optional
            local file path to download blob to, if None, then use default path which corresponds to {download_dir}/{prefix}, by default None
        existing_handling : Literal[&quot;skip&quot;, &quot;overwrite&quot;, &quot;raise&quot;], optional
            how to handle existing files:
                - &#39;skip&#39; - skip existing files
                - &#39;overwrite&#39; - overwrite existing files
                - &#39;raise&#39; - raise error if file already exists, by default &#39;skip&#39;

        Raises
        ------
        FileExistsError
            if file already exists and exists_ok is False
        """
        local_path = self._prepare_path(destination_file_name, blob)
        if local_path.exists():
            if existing_handling == "skip":
                logger.warning(f"File {local_path} already exists, skipping")
                return
            elif existing_handling == "overwrite":
                logger.info(f"File {local_path} already exists, overwriting")
            elif existing_handling == "raise":
                raise FileExistsError(f"File {local_path} already exists")
            else:
                raise ValueError(
                    f"Unknown existing_handling strategy: {existing_handling}"
                )

        logger.info(f"Downloading file from URI: `{blob.name}` to path: `{local_path}`")
        try:
            with open(local_path, "wb") as file_obj:
                self.storage_client.download_blob_to_file(blob, file_obj)
        except resumable_media.DataCorruption:
            # Delete the corrupt downloaded file.
            os.remove(local_path)
            raise

    def download_file(
        self,
        context: GSBrowserContext,
        local_path: PathLike = None,
        existing_handling: Literal["skip", "overwrite", "raise"] = "skip",
    ):
        """Download a single file from GCP from context to local file

        Parameters
        ----------
        context : GSBrowserContextDTO | URI | URL | None, optional
            context to download from, if None, then current context is used, by default None
        local_path : PathLike, optional
            local file path to download blob to, if None, then use default path which corresponds to {download_dir}/{prefix}, by default None
        existing_handling : Literal[&quot;skip&quot;, &quot;overwrite&quot;, &quot;raise&quot;], optional
            how to handle existing files:
                - &#39;skip&#39; - skip existing files
                - &#39;overwrite&#39; - overwrite existing files
                - &#39;raise&#39; - raise error if file already exists, by default &#39;skip&#39;
        """
        blobs = self.list_blobs(context=context, recursive=False, as_dir=False)
        for blob in blobs:
            self.download_blob(blob, local_path, existing_handling)

    def get_local_paths_mapping(
        self,
        contexts: Iterifiable[GSBrowserContext],
        local_root: PathLike = None,
        remote_root: PathLike = None,
    ) -> dict[GSBrowserContextDTO, Path]:
        """Maps remote paths (Contexts) to local paths


        Parameters
        ----------
        contexts : Iterifiable[GSBrowserContextDTO]
            remote paths to map
        local_root : PathLike, optional
            local root path, if None, then use default path which corresponds to {download_dir}/{prefix}, by default None
        remote_root : PathLike, optional
            remote root path, if None, then shared root of all remote paths is used, by default None

        Returns
        -------
        list[Path]
            list of local paths
        """
        local_root = (
            Path(local_root).absolute().resolve() if local_root else self.downloads_path
        )
        contexts = [self.parse_context(c) for c in listify(contexts)]
        absolute_remote_paths = list(map(lambda p: Path("/" + p.path), contexts))
        remote_root = (
            remote_root
            if remote_root
            else shared_root(absolute_remote_paths, only_files=True)
        )
        local_paths_mapping = {
            c: local_root / p.relative_to(remote_root)
            for c, p in zip(contexts, absolute_remote_paths)
        }
        return local_paths_mapping

    def download_files(
        self,
        contexts: Iterifiable[GSBrowserContext],
        local_folder_path: PathLike = None,
        remote_root: PathLike = None,
        existing_handling: Literal["skip", "overwrite", "raise"] = "skip",
    ) -> None:
        """Analogue of `download_file` for multiple files use it for convenience

        Parameters
        ----------
        contexts : Iterifiable[GSBrowserContextDTO]
            contexts to download from, may be a single context or a list of contexts
        local_folder_path : PathLike, optional
            local folder path to download blobs to, if None, then use default path which corresponds to {download_dir}/{prefix}, by default None
        remote_root : PathLike, optional
            remote root path, if None, then shared root of all remote paths is used, by default None
        existing_handling : Literal[&quot;skip&quot;, &quot;overwrite&quot;, &quot;raise&quot;], optional
            how to handle existing files:
                - &#39;skip&#39; - skip existing files
                - &#39;overwrite&#39; - overwrite existing files
                - &#39;raise&#39; - raise error if file already exists, by default &#39;skip&#39;
        """
        local_paths_mapping = self.get_local_paths_mapping(
            contexts, local_folder_path, remote_root
        )
        for context, local_path in tqdm(
            local_paths_mapping.items(),
            total=len(local_paths_mapping),
            desc="Downloading files from GCP",
        ):
            self.download_file(context, local_path, existing_handling)

    def upload_file(
        self, local_path: PathLike, context: GSBrowserContext, exists_ok=False
    ):
        """Upload a single file to GCP

        Parameters
        ----------
        local_path : PathLike
            local file path to upload
        context : GSBrowserContext
            context to upload to (google cloud path)
        exists_ok : bool, optional
            if True, then skip uploading if file already exists, if False then raise FileExistsError, by default False

        Raises
        ------
        FileNotFoundError
            If local_path does not exist
        ValueError
            If context is None
        FileExistsError
            If file already exists in google cloud and exists_ok is False
        """
        local_path = Path(local_path)
        if not local_path.exists():
            raise FileNotFoundError(f"No such file or directory: {local_path}")
        if context is None:
            raise ValueError("Context must be specified")
        context = self.parse_context(context, is_dir=False)
        blob = self.storage_client.bucket(context.bucket).blob(context.prefix)
        if blob.exists() and not exists_ok:
            raise FileExistsError(f"File {context} already exists")
        logging.info(f"Uploading file from path: `{local_path}` to URI: `{context}`")
        blob.upload_from_filename(local_path)

    def upload_files(
        self,
        local_paths: Iterifiable[PathLike],
        gcs_destination_root: GSBrowserContext,
        duplicates_handling: Literal["overwrite", "skip", "error"] | None = None,
        recursive: bool = False,
        local_shared_root: PathLike = None,
        test_launch: bool = False,
    ):
        """Upload multiple files to GCP

        Parameters
        ----------
        local_paths : Iterifiable[PathLike]
            local paths to upload to GCP, may be iterable files and directories or a single file or directory
        gcs_destination_root : GSBrowserContext
            root directory context (GSBrowserContext), this directory will be used as a root prefix for all uploaded files
        duplicates_handling : Literal[&quot;overwrite&quot;, &quot;skip&quot;, &quot;error&quot;] | None, optional
            how to handle duplicates:
                - if None, then no checks for file existence are performed,
                - &#39;overwrite&#39; - overwrite existing files
                - &#39;skip&#39; - skip existing files
                - &#39;error&#39; - raise error if file already exists, by default None
        recursive : bool, optional
            if True, then upload folders recursively, otherwise only files of 1st level, by default False
        local_shared_root : _type_, optional
            local paths are treated as relative to this root,
            if None shared root of all files and directories in `local_paths` will be extracted automatically,
            try to avoid this due to unpredictability, by default None
        test_launch : bool, optional
            if True, then do not upload files, only print what will be uploaded, by default False

        Raises
        ------
        FileExistsError
            If file already exists in google cloud and exists_ok is False
        ValueError
            If duplicates_handling is not one of &#39;overwrite&#39;, &#39;skip&#39;, &#39;error&#39;
        """
        gcs_destination_root = self.parse_context(gcs_destination_root, is_dir=True)
        local_paths = list(list_paths(local_paths, recursive=recursive))
        contexts = prepare_paths_for_transfer(
            local_paths,
            recursive=False,
            target_root=gcs_destination_root.path,
            local_shared_root=local_shared_root,
        )
        contexts = [self.parse_context(context, is_dir=False) for context in contexts]
        for local_path, context in tqdm(
            zip(local_paths, contexts),
            total=len(contexts),
            desc="Uploading files to GCP",
            leave=False,
        ):
            if duplicates_handling and self.is_present(context):
                if duplicates_handling == "skip":
                    logging.info(f"File {context} already exists, skipping")
                    continue
                elif duplicates_handling == "error":
                    raise FileExistsError(f"File {context} already exists")
                elif duplicates_handling == "overwrite":
                    logging.info(f"File {context} already exists, overwriting")
                else:
                    raise ValueError(
                        f"Unknown duplicates_handling strategy: {duplicates_handling}"
                    )
            if test_launch:
                print(f"Uploading file from path: `{local_path}` to URI: `{context}`")
            else:
                self.upload_file(
                    local_path, context, exists_ok=(duplicates_handling == "overwrite")
                )

    def __repr__(self):
        return (
            f"GSBrowser(project={self.storage_client.project}, context={self._context})"
        )
