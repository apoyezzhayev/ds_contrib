# AUTOGENERATED! DO NOT EDIT! File to edit: ../../../nbs/core/05_road_quality.ipynb.

# %% ../../../nbs/core/05_road_quality.ipynb 3
# basic imports
from __future__ import annotations

# sys and paths imports
import json
import logging
import os

# typing imports
from enum import Enum
from pathlib import Path
from typing import Literal

# cv and image imports
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from dotenv import load_dotenv

# widgets imports
from matplotlib.ticker import PercentFormatter
from pyproj import Geod
from scipy.signal import find_peaks

from ...core.files.structure import GSBrowserFileStructure
from ds_contrib.core.paths import (
    Directory,
    PathLike,
    pathify,
)

# visualization imports
from ...core.utils import Iterifiable, exclusive_args, listify
from ...tools.io.gscloud import GSBrowser

# %% auto 0
__all__ = ['logger', 'geod', 'g', 'read_recslam_gps_raw', 'read_recslam_motion_raw', 'read_recslam_timestamps_raw',
           'standardize_recslam_gps_raw', 'standardize_recslam_motion_raw', 'standardize_recslam_timestamps_raw',
           'read_recslam_sensor_data_raw', 'standardize_recslam_sensor_data', 'read_recslam_sensor_data_standard',
           'get_shared_time_index', 'map_df_to_shared_index', 'interpolate_inner', 'get_path_from_gps',
           'get_shared_index_for_sensor_data', 'get_road_qaulity_agg_func', 'change_index', 'RideQuality',
           'get_ride_quality', 'split_imu_on_sections', 'calculate_rms_on_sections', 'calculate_iri', 'find_bumps',
           'calculate_road_quality', 'road_quality_from_sensor_data', 'plot_road_quality_stats',
           'plot_road_quality_on_range']

# %% ../../../nbs/core/05_road_quality.ipynb 4
os.environ["USE_PYGEOS"] = "0"
import geopandas as gpd

# %% ../../../nbs/core/05_road_quality.ipynb 5
logger = logging.getLogger(__name__)

# %% ../../../nbs/core/05_road_quality.ipynb 8
geod = Geod(ellps="WGS84")
g = 9.80665

# %% ../../../nbs/core/05_road_quality.ipynb 10
@exclusive_args(["recslam_file_structure", "path"])
def _get_from_dfs_or_path(
    recslam_file_structure: GSBrowserFileStructure | None = None,
    path: PathLike | None = None,
    dfs_prefix: str | None = None,
) -> Path:
    if recslam_file_structure:
        if dfs_prefix is None:
            raise ValueError(
                "If recslam_file_structure is provided, dfs_prefix must be provided as well."
            )
        recslam_file_structure.get(dfs_prefix)
        path: Path = recslam_file_structure[dfs_prefix].meta["local_path"]
    else:
        path = pathify(path)
    return path


@exclusive_args(["recslam_file_structure", "path"])
def read_recslam_gps_raw(
    recslam_file_structure: GSBrowserFileStructure | None = None,
    path: PathLike | None = None,
) -> pd.DataFrame:
    path = _get_from_dfs_or_path(recslam_file_structure, path, "common/gps")
    gps_df = pd.read_csv(path)
    return gps_df


@exclusive_args(["recslam_file_structure", "path"])
def read_recslam_motion_raw(
    recslam_file_structure: GSBrowserFileStructure | None = None,
    path: PathLike | None = None,
) -> pd.DataFrame:
    path = _get_from_dfs_or_path(recslam_file_structure, path, "common/motion")
    motion_df = pd.read_csv(path)
    return motion_df


@exclusive_args(["recslam_file_structure", "path"])
def read_recslam_timestamps_raw(
    recslam_file_structure: GSBrowserFileStructure | None = None,
    path: PathLike | None = None,
    camera: Literal["wide", "ultrawide"] = "wide",
) -> dict:
    path = _get_from_dfs_or_path(
        recslam_file_structure, path, f"camera_{camera}/timestamps"
    )
    with open(path) as f:
        timestamps_json = json.load(f)
    return timestamps_json


