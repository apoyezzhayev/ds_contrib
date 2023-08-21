# AUTOGENERATED! DO NOT EDIT! File to edit: ../../nbs/core/00_core.ipynb.

# %% ../../nbs/core/00_core.ipynb 3
from __future__ import annotations
import os
from typing import Any, TypeVar, Iterable, Literal

# %% auto 0
__all__ = ['T', 'PathLike', 'Iterifiable', 'get_class_vars', 'get_class_name', 'get_object_class_name', 'iterify', 'listify',
           'tuplify', 'dictify_with_names']

# %% ../../nbs/core/00_core.ipynb 4
T = TypeVar("T")

PathLike = str | os.PathLike | None
Iterifiable = Iterable[T] | T | None

# %% ../../nbs/core/00_core.ipynb 6
def get_class_vars(cls: type) -> dict[str, Any]:
    """Get all class variables of a class.

    Parameters
    ----------
    cls : type
        Class to get variables from.

    Returns
    -------
    dict[str, Any]
        Dictionary of class variables.
    """
    return {
        k: v
        for k, v in cls.__dict__.items()
        if not k.startswith("__") and not callable(v)
    }

# %% ../../nbs/core/00_core.ipynb 9
def get_class_name(t: type) -> str:
    """Get the full name of a class inlcuding the module name.

    Parameters
    ----------
    t : type
        The type to get the name of.

    Returns
    -------
    str
        The full name of the type.
    """
    if isinstance(t, type):
        return f"{t.__module__}.{t.__name__}"
    else:
        raise TypeError(f"Expected type, got {type(t)}")


def get_object_class_name(o: object) -> str:
    """Returns the full name of the class of an object.

    Parameters
    ----------
    o : object
        object to get the class name of.

    Returns
    -------
    str
        The full name of the class of the object.
    """
    return get_class_name(o.__class__)

# %% ../../nbs/core/00_core.ipynb 11
def iterify(obj: object) -> Iterable:
    """Make an object iterable if it is not already.

    Parameters
    ----------
    obj : object
        Input object to be made iterable if it is not already.

    Returns
    -------
    Iterable
        Iterable version of the input object.
    """ """"""
    if isinstance(obj, Iterable) and not isinstance(obj, str):
        return obj
    else:
        return [obj]

# %% ../../nbs/core/00_core.ipynb 12
from typing import Mapping


def listify(
    obj: object,
    nested_collections: bool = False,
    none_handlings: Literal["none", "empty", "wrap", "default"] = "empty",
    default_value: Any = None,
) -> list | None:
    """Make an object a list if it is not already.

    Parameters
    ----------
    obj : object
        input object to be made a list if it is not already.
    nested_collections : bool, optional
        How to handle the case if input object is already a collection, if True, the input object will be wrapped in a list, if False, the input object will be converted to a list, by default False
    none_handlings : Literal[&#39;none&#39;, &#39;empty&#39;, &#39;wrap&#39;, &#39;default&#39;], optional
        How to handle the case if input object is None, by default &#39;empty&#39;
            - &#39;none&#39;: return None
            - &#39;empty&#39;: return an empty list
            - &#39;wrap&#39;: return a list with None as the only element
            - &#39;default&#39;: return a list with default_value as the only element
    default_value : Any, optional
        Default value to be used if none_handlings is &#39;default&#39;, by default None

    Returns
    -------
    List
        List version of the input object.

    Raises
    ------
    ValueError
        If none_handlings is not one of &#39;none&#39;, &#39;empty&#39;, &#39;wrap&#39;, &#39;default&#39;.
    """
    if isinstance(obj, str):
        return [obj]
    elif isinstance(obj, (set, list, tuple, Mapping)):
        if nested_collections:
            return [obj]
        else:
            return list(obj)
    elif obj is None:
        if none_handlings == "none":
            return None
        elif none_handlings == "empty":
            return []
        elif none_handlings == "wrap":
            return [None]
        elif none_handlings == "default":
            return [default_value]
        else:
            raise ValueError(
                f"Invalid none_handlings: `{none_handlings}`, choose from `none`, `empty`, `wrap`, `default`."
            )
    else:
        return [obj]

# %% ../../nbs/core/00_core.ipynb 18
def tuplify(obj: object, num: int = 2) -> tuple:
    """Convert an object to a tuple with length num, internally calls listify.

    Parameters
    ----------
    obj : object
        Input object to be converted to a tuple.
    num : int, optional
        Length of collection, by default 2

    Returns
    -------
    tuple
        Tuple version of the input object.
    """

    if isinstance(obj, (tuple, list)):
        if len(obj) == num:
            return tuple(obj)
        elif len(obj) < num:
            return tuple([obj[i] if i < len(obj) else obj[0] for i in range(num)])
        else:
            return obj[:num]
    else:
        return tuple([obj] * num)

# %% ../../nbs/core/00_core.ipynb 19
def dictify_with_names(
    data: Any | list | tuple | dict, default_name="image"
) -> dict[str, Any]:
    """Converts the data to a dictionary with names

    Parameters
    ----------
    data : Any | list | tuple | dict
        data to convert, may be a dictionary of {name: data}, a list, a tuple, list/tuple of 2 lists/tuples (names, datas) or a single object
    default_name : str, optional
        default name for the data that will be enumerated if the data is not a dictionary, by default 'image'

    Returns
    -------
    dict[str, Any]
        a dictionary of {name: data}

    Raises
    ------
    ValueError
        data[0] and data[1] must be the same length, but are {len(data[0])} and {len(data[1])} respectively
    """
    if isinstance(data, dict):
        return data
    elif isinstance(data, (tuple, list)):
        if (
            len(data) == 2
            and isinstance(data[0], (list, tuple))
            and isinstance(data[1], (list, tuple))
        ):
            if len(data[0]) == len(data[1]):
                return {data[0][i]: data[1][i] for i in range(len(data[0]))}
            else:
                raise ValueError(
                    f"data[0] and data[1] must be the same length, but are {len(data[0])} and {len(data[1])} respectively"
                )
        else:
            data = listify(data)
            return {f"{default_name}_{i}": d for i, d in enumerate(data)}
    else:
        data = listify(data)
        return {f"{default_name}_{i}": d for i, d in enumerate(data)}