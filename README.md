# singledispatch-native

Native version of `functools.singledispatch` written in Rust

## Getting Started

`singledispatch-native` can be installed from PyPI using e.g. `pip install singledispatch-native`.

Usage is identical to the builtin [`functools.singledispatch`](https://docs.python.org/3/library/functools.html#functools.singledispatch):

```python
from typing import Any

from singledispatch_native import singledispatch

@singledispatch
def f(o: Any) -> str:
    return "Any"


@f.register(str)
def f(o: str) -> str:
    return o
```

# License

Copyright (c) 2025 Chris Rink

Apache License 2.0