def standardize_recslam_gps_raw(gps_df: pd.DataFrame):
    gps_df["time"] = pd.to_datetime(gps_df["time"], unit="s")
    gps_df.set_index("time", inplace=True)
    return gps_df


def standardize_recslam_motion_raw(motion_df: pd.DataFrame):
    motion_df["time"] = pd.to_datetime(motion_df["time"], unit="s")
    motion_df.set_index("time", inplace=True)
    return motion_df


def standardize_recslam_timestamps_raw(timestamps_json: dict):
    timestamps_df = pd.DataFrame(timestamps_json)
    timestamps_df["frame_number"] = timestamps_df.index
    timestamps_df["time"] = pd.to_datetime(timestamps_df["time"], unit="s")
    timestamps_df.set_index("time", inplace=True)
    return timestamps_df


def read_recslam_sensor_data_raw(
    reclsam_file_structure: GSBrowserFileStructure,
    camera: Literal["wide", "ultrawide"] = "wide",
    sensor_data: Literal["motion", "gps", "timestamps", "all"] = "all",
) -> dict[str, pd.DataFrame | dict]:
    """Reads recslam sensor data from a GSBrowserFileStructure, downloading it if necessary.

    Parameters
    ----------
    reclsam_file_structure : GSBrowserFileStructure
        A GSBrowserFileStructure object containing the recslam data.
    camera : Literal['wide', 'ultrawide'], optional
        The camera to use, by default 'wide'
    sensor_data : Literal['motion', 'gps', 'timestamps', 'all'], optional
        The sensor data to read, by default 'all'

    Returns
    -------
    dict[str, pd.DataFrame|dict]
        A dictionary containing the motion, gps and timestamps dataframes.
    """
    # load data, skip if already loaded
    raw_sensor_data = {}
    if sensor_data == "all" or sensor_data == "gps":
        gps_df = read_recslam_gps_raw(reclsam_file_structure)
        raw_sensor_data["gps_df"] = gps_df
    if sensor_data == "all" or sensor_data == "motion":
        motion_df = read_recslam_motion_raw(reclsam_file_structure)
        raw_sensor_data["motion_df"] = motion_df
    if sensor_data == "all" or sensor_data == "timestamps":
        timestamps_json = read_recslam_timestamps_raw(
            reclsam_file_structure, camera=camera
        )
        raw_sensor_data["timestamps_json"] = timestamps_json
    return raw_sensor_data


def standardize_recslam_sensor_data(
    raw_sensor_data: dict[str, pd.DataFrame | dict]
) -> dict[str, pd.DataFrame]:
    """Makes the raw sensor data consistent with each other.
    Converts all data to dataframes with DateTime index and timestamps to datetime objects.

    Parameters
    ----------
    raw_sensor_data : dict[str, pd.DataFrame|dict]
        A dictionary containing the motion, gps and timestamps dataframes optionally with corresponding names. The dict is expected to contain at least one of the following keys: 'motion_df', 'gps_df', 'timestamps_json'.
        This dict may be built using the `read_raw_recslam_sensor_data` or separately by `read_recslam_...` function.

    Returns
    -------
    dict[str, pd.DataFrame]
        A dictionary containing the motion, gps and timestamps dataframes.
    """
    # prepare raw dataframes
    standardized_data = {}
    if "motion_df" in raw_sensor_data:
        standardized_data["motion"] = standardize_recslam_motion_raw(
            raw_sensor_data["motion_df"]
        )
    if "gps_df" in raw_sensor_data:
        standardized_data["gps"] = standardize_recslam_gps_raw(
            raw_sensor_data["gps_df"]
        )

    if "timestamps_json" in raw_sensor_data:
        standardized_data["timestamps"] = standardize_recslam_timestamps_raw(
            raw_sensor_data["timestamps_json"]
        )

    return standardized_data


