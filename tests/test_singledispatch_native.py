import collections
import decimal
import functools
import sys
import typing
import unittest
import weakref
from annotationlib import Format
from inspect import Signature
from itertools import permutations
from typing import Any
from unittest.mock import patch

import pytest

from singledispatch_native import singledispatch


# Tests below were sourced from the CPython tests for singledispatch:
# https://github.com/python/cpython/blob/main/Lib/test/test_functools.py


def test_simple_overloads():
    @singledispatch
    def g(obj):
        return "base"

    def g_int(i):
        return "integer"

    g.register(int, g_int)
    assert g("str") == "base"
    assert g(1) == "integer"
    assert g([1, 2, 3]) == "base"


def test_mro():
    @singledispatch
    def g(obj):
        return "base"

    class A:
        pass

    class C(A):
        pass

    class B(A):
        pass

    class D(C, B):
        pass

    def g_A(a):
        return "A"

    def g_B(b):
        return "B"

    g.register(A, g_A)
    g.register(B, g_B)

    assert g(A()) == "A"
    assert g(B()) == "B"
    assert g(C()) == "A"
    assert g(D()) == "B"


def test_register_decorator():
    @singledispatch
    def g(obj):
        return "base"

    @g.register(int)
    def g_int(i):
        return "int %s" % (i,)

    assert g("") == "base"
    assert g(12) == "int 12"
    assert g.dispatch(int) is g_int
    assert g.dispatch(object) is g.dispatch(str)
    # Note: in the assert above this is not g.
    # @singledispatch returns the wrapper.


def test_wrapping_attributes():
    @singledispatch
    def g(obj):
        """Simple test"""
        return "Test"

    assert g.__name__ == "g"
    # if sys.flags.optimize < 2:
    #     assert g.__doc__ == "Simple test"


def test_c_classes():
    @singledispatch
    def g(obj):
        return "base"

    @g.register(decimal.DecimalException)
    def _(obj):
        return obj.args

    subn = decimal.Subnormal("Exponent < Emin")
    rnd = decimal.Rounded("Number got rounded")
    assert g(subn) == ("Exponent < Emin",)
    assert g(rnd) == ("Number got rounded",)

    @g.register(decimal.Subnormal)
    def _(obj):
        return "Too small to care."

    assert g(subn) == "Too small to care."
    assert g(rnd) == ("Number got rounded",)


def test_false_meta():
    class MetaA(type):
        def __len__(self):
            return 0

    class A(metaclass=MetaA):
        pass

    class AA(A):
        pass

    @singledispatch
    def fun(a):
        return "base A"

    @fun.register(A)
    def _(a):
        return "fun A"

    aa = AA()
    assert fun(aa) == "fun A"


def test_signatures():
    @singledispatch
    def func(item, arg: int) -> str:
        return str(item)

    @func.register
    def _(item: int, arg: bytes) -> str:
        return str(item)

    assert str(Signature.from_callable(func)) == "(item, arg: int) -> str"


