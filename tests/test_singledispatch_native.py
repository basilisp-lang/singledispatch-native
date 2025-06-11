import pytest
from singledispatch_native import singledispatch

from typing import Any

@singledispatch
def some_fun(o: Any) -> str:
    return f"Got {o} {type(o)}"


@some_fun.register(str)
def _some_fun_str(o: str) -> str:
    return "It's a string!"


@some_fun.register(int)
def _some_fun_str(o: int) -> str:
    return "It's an int!"


@pytest.mark.parametrize(
    "v,ret",
    [
        (None, "Got None <class 'NoneType'>"),
        ("val", "It's a string!"),
        (1, "It's an int!"),
        # (True, "It's an int!"),
    ]
)
def test_singledispatch(v, ret):
    assert some_fun(v) == ret