@exclusive_args(["dfs", "paths"], may_be_empty=False)
def read_recslam_sensor_data_standard(
    dfs: GSBrowserFileStructure | None = None, paths: dict[str, PathLike] | None = None
):
    if dfs:
        raw_sensor_data = read_recslam_sensor_data_raw(dfs)
    else:
        paths = {k: pathify(v) for k, v in paths.items()}
        raw_sensor_data = {}
        if "motion_path" in paths:
            raw_sensor_data["motion_df"] = read_recslam_motion_raw(
                path=paths["motion_path"]
            )
        if "gps_path" in paths:
            raw_sensor_data["gps_df"] = read_recslam_gps_raw(path=paths["gps_path"])
        if "timestamps_path" in paths:
            raw_sensor_data["timestamps_json"] = read_recslam_timestamps_raw(
                path=paths["timestamps_path"]
            )

    standardized_data = standardize_recslam_sensor_data(raw_sensor_data)
    return standardized_data

# %% ../../../nbs/core/05_road_quality.ipynb 20
def _get_dist(df):
    # Helper function to compute distance between two GPS coordinates
    _, _, dist = geod.inv(df["lon"], df["lat"], df["lon"].shift(), df["lat"].shift())
    return dist

# %% ../../../nbs/core/05_road_quality.ipynb 21
def get_shared_time_index(dataframes: list[pd.DataFrame]):
    """Get shared time index for a list of dataframes

    Dataframes may have different time indexes with different frequencies or may be aperiodic,
    this function returns a shared time index for all dataframes starting from the earliest timestamp
    and ending at the latest timestamp with the minimum frequency of all dataframes.

    Parameters
    ----------
    dataframes : list[pd.DataFrame]
        list of dataframes with DatetimeIndex

    Returns
    -------
    pd.DatetimeIndex
        shared time index for the list of dataframes
    """
    assert all(
        [isinstance(df.index, pd.DatetimeIndex) for df in dataframes]
    ), f"Dataframes must have a DatetimeIndex"
    start_timestamp = min([df.index.min() for df in dataframes])
    end_timestamp = max([df.index.max() for df in dataframes])
    min_delta = min(
        [df.index.to_series().diff().dt.total_seconds().mean() for df in dataframes]
    )
    ms_min_delta: int = round(min_delta * 1000)  # convert to milliseconds
    shared_time_index = pd.date_range(
        start=start_timestamp, end=end_timestamp, freq=f"{ms_min_delta}L"
    )
    return shared_time_index


def map_df_to_shared_index(
    df: pd.Series | pd.DataFrame,
    shared_time_index: pd.DatetimeIndex | pd.DataFrame | pd.Series,
    direction: Literal["nearest", "backward", "forward"] = "nearest",
    column_suffix=None,
):
    """Map a dataframe with DateTime index to a shared time index

    It is possible that the dataframe has a different time index than the shared time index,
    this function maps the dataframe to the shared time index using the specified direction.

    All timestamps in the shared time index will be present in the resulting dataframe,
    and every original point will be mapped to the nearest point in the shared time index.
    For convenience, points from the original dataframe will be marked as "original" in the
    resulting dataframe, and points that were interpolated will be marked as "interpolated"/"extrapolated".

    Parameters
    ----------
    df : pd.Series | pd.DataFrame
        dataframe with DatetimeIndex
    shared_time_index : pd.DatetimeIndex | pd.DataFrame | pd.Series
        shared time index to map the dataframe to
    direction : Literal[&quot;nearest&quot;, &quot;backward&quot;, &quot;forward&quot;], optional
        direction to map the dataframe to the shared time index, by default &quot;nearest&quot;
    column_suffix : _type_, optional
        which suffix to append to `original_time` and `source` columns in the resulting dataframe, by default None

    Returns
    -------
    pd.DataFrame
        dataframe with shared time index and `original_time` and `source` columns

    Raises
    ------
    TypeError
        if `shared_time_index` is not pd.DatetimeIndex, pd.Series or pd.DataFrame
    TypeError
        if `df` is not pd.Series or pd.DataFrame
    """
    if isinstance(shared_time_index, (pd.DatetimeIndex, pd.Series)):
        shared_time_index = pd.DataFrame(index=shared_time_index)
        shared_time_index.index.name = "timestamp"
    else:
        if not isinstance(shared_time_index, pd.DataFrame):
            raise TypeError(
                f"`shared_time_index` should be pd.DatetimeIndex, pd.Series or pd.DataFrame, but got `{type(shared_time_index)}`"
            )
    if isinstance(df, pd.Series):
        df = df.to_frame()
    else:
        if not isinstance(df, pd.DataFrame):
            raise TypeError(
                f"`df` should be pd.Series or pd.DataFrame, but got {type(df)}"
            )
        df = df.copy()
    original_time_str = (
        "original_time" if column_suffix is None else f"original_time_{column_suffix}"
    )
    source_str = "source" if column_suffix is None else f"source_{column_suffix}"
    df[original_time_str] = df.index.to_series()

    result_df = pd.merge_asof(
        shared_time_index,
        right=df,
        left_index=True,
        right_index=True,
        tolerance=pd.Timedelta(shared_time_index.index.freq / 2),
        direction=direction,
    )
    # add interpolation status
    interpolation_slice = slice(
        result_df[original_time_str].min(), result_df[original_time_str].max()
    )
    result_df.loc[interpolation_slice, source_str] = "interpolated"
    result_df.loc[result_df[original_time_str].notna(), source_str] = "original"
    result_df.loc[result_df[source_str].isna(), source_str] = "extrapolated"
    return result_df


