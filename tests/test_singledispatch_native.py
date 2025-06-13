from collections.abc import Sequence

import pytest
#from functools import singledispatch
from singledispatch_native import singledispatch

from typing import Any

@singledispatch
def some_fun(o: Any) -> str:
    return f"Got {o} {type(o)}"


@some_fun.register(str)
def _some_fun_str(o: str) -> str:
    return "It's a string!"


@some_fun.register(int)
def _some_fun_int(o: int) -> str:
    return "It's an int!"


@some_fun.register(Sequence)
def _some_fun_sequence(l: Sequence) -> str:
    return "Sequence: " + ", ".join(l)


@some_fun.register(tuple)
def _some_fun_tuple(l: tuple) -> str:
    return "tuple: " + ", ".join(l)


@pytest.mark.parametrize(
    "v,ret",
    [
        (None, "Got None <class 'NoneType'>"),
        ("val", "It's a string!"),
        (1, "It's an int!"),
        (True, "It's an int!"),
        ([], "Sequence: "),
        (["1"], "Sequence: 1"),
        (["1", "2", "3"], "Sequence: 1, 2, 3"),
        (("1", "2", "3"), "tuple: 1, 2, 3"),
    ]
)
def test_singledispatch(v, ret):
    assert some_fun(v) == ret
