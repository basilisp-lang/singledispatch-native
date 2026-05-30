import sys
import types
from typing import TypeAlias, Any, Callable, overload, Generic, TypeVar

if sys.version_info >= (3, 11):
    _RegType: TypeAlias = type[Any] | types.UnionType
else:
    _RegType: TypeAlias = type[Any]

_T = TypeVar("_T")
class _SingleDispatchCallable(Generic[_T]):
    registry: types.MappingProxyType[Any, Callable[..., _T]]
    def dispatch(self, cls: Any) -> Callable[..., _T]: ...

    # @fun.register(complex)
    # def _(arg, verbose=False): ...
    @overload
    def register(self, cls: _RegType, func: None = None) -> Callable[[Callable[..., _T]], Callable[..., _T]]: ...
    # @fun.register
    # def _(arg: int, verbose=False):
    @overload
    def register(self, cls: Callable[..., _T], func: None = None) -> Callable[..., _T]: ...
    # fun.register(int, lambda x: x)
    @overload
    def register(self, cls: _RegType, func: Callable[..., _T]) -> Callable[..., _T]: ...

    def _clear_cache(self) -> None: ...
    def __call__(self, /, *args: Any, **kwargs: Any) -> _T: ...

def singledispatch(func: Callable[..., _T]) -> _SingleDispatchCallable[_T]: ...

__all__ = ("singledispatch",)