def interpolate_inner(
    df: pd.DataFrame, column: str, method: str, limit_direction: str
) -> pd.DataFrame:
    """Interpolate a column in a dataframe inplace, but filling only values between the first and last non-null values

    Parameters
    ----------
    df : pd.DataFrame
        dataframe to interpolate
    column : str
        column to interpolate
    method : str
        interpolation method, see `pandas.DataFrame.interpolate`
    limit_direction : str
        limit direction, see `pandas.DataFrame.interpolate`

    Returns
    -------
    pd.DataFrame
        dataframe with interpolated column
    """
    first_non_null = df[column].first_valid_index()
    last_non_null = df[column].last_valid_index()
    selected_rows = slice(first_non_null, last_non_null)
    df.loc[selected_rows, column] = df.loc[selected_rows, column].interpolate(
        method=method, limit_direction=limit_direction
    )
    return df


def get_path_from_gps(pd_gps: pd.DataFrame, shared_time_index) -> gpd.GeoDataFrame:
    """Convert GPS data to a GeoDataFrame with a shared time index,
    also computes the cumulative distance - `path` for each GPS data point and `path_progress` (from 0 to 1)

    Parameters
    ----------
    pd_gps : pd.DataFrame
        dataframe with GPS data, must have a DatetimeIndex
    shared_time_index : pd.DatetimeIndex
        shared time index to map the dataframe to

    Returns
    -------
    gpd.GeoDataFrame
        GeoDataFrame with shared time index and `path` and `path_progress` columns,
        lon, lat and altitude columns are interpolated to the shared time index and converted to a geometry column
    """
    # Compute distance and cumulative distance for each GPS data point
    pd_gps["dist_delta"] = _get_dist(pd_gps).astype(pd.Float32Dtype)
    pd_gps["dist_delta"].fillna(0, inplace=True)
    pd_gps["path"] = pd_gps["dist_delta"].cumsum()

    # Interpolate the GPS time and total distance data
    mapped_gps = map_df_to_shared_index(
        pd_gps[["path", "lon", "lat", "altitude"]],
        shared_time_index,
        column_suffix="gps",
    )
    interpolate_inner(mapped_gps, "path", "linear", "both")
    interpolate_inner(mapped_gps, "lon", "linear", "both")
    interpolate_inner(mapped_gps, "lat", "linear", "both")
    interpolate_inner(mapped_gps, "altitude", "linear", "both")
    # TODO[High](Buggy): check crs
    mapped_gps["gps"] = gpd.points_from_xy(
        mapped_gps["lon"], mapped_gps["lat"], mapped_gps["altitude"], crs="EPSG:4326"
    )
    mapped_gps.drop(columns=["lon", "lat", "altitude"], inplace=True)
    mapped_gps["path_progress"] = mapped_gps["path"] / mapped_gps["path"].max()
    return gpd.GeoDataFrame(mapped_gps, geometry="gps")

