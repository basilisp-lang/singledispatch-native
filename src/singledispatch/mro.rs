use crate::singledispatch::builtins::Builtins;
use crate::singledispatch::typeref::PyTypeReference;
use crate::singledispatch::typing::TypingModule;
use pyo3::prelude::*;
use pyo3::types::PyTuple;
use pyo3::{intern, Bound, PyObject, PyResult, Python};
use std::cmp::Reverse;
use std::collections::hash_map::Keys;
use std::collections::HashSet;

pub(crate) fn get_obj_mro(cls: &Bound<'_, PyAny>) -> PyResult<HashSet<PyTypeReference>> {
    let mro: HashSet<_> = cls
        .getattr(intern!(cls.py(), "__mro__"))?
        .downcast::<PyTuple>()?
        .iter()
        .map(|item| PyTypeReference::new(item.unbind()))
        .collect();
    Ok(mro)
}

fn get_obj_subclasses(cls: &Bound<'_, PyAny>) -> PyResult<HashSet<PyTypeReference>> {
    let subclasses: HashSet<_> = cls
        .call_method0(intern!(cls.py(), "__subclasses__"))?
        .downcast::<PyTuple>()?
        .iter()
        .map(|item| PyTypeReference::new(item.unbind()))
        .collect();
    Ok(subclasses)
}

fn c3_mro(py: Python, cls: Bound<'_, PyAny>, abcs: Vec<PyTypeReference>) -> PyResult<Vec<PyTypeReference>> {
    Ok(abcs)
}

pub(crate) fn compose_mro(
    py: Python,
    cls: Bound<'_, PyAny>,
    types: Keys<PyTypeReference, PyObject>,
) -> PyResult<Vec<PyTypeReference>> {
    let builtins = Builtins::cached(py);
    let typing = TypingModule::cached(py);

    let bases: HashSet<_> = get_obj_mro(&cls)?;
    let registered_types: HashSet<_> = types.collect();
    let eligible_types: HashSet<_> = registered_types
        .iter()
        .filter(|&tref| {
            // Remove entries which are already present in the __mro__ or unrelated.
            let typ = tref.wrapped().bind(py);
            !bases.contains(tref)
                && typ.hasattr(intern!(py, "__mro__")).unwrap()
                && !typ
                    .is_instance(typing.generic_alias_type.wrapped().bind(py))
                    .unwrap()
                && builtins.issubclass(py, &cls, typ).unwrap()
        })
        .filter(|&tref| {
            // Remove entries which are strict bases of other entries (they will end up
            // in the MRO anyway).
            !registered_types.iter().any(|&other| {
                let other_mro = get_obj_mro(other.wrapped().bind(py)).unwrap();
                *tref != other && other_mro.contains(tref)
            })
        })
        .map(|tref| *tref)
        .collect();
    let mut mro: Vec<PyTypeReference> = Vec::new();
    eligible_types.iter().for_each(|&tref| {
        // Subclasses of the ABCs in *types* which are also implemented by
        // *cls* can be used to stabilize ABC ordering.
        let typ = tref.wrapped().bind(py);
        let mut found_subclasses: Vec<_> = get_obj_subclasses(typ)
            .unwrap()
            .iter()
            .filter(|subclass| {
                let typ = subclass.wrapped();
                let tref = PyTypeReference::new(typ.clone_ref(py));
                !bases.contains(&tref)
                    && Builtins::cached(py)
                        .issubclass(py, &cls, &typ.clone_ref(py).into_bound(py))
                        .unwrap()
            })
            .map(|subclass| {
                let obj_mro: Vec<_> = get_obj_mro(subclass.wrapped().bind(py))
                    .unwrap()
                    .into_iter()
                    .filter(|tref| eligible_types.contains(tref))
                    .collect();

                obj_mro
            })
            .collect();

        if found_subclasses.is_empty() {
            mro.push(tref.clone_ref(py));
        } else {
            found_subclasses.sort_by_key(|s| Reverse(s.len()));
            found_subclasses.iter().flatten().for_each(|tref| {
                if !mro.contains(&tref) {
                    mro.push(tref.clone_ref(py));
                }
            });
        }
    });

    c3_mro(py, cls, mro)
}