def test_cache_invalidation():
    class TracingDict(collections.UserDict):
        def __init__(self, *args, **kwargs):
            super(TracingDict, self).__init__(*args, **kwargs)
            self.set_ops = []
            self.get_ops = []

        def __getitem__(self, key):
            result = self.data[key]
            self.get_ops.append(key)
            return result

        def __setitem__(self, key, value):
            self.set_ops.append(key)
            self.data[key] = value

        def clear(self):
            self.data.clear()

    td = TracingDict()
    with patch.object(weakref, "WeakKeyDictionary", new=lambda: td):
        c = collections.abc

        @singledispatch
        def g(arg):
            return "base"

        d = {}
        l = []
        assert len(td) == 0
        assert g(d) == "base"
        assert len(td) == 1
        assert td.get_ops == []
        assert td.set_ops == [dict]
        assert td.data[dict] == g.registry[object]
        assert g(l) == "base"
        assert len(td) == 2
        assert td.get_ops == []
        assert td.set_ops == [dict, list]
        assert td.data[dict] == g.registry[object]
        assert td.data[list] == g.registry[object]
        assert td.data[dict] == td.data[list]
        assert g(l) == "base"
        assert g(d) == "base"
        assert td.get_ops == [list, dict]
        assert td.set_ops == [dict, list]
        g.register(list, lambda arg: "list")
        assert td.get_ops == [list, dict]
        assert len(td) == 0
        assert g(d) == "base"
        assert len(td) == 1
        assert td.get_ops == [list, dict]
        assert td.set_ops == [dict, list, dict]
        # assert td.data[dict] == functools._find_impl(dict, g.registry)
        assert g(l) == "list"
        assert len(td) == 2
        assert td.get_ops == [list, dict]
        assert td.set_ops == [dict, list, dict, list]
        # assert td.data[list] == functools._find_impl(list, g.registry)

        class X:
            pass

        c.MutableMapping.register(X)  # Will not invalidate the cache,
        # not using ABCs yet.
        assert g(d) == "base"
        assert g(l) == "list"
        assert td.get_ops == [list, dict, dict, list]
        assert td.set_ops == [dict, list, dict, list]
        g.register(c.Sized, lambda arg: "sized")
        assert len(td) == 0
        assert g(d) == "sized"
        assert len(td) == 1
        assert td.get_ops == [list, dict, dict, list]
        assert td.set_ops == [dict, list, dict, list, dict]
        assert g(l) == "list"
        assert len(td) == 2
        assert td.get_ops == [list, dict, dict, list]
        assert td.set_ops == [dict, list, dict, list, dict, list]
        assert g(l) == "list"
        assert g(d) == "sized"
        assert td.get_ops == [list, dict, dict, list, list, dict]
        assert td.set_ops == [dict, list, dict, list, dict, list]
        g.dispatch(list)
        g.dispatch(dict)
        assert td.get_ops == [list, dict, dict, list, list, dict, list, dict]

        assert td.set_ops == [dict, list, dict, list, dict, list]
        c.MutableSet.register(X)  # Will invalidate the cache.
        assert len(td) == 2  # Stale cache.
        assert g(l) == "list"
        assert len(td) == 1
        g.register(c.MutableMapping, lambda arg: "mutablemapping")
        assert len(td) == 0
        assert g(d) == "mutablemapping"
        assert len(td) == 1
        assert g(l) == "list"
        assert len(td) == 2
        g.register(dict, lambda arg: "dict")
        assert g(d) == "dict"
        assert g(l) == "list"
        g._clear_cache()
        assert len(td) == 0


def test_annotations():
    @singledispatch
    def i(arg):
        return "base"

    @i.register
    def _(arg: collections.abc.Mapping):
        return "mapping"

    @i.register
    def _(arg: "collections.abc.Sequence"):
        return "sequence"

    assert i(None) == "base"
    assert i({"a": 1}) == "mapping"
    assert i([1, 2, 3]) == "sequence"
    assert i((1, 2, 3)) == "sequence"
    assert i("str") == "sequence"

    # Registering classes as callables doesn't work with annotations,
    # you need to pass the type explicitly.
    @i.register(str)
    class _:
        def __init__(self, arg):
            self.arg = arg

        def __eq__(self, other):
            return self.arg == other

    assert i("str") == "str"


def test_invalid_positional_argument():
    @singledispatch
    def f(*args, **kwargs):
        pass

    with pytest.raises(TypeError, match="missing 1 required positional argument:"):
        f()

    with pytest.raises(TypeError, match="missing 1 required positional argument"):
        f(a=1)


def test_positional_only_argument():
    @singledispatch
    def f(arg, /, extra):
        return "base"

    @f.register
    def f_int(arg: int, /, extra: str):
        return "int"

    @f.register
    def f_str(arg: str, /, extra: int):
        return "str"

    print(next(iter(typing.get_type_hints(f_int).items())))

    assert f(None, "extra") == "base"
    assert f(1, "extra") == "int"
    assert f("s", "extra") == "str"


def test_invalid_registrations():
    msg_prefix = "Invalid first argument to `register()`: "
    msg_suffix = (
        ". Use either `@register(some_class)` or plain `@register` on an "
        "annotated function."
    )

    @singledispatch
    def i(arg):
        return "base"

    with pytest.raises(TypeError) as exc:

        @i.register(42)
        def _(arg):
            return "I annotated with a non-type"

    assert str(exc.value).startswith(msg_prefix + "42")
    assert str(exc.value).endswith(msg_suffix)

    with pytest.raises(TypeError) as exc:

        @i.register
        def _(arg):
            return "I forgot to annotate"

    assert str(exc.value).startswith(
        msg_prefix + "<function test_invalid_registrations.<locals>._",
    )
    assert str(exc.value).endswith(msg_suffix)

    with pytest.raises(TypeError) as exc:

        @i.register
        def _(arg: typing.Iterable[str]):
            # At runtime, dispatching on generics is impossible.
            # When registering implementations with singledispatch, avoid
            # types from `typing`. Instead, annotate with regular types
            # or ABCs.
            return "I annotated with a generic collection"

    assert str(exc.value).startswith("Invalid annotation for 'arg'.")
    assert str(exc.value).endswith("typing.Iterable[str] is not a class.")

    with pytest.raises(TypeError) as exc:

        @i.register
        def _(arg: typing.Union[int, typing.Iterable[str]]):
            return "Invalid Union"

    assert str(exc.value).startswith("Invalid annotation for 'arg'.")
    assert str(exc.value).endswith(
        "int | typing.Iterable[str] not all arguments are classes.",
    )