# %% ../../../nbs/core/05_road_quality.ipynb 22
def get_shared_index_for_sensor_data(
    pd_gps: pd.DataFrame, pd_timestamps: pd.DataFrame, pd_motion: pd.DataFrame
) -> pd.DataFrame:
    """Get a shared index for all sensor data, including GPS, timestamps and motion data.
    All the dataframes will be interpolated to the shared index with frequency of the motion data (10ms).
    WARNING: this function generates index, therefore it does not include the whole data from original dataframes,
        only data usefull for indexing, interpolation and slicing

    Additional info attached to all the dataframes:
    - `original_time_{suffix}` - original timestamp from the corresponding dataframe
    - `source_{suffix}` - whether the point was interpolated or extrapolated
    - `path` - cumulative distance from the start of the path
    - `path_progress` - cumulative distance from the start of the path normalized to [0, 1]
    - `frame_number` - frame number from the camera timestamps

    Parameters
    ----------
    pd_gps : pd.DataFrame
        original GPS dataframe
    pd_timestamps : pd.DataFrame
        original timestamps dataframe
    pd_motion : pd.DataFrame
        original motion dataframe

    Returns
    -------
    pd.DataFrame
        shared index dataframe
    """
    # get shared timestamps index, which is the intersection of all timestamps with the smallest delta
    shared_time_index = get_shared_time_index([pd_timestamps, pd_gps, pd_motion])
    # map timestamps to shared index
    shared_index_frames = map_df_to_shared_index(
        pd_timestamps["frame_number"], shared_time_index, column_suffix="frames"
    )
    # map gps to shared index
    shared_index_gps = get_path_from_gps(pd_gps, shared_time_index)
    # compose shared index from frames and gps
    shared_index = shared_index_frames.merge(
        shared_index_gps, left_index=True, right_index=True
    )
    shared_index = interpolate_inner(shared_index, "frame_number", "nearest", "both")
    return gpd.GeoDataFrame(shared_index, geometry="gps")

# %% ../../../nbs/core/05_road_quality.ipynb 33
def get_road_qaulity_agg_func(
    shared_index: pd.DataFrame,
    index: Literal[
        "timestamp", "path_progress", "frame_number", "gps"
    ] = "frame_number",
):
    # Depends: Depends on `road_quality_from_sensor_data` function and columns it creates
    def _get_source_agg_func(names: Iterifiable[str]):
        names: list[str] = listify(names)
        d = {}
        for name in names:
            d[
                f"original_time_{name}"
            ] = lambda x: x.dropna().mean()  # if x.dropna().values.size > 0 else pd.NaT
            d[f"source_{name}"] = (
                lambda x: "original" if "original" in x.values else x.mode().iloc[0]
            )
        return d

    road_quality_agg_func = {
        "frame_number": "median",
        "timestamp": "mean",
        "path": "mean",
        "gps": lambda x: x.unary_union.centroid if x.geometry.unary_union else None,
        "path_progress": "mean",
        "accel_x": lambda x: x.iloc[x.abs().to_numpy().argmax()],
        "section_number": "median",
        "rms": "mean",
        "iri": "mean",
        "rolling_accel_x": "mean",
        "ride_quality": "mean",
        "anomalies": "max",
        "bump": "any",
    }
    road_quality_agg_func.update(_get_source_agg_func(["gps", "frames", "imu"]))
    columns = [shared_index.index.name, *shared_index.columns.to_list()]
    road_quality_agg_func = {
        c: road_quality_agg_func[c] for c in columns if not c == index
    }
    return road_quality_agg_func


def change_index(shared_index_df: pd.DataFrame, new_index: str, agg_func=None):
    """Utility method to change the index of a dataframe inplace
        and create a named column from the old index

    Parameters
    ----------
    shared_index_df : pd.DataFrame
        shared index dataframe
    new_index : str
        new index name from the columns of the dataframe

    Returns
    -------
    pd.DataFrame
        shared index dataframe with new index
    """
    if shared_index_df.index.name == new_index:
        return shared_index_df
    assert new_index in shared_index_df.columns, f"Index {new_index} is not in columns"
    shared_index_df = shared_index_df.reset_index(names=[shared_index_df.index.name])
    shared_index_df.set_index(new_index, inplace=True)
    if agg_func:
        shared_index_df = shared_index_df.groupby(new_index).agg(agg_func)
    return shared_index_df

# %% ../../../nbs/core/05_road_quality.ipynb 37
class RideQuality(Enum):
    POOR = 1
    BAD = 2
    FAIR = 3
    GOOD = 4


def get_ride_quality(iri):
    if iri < 4:
        return RideQuality.GOOD.value
    elif iri >= 4 and iri < 8:
        return RideQuality.FAIR.value
    elif iri >= 8 and iri < 12:
        return RideQuality.BAD.value
    elif iri >= 12:
        return RideQuality.POOR.value


def _split_path_on_sections(path: pd.Series, section_len=100):
    return (path[path < path.max()] // section_len).astype(int)


def split_imu_on_sections(
    pd_motion: pd.DataFrame,
    shared_index: pd.DatetimeIndex,
    section_len: float = 100,
) -> pd.DataFrame:
    pd_motion = map_df_to_shared_index(pd_motion, shared_index, column_suffix="imu")
    pd_motion["section_number"] = _split_path_on_sections(pd_motion["path"])
    return pd_motion


def calculate_rms_on_sections(pd_motion_with_sections: pd.DataFrame):
    return pd_motion_with_sections.groupby("section_number", dropna=True).agg(
        rms=pd.NamedAgg(
            column="accel_x", aggfunc=lambda x: np.sqrt(np.mean(np.square(g * x)))
        )
    )


def calculate_iri(rms: pd.DataFrame):
    iri = 4.19 * rms + 1.73
    return iri


def find_bumps(pd_motion, window_size=45, height=0.8):
    bumps_df: pd.DataFrame = pd_motion.loc[:, "accel_x"].to_frame()
    bumps_df["rolling_accel_x"] = bumps_df["accel_x"].rolling(window=window_size).mean()
    bumps_df["anomalies"] = (bumps_df["rolling_accel_x"] - bumps_df["accel_x"]) ** 2
    bumps_df["bump"] = False
    peak_indices, _ = find_peaks(bumps_df["anomalies"], height=height)
    bumps_df.iloc[peak_indices, -1] = True
    bumps_df.drop(columns=["accel_x"], inplace=True)
    return bumps_df


def calculate_road_quality(shared_index: pd.DataFrame, pd_motion: pd.DataFrame):
    """Calculate road quality from motion data and maps them to shared index

    Parameters
    ----------
    shared_index : pd.DataFrame
        shared index dataframe
    pd_motion : pd.DataFrame
        original motion dataframe

    Returns
    -------
    pd.DataFrame
        shared index dataframe with road quality data
    """
    pd_motion_with_sections = split_imu_on_sections(pd_motion["accel_x"], shared_index)
    rms = calculate_rms_on_sections(pd_motion_with_sections)
    road_quality_data = pd_motion_with_sections.merge(
        rms, left_on="section_number", right_index=True, how="left"
    )
    # add iri
    road_quality_data["iri"] = road_quality_data["rms"].apply(calculate_iri)
    # add ride quality
    road_quality_data["ride_quality"] = road_quality_data["iri"].apply(get_ride_quality)

    # add bumps and anomalies
    bumps_df = find_bumps(pd_motion, height=0.3)

    road_quality_data = road_quality_data.merge(
        bumps_df, left_on="original_time_imu", right_index=True, how="left"
    )
    return road_quality_data


def road_quality_from_sensor_data(
    sensor_data_df_dict: dict[str, pd.DataFrame],
    shared_index: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Calculate road quality from sensor data

    Parameters
    ----------
    sensor_data_df_dict : dict
        dictionary with motion, gps and timestamps dataframes
    shared_index : pd.DataFrame | None, optional
        shared index dataframe if previously calculated, by default None

    Returns
    -------
    pd.DataFrame
        shared index dataframe with road quality data
    """
    # get_shared_index
    if shared_index is None:
        shared_index = get_shared_index_for_sensor_data(
            sensor_data_df_dict["gps"],
            sensor_data_df_dict["timestamps"],
            sensor_data_df_dict["motion"],
        )

    # calculate road_quality
    road_quality_data = calculate_road_quality(
        shared_index, sensor_data_df_dict["motion"]
    )
    return road_quality_data

# %% ../../../nbs/core/05_road_quality.ipynb 39
def plot_road_quality_stats(road_quality_df: pd.DataFrame):
    """Plots the road quality overall stats for the whole dataframe

    Parameters
    ----------
    road_quality_df : pd.DataFrame
        road quality dataframe, calculated with `road_quality_from_sensor_data` function
    """
    fig, axs = plt.subplots(nrows=3, ncols=2, figsize=(20, 7))
    road_quality_df["iri"].plot(ax=axs[0, 0], title="iri[time]")
    change_index(road_quality_df, "path")["iri"].plot(
        ax=axs[0, 1], title="iri[distance]"
    )
    road_quality_by_frame = change_index(road_quality_df, "frame_number")

    road_quality_by_frame["iri"].plot(ax=axs[1, 0], title="iri[frame_number]")
    road_quality_by_frame["ride_quality"].plot(
        ax=axs[1, 1], ylim=(0, 5), title="ride_quality"
    )
    road_quality_by_frame["anomalies"].plot(ax=axs[2, 0], title="anomalies")
    (road_quality_by_frame["bump"] * 1).plot(ax=axs[2, 1], title="bumps")
    plt.tight_layout()
    plt.show()


def _default_plot_setup(ax, range, current_index):
    ax.grid(True)
    ax.set_xlim(range.start, range.stop)
    ax.axvline(x=current_index, color="r", linestyle="--")


def _plot_iri(ax, road_quality, range, current_index, max_val):
    road_quality["iri"].plot(ax=ax, title="iri")
    ax.set_ylim(0, max_val)
    _default_plot_setup(ax, range, current_index)


def _plot_anomalies(ax, road_quality, range, current_index, max_val=None):
    max_val = road_quality["anomalies"].max() if max_val is None else max_val
    road_quality["anomalies"].groupby("frame_number").max().plot(ax=ax)
    (road_quality["bump"] * max_val).plot(ax=ax, title="anomalies")
    ax.legend(["anomalies", "bumps"])
    ax.set_ylim(0, max_val)
    _default_plot_setup(ax, range, current_index)


def _plot_path_progress(ax, road_quality, range, current_index):
    road_quality["path_progress"].plot(title="path_progress", ax=ax)
    _default_plot_setup(ax, range, current_index)
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.axhline(
        y=road_quality.loc[current_index]["path_progress"].mean(),
        color="r",
        linestyle="--",
    )


def plot_road_quality_on_range(
    road_quality_df: pd.DataFrame, range: slice, current_index=0
):
    """Plots the road quality data on a given range with a vertical line at the current index

    Parameters
    ----------
    road_quality_df : pd.DataFrame
        road quality dataframe, calculated with `road_quality_from_sensor_data` function
    range : slice
        range of frames to plot
    current_index : int, optional
        current index, by default 0
    """
    assert range.start <= current_index and (
        range.stop is None or current_index < range.stop
    ), f"Current index {current_index} is not in range {range}"
    if road_quality_df.index.name != "frame_number":
        road_quality_df = change_index(road_quality_df, "frame_number")
    max_val_anomaly = road_quality_df["anomalies"].max()
    max_val_iri = road_quality_df["iri"].max()
    road_quality_df = road_quality_df.loc[
        range.start : (None if range.stop is None else range.stop - 1)
    ]  # -1 because loc operator is inclusive
    fig, axs = plt.subplots(nrows=1, ncols=3, figsize=(20, 3))
    _plot_iri(axs[0], road_quality_df, range, current_index, max_val_iri)
    _plot_anomalies(axs[1], road_quality_df, range, current_index, max_val_anomaly)
    _plot_path_progress(axs[2], road_quality_df, range, current_index)
    plt.tight_layout()
    plt.show()