def test_union():
    @singledispatch
    def f(arg):
        return "default"

    @f.register
    def _(arg: typing.Union[str, bytes]):
        return "typing.Union"

    @f.register
    def _(arg: int | float):
        return "types.UnionType"

    assert f([]) == "default"
    assert f("") == "typing.Union"
    assert f(b"") == "typing.Union"
    assert f(1) == "types.UnionType"
    assert f(1.0) == "types.UnionType"


def test_union_conflict():
    @singledispatch
    def f(arg):
        return "default"

    @f.register
    def _(arg: typing.Union[str, bytes]):
        return "typing.Union"

    @f.register
    def _(arg: int | str):
        return "types.UnionType"

    assert f([]) == "default"
    assert f("") == "types.UnionType"  # last one wins
    assert f(b"") == "typing.Union"
    assert f(1) == "types.UnionType"


def test_union_None():
    @singledispatch
    def typing_union(arg):
        return "default"

    @typing_union.register
    def _(arg: typing.Union[str, None]):
        return "typing.Union"

    assert typing_union(1) == "default"
    assert typing_union("") == "typing.Union"
    assert typing_union(None) == "typing.Union"

    @singledispatch
    def types_union(arg):
        return "default"

    @types_union.register
    def _(arg: int | None):
        return "types.UnionType"

    assert types_union("") == "default"
    assert types_union(1) == "types.UnionType"
    assert types_union(None) == "types.UnionType"


def test_register_genericalias():
    @singledispatch
    def f(arg):
        return "default"

    with pytest.raises(TypeError, match="Invalid first argument to "):
        f.register(list[int], lambda arg: "types.GenericAlias")
    with pytest.raises(TypeError, match="Invalid first argument to "):
        f.register(typing.List[int], lambda arg: "typing.GenericAlias")
    with pytest.raises(TypeError, match="Invalid first argument to "):
        f.register(list[int] | str, lambda arg: "types.UnionTypes(types.GenericAlias)")
    with pytest.raises(TypeError, match="Invalid first argument to "):
        f.register(
            typing.List[float] | bytes,
            lambda arg: "typing.Union[typing.GenericAlias]",
        )

    assert f([1]) == "default"
    assert f([1.0]) == "default"
    assert f("") == "default"
    assert f(b"") == "default"


def test_register_genericalias_decorator():
    @singledispatch
    def f(arg):
        return "default"

    with pytest.raises(TypeError, match="Invalid first argument to "):
        f.register(list[int])
    with pytest.raises(TypeError, match="Invalid first argument to "):
        f.register(typing.List[int])
    with pytest.raises(TypeError, match="Invalid first argument to "):
        f.register(list[int] | str)
    with pytest.raises(TypeError, match="Invalid first argument to "):
        f.register(typing.List[int] | str)


def test_register_genericalias_annotation():
    @singledispatch
    def f(arg):
        return "default"

    with pytest.raises(TypeError, match="Invalid annotation for 'arg'"):

        @f.register
        def _(arg: list[int]):
            return "types.GenericAlias"

    with pytest.raises(TypeError, match="Invalid annotation for 'arg'"):

        @f.register
        def _(arg: typing.List[float]):
            return "typing.GenericAlias"

    with pytest.raises(TypeError, match="Invalid annotation for 'arg'"):

        @f.register
        def _(arg: list[int] | str):
            return "types.UnionType(types.GenericAlias)"

    with pytest.raises(TypeError, match="Invalid annotation for 'arg'"):

        @f.register
        def _(arg: typing.List[float] | bytes):
            return "typing.Union[typing.GenericAlias]"

    assert f([1]) == "default"
    assert f([1.0]) == "default"
    assert f("") == "default"
    assert f(b"") == "default"


@pytest.mark.skipif(sys.version_info < (3, 14), reason="Forward references are 3.14+")
def test_forward_reference():
    @singledispatch
    def f(arg, arg2=None):
        return "default"

    @f.register
    def _(arg: str, arg2: Any = None):
        return "forward reference"

    assert f(1) == "default"
    assert f("") == "forward reference"


@pytest.mark.skipif(sys.version_info < (3, 14), reason="Forward references are 3.14+")
def test_unresolved_forward_reference():
    @singledispatch
    def f(arg):
        return "default"

    with pytest.raises(TypeError, match="is an unresolved forward reference"):

        @f.register
        def _(arg: Any):
            return "forward reference"


class TestSingleDispatch(unittest.TestCase):
    def test_compose_mro(self):
        # None of the examples in this test depend on haystack ordering.
        c = collections.abc
        mro = functools._compose_mro
        bases = [c.Sequence, c.MutableMapping, c.Mapping, c.Set]
        for haystack in permutations(bases):
            m = mro(dict, haystack)
            self.assertEqual(
                m,
                [
                    dict,
                    c.MutableMapping,
                    c.Mapping,
                    c.Collection,
                    c.Sized,
                    c.Iterable,
                    c.Container,
                    object,
                ],
            )
        bases = [c.Container, c.Mapping, c.MutableMapping, collections.OrderedDict]
        for haystack in permutations(bases):
            m = mro(collections.ChainMap, haystack)
            self.assertEqual(
                m,
                [
                    collections.ChainMap,
                    c.MutableMapping,
                    c.Mapping,
                    c.Collection,
                    c.Sized,
                    c.Iterable,
                    c.Container,
                    object,
                ],
            )

        # If there's a generic function with implementations registered for
        # both Sized and Container, passing a defaultdict to it results in an
        # ambiguous dispatch which will cause a RuntimeError (see
        # test_mro_conflicts).
        bases = [c.Container, c.Sized, str]
        for haystack in permutations(bases):
            m = mro(collections.defaultdict, [c.Sized, c.Container, str])
            self.assertEqual(
                m, [collections.defaultdict, dict, c.Sized, c.Container, object]
            )

        # MutableSequence below is registered directly on D. In other words, it
        # precedes MutableMapping which means single dispatch will always
        # choose MutableSequence here.
        class D(collections.defaultdict):
            pass

        c.MutableSequence.register(D)
        bases = [c.MutableSequence, c.MutableMapping]
        for haystack in permutations(bases):
            m = mro(D, haystack)
            self.assertEqual(
                m,
                [
                    D,
                    c.MutableSequence,
                    c.Sequence,
                    c.Reversible,
                    collections.defaultdict,
                    dict,
                    c.MutableMapping,
                    c.Mapping,
                    c.Collection,
                    c.Sized,
                    c.Iterable,
                    c.Container,
                    object,
                ],
            )

        # Container and Callable are registered on different base classes and
        # a generic function supporting both should always pick the Callable
        # implementation if a C instance is passed.
        class C(collections.defaultdict):
            def __call__(self):
                pass

        bases = [c.Sized, c.Callable, c.Container, c.Mapping]
        for haystack in permutations(bases):
            m = mro(C, haystack)
            self.assertEqual(
                m,
                [
                    C,
                    c.Callable,
                    collections.defaultdict,
                    dict,
                    c.Mapping,
                    c.Collection,
                    c.Sized,
                    c.Iterable,
                    c.Container,
                    object,
                ],
            )

    def test_register_abc(self):
        c = collections.abc
        d = {"a": "b"}
        l = [1, 2, 3]
        s = {object(), None}
        f = frozenset(s)
        t = (1, 2, 3)

        @singledispatch
        def g(obj):
            return "base"

        self.assertEqual(g(d), "base")
        self.assertEqual(g(l), "base")
        self.assertEqual(g(s), "base")
        self.assertEqual(g(f), "base")
        self.assertEqual(g(t), "base")
        g.register(c.Sized, lambda obj: "sized")
        self.assertEqual(g(d), "sized")
        self.assertEqual(g(l), "sized")
        self.assertEqual(g(s), "sized")
        self.assertEqual(g(f), "sized")
        self.assertEqual(g(t), "sized")
        g.register(c.MutableMapping, lambda obj: "mutablemapping")
        self.assertEqual(g(d), "mutablemapping")
        self.assertEqual(g(l), "sized")
        self.assertEqual(g(s), "sized")
        self.assertEqual(g(f), "sized")
        self.assertEqual(g(t), "sized")
        g.register(collections.ChainMap, lambda obj: "chainmap")
        self.assertEqual(g(d), "mutablemapping")  # irrelevant ABCs registered
        self.assertEqual(g(l), "sized")
        self.assertEqual(g(s), "sized")
        self.assertEqual(g(f), "sized")
        self.assertEqual(g(t), "sized")
        g.register(c.MutableSequence, lambda obj: "mutablesequence")
        self.assertEqual(g(d), "mutablemapping")
        self.assertEqual(g(l), "mutablesequence")
        self.assertEqual(g(s), "sized")
        self.assertEqual(g(f), "sized")
        self.assertEqual(g(t), "sized")
        g.register(c.MutableSet, lambda obj: "mutableset")
        self.assertEqual(g(d), "mutablemapping")
        self.assertEqual(g(l), "mutablesequence")
        self.assertEqual(g(s), "mutableset")
        self.assertEqual(g(f), "sized")
        self.assertEqual(g(t), "sized")
        g.register(c.Mapping, lambda obj: "mapping")
        self.assertEqual(g(d), "mutablemapping")  # not specific enough
        self.assertEqual(g(l), "mutablesequence")
        self.assertEqual(g(s), "mutableset")
        self.assertEqual(g(f), "sized")
        self.assertEqual(g(t), "sized")
        g.register(c.Sequence, lambda obj: "sequence")
        self.assertEqual(g(d), "mutablemapping")
        self.assertEqual(g(l), "mutablesequence")
        self.assertEqual(g(s), "mutableset")
        self.assertEqual(g(f), "sized")
        self.assertEqual(g(t), "sequence")
        g.register(c.Set, lambda obj: "set")
        self.assertEqual(g(d), "mutablemapping")
        self.assertEqual(g(l), "mutablesequence")
        self.assertEqual(g(s), "mutableset")
        self.assertEqual(g(f), "set")
        self.assertEqual(g(t), "sequence")
        g.register(dict, lambda obj: "dict")
        self.assertEqual(g(d), "dict")
        self.assertEqual(g(l), "mutablesequence")
        self.assertEqual(g(s), "mutableset")
        self.assertEqual(g(f), "set")
        self.assertEqual(g(t), "sequence")
        g.register(list, lambda obj: "list")
        self.assertEqual(g(d), "dict")
        self.assertEqual(g(l), "list")
        self.assertEqual(g(s), "mutableset")
        self.assertEqual(g(f), "set")
        self.assertEqual(g(t), "sequence")
        g.register(set, lambda obj: "concrete-set")
        self.assertEqual(g(d), "dict")
        self.assertEqual(g(l), "list")
        self.assertEqual(g(s), "concrete-set")
        self.assertEqual(g(f), "set")
        self.assertEqual(g(t), "sequence")
        g.register(frozenset, lambda obj: "frozen-set")
        self.assertEqual(g(d), "dict")
        self.assertEqual(g(l), "list")
        self.assertEqual(g(s), "concrete-set")
        self.assertEqual(g(f), "frozen-set")
        self.assertEqual(g(t), "sequence")
        g.register(tuple, lambda obj: "tuple")
        self.assertEqual(g(d), "dict")
        self.assertEqual(g(l), "list")
        self.assertEqual(g(s), "concrete-set")
        self.assertEqual(g(f), "frozen-set")
        self.assertEqual(g(t), "tuple")

    def test_c3_abc(self):
        c = collections.abc
        mro = functools._c3_mro

        class A(object):
            pass

        class B(A):
            def __len__(self):
                return 0  # implies Sized

        @c.Container.register
        class C(object):
            pass

        class D(object):
            pass  # unrelated

        class X(D, C, B):
            def __call__(self):
                pass  # implies Callable

        expected = [X, c.Callable, D, C, c.Container, B, c.Sized, A, object]
        for abcs in permutations([c.Sized, c.Callable, c.Container]):
            self.assertEqual(mro(X, abcs=abcs), expected)
        # unrelated ABCs don't appear in the resulting MRO
        many_abcs = [c.Mapping, c.Sized, c.Callable, c.Container, c.Iterable]
        self.assertEqual(mro(X, abcs=many_abcs), expected)

    def test_mro_conflicts(self):
        c = collections.abc

        @singledispatch
        def g(arg):
            return "base"

        class O(c.Sized):
            def __len__(self):
                return 0

        o = O()
        self.assertEqual(g(o), "base")
        g.register(c.Iterable, lambda arg: "iterable")
        g.register(c.Container, lambda arg: "container")
        g.register(c.Sized, lambda arg: "sized")
        g.register(c.Set, lambda arg: "set")
        self.assertEqual(g(o), "sized")
        c.Iterable.register(O)
        self.assertEqual(g(o), "sized")  # because it's explicitly in __mro__
        c.Container.register(O)
        self.assertEqual(g(o), "sized")  # see above: Sized is in __mro__
        c.Set.register(O)
        self.assertEqual(g(o), "set")  # because c.Set is a subclass of

        # c.Sized and c.Container
        class P:
            pass

        p = P()
        self.assertEqual(g(p), "base")
        c.Iterable.register(P)
        self.assertEqual(g(p), "iterable")
        c.Container.register(P)
        with self.assertRaises(RuntimeError) as re_one:
            g(p)
        self.assertIn(
            str(re_one.exception),
            (
                (
                    "Ambiguous dispatch: <class 'collections.abc.Container'> "
                    "or <class 'collections.abc.Iterable'>"
                ),
                (
                    "Ambiguous dispatch: <class 'collections.abc.Iterable'> "
                    "or <class 'collections.abc.Container'>"
                ),
            ),
        )

        class Q(c.Sized):
            def __len__(self):
                return 0

        q = Q()
        self.assertEqual(g(q), "sized")
        c.Iterable.register(Q)
        self.assertEqual(g(q), "sized")  # because it's explicitly in __mro__
        c.Set.register(Q)
        self.assertEqual(g(q), "set")  # because c.Set is a subclass of

        # c.Sized and c.Iterable
        @singledispatch
        def h(arg):
            return "base"

        @h.register(c.Sized)
        def _(arg):
            return "sized"

        @h.register(c.Container)
        def _(arg):
            return "container"

        # Even though Sized and Container are explicit bases of MutableMapping,
        # this ABC is implicitly registered on defaultdict which makes all of
        # MutableMapping's bases implicit as well from defaultdict's
        # perspective.
        with self.assertRaises(RuntimeError) as re_two:
            h(collections.defaultdict(lambda: 0))
        self.assertIn(
            str(re_two.exception),
            (
                (
                    "Ambiguous dispatch: <class 'collections.abc.Container'> "
                    "or <class 'collections.abc.Sized'>"
                ),
                (
                    "Ambiguous dispatch: <class 'collections.abc.Sized'> "
                    "or <class 'collections.abc.Container'>"
                ),
            ),
        )

        class R(collections.defaultdict):
            pass

        c.MutableSequence.register(R)

        @singledispatch
        def i(arg):
            return "base"

        @i.register(c.MutableMapping)
        def _(arg):
            return "mapping"

        @i.register(c.MutableSequence)
        def _(arg):
            return "sequence"

        r = R()
        self.assertEqual(i(r), "sequence")

        class S:
            pass

        class T(S, c.Sized):
            def __len__(self):
                return 0

        t = T()
        self.assertEqual(h(t), "sized")
        c.Container.register(T)
        self.assertEqual(h(t), "sized")  # because it's explicitly in the MRO

        class U:
            def __len__(self):
                return 0

        u = U()
        self.assertEqual(h(u), "sized")  # implicit Sized subclass inferred
        # from the existence of __len__()
        c.Container.register(U)
        # There is no preference for registered versus inferred ABCs.
        with self.assertRaises(RuntimeError) as re_three:
            h(u)
        self.assertIn(
            str(re_three.exception),
            (
                (
                    "Ambiguous dispatch: <class 'collections.abc.Container'> "
                    "or <class 'collections.abc.Sized'>"
                ),
                (
                    "Ambiguous dispatch: <class 'collections.abc.Sized'> "
                    "or <class 'collections.abc.Container'>"
                ),
            ),
        )

        class V(c.Sized, S):
            def __len__(self):
                return 0

        @singledispatch
        def j(arg):
            return "base"

        @j.register(S)
        def _(arg):
            return "s"

        @j.register(c.Container)
        def _(arg):
            return "container"

        v = V()
        self.assertEqual(j(v), "s")
        c.Container.register(V)
        self.assertEqual(j(v), "container")  # because it ends up right after
        # Sized in the MRO
