use crate::singledispatch::builtins::Builtins;
use crate::singledispatch::typeref::PyTypeReference;
use crate::singledispatch::typing::TypingModule;
use pyo3::exceptions::PyRuntimeError;
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

fn get_obj_bases(cls: &Bound<'_, PyAny>) -> PyResult<Vec<PyTypeReference>> {
    match cls.getattr_opt(intern!(cls.py(), "__bases__")) {
        Ok(opt) => match opt {
            Some(b) => Ok(b
                .downcast::<PyTuple>()?
                .iter()
                .map(|item| PyTypeReference::new(item.unbind()))
                .collect()),
            None => Ok(Vec::new()),
        },
        Err(e) => Err(e),
    }
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

fn find_merge_candidate(py: Python, seqs: &[&mut Vec<PyTypeReference>]) -> Option<PyTypeReference> {
    let mut candidate: Option<&PyTypeReference> = None;
    for i1 in 0..seqs.len() {
        let s1 = &seqs[i1];
        candidate = Some(&s1[0]);
        for i2 in 0..seqs.len() {
            let s2 = &seqs[i2];
            if s2[1..].contains(candidate.unwrap()) {
                candidate = None;
                break;
            }
        }
        if candidate.is_some() {
            break;
        }
    }
    candidate.map(|c| c.clone_ref(py))
}

struct C3Mro<'a> {
    seqs: &'a mut Vec<&'a mut Vec<PyTypeReference>>,
}

impl C3Mro<'_> {
    fn for_abcs<'a>(
        py: Python,
        abcs: &'a mut Vec<&'a mut Vec<PyTypeReference>>,
    ) -> PyResult<Vec<PyTypeReference>> {
        C3Mro { seqs: abcs }.merge(py)
    }

    fn merge(&mut self, py: Python) -> PyResult<Vec<PyTypeReference>> {
        let mut result: Vec<PyTypeReference> = Vec::new();
        loop {
            let seqs = &mut self.seqs;
            seqs.retain(|seq| !seq.is_empty());
            if seqs.is_empty() {
                return Ok(result);
            }
            match find_merge_candidate(py, seqs.as_slice()) {
                Some(c) => {
                    for i in 0..seqs.len() {
                        let seq = &mut self.seqs[i];
                        if seq[0].eq(&c) {
                            seq.remove(0);
                        }
                    }
                    result.push(c);
                }
                None => return Err(PyRuntimeError::new_err("Inconsistent hierarchy")),
            }
        }
    }
}

fn c3_boundary(py: Python, bases: &[PyTypeReference]) -> usize {
    let mut boundary = 0;

    for (i, base) in bases.iter().rev().enumerate() {
        if base
            .wrapped()
            .bind(py)
            .hasattr(intern!(py, "__abstractmethods__"))
            .unwrap()
        {
            boundary = bases.len() - i;
            break;
        }
    }

    boundary
}

fn c3_mro(
    py: Python,
    cls: &Bound<'_, PyAny>,
    abcs: Vec<PyTypeReference>,
) -> PyResult<Vec<PyTypeReference>> {
    let bases = match get_obj_bases(cls) {
        Ok(b) => {
            if !b.is_empty() {
                b
            } else {
                return Ok(Vec::new());
            }
        }
        Err(e) => return Err(e),
    };
    let boundary = c3_boundary(py, &bases);
    eprintln!("boundary = {boundary}");
    let base = &bases[boundary];

    let (explicit_bases, other_bases) = bases.split_at(boundary);
    let abstract_bases: Vec<_> = abcs
        .iter()
        .flat_map(|abc| {
            if Builtins::cached(py)
                .issubclass(py, cls, base.wrapped().bind(py))
                .unwrap()
                && !bases.iter().any(|b| {
                    Builtins::cached(py)
                        .issubclass(py, b.wrapped().bind(py), base.wrapped().bind(py))
                        .unwrap()
                })
            {
                vec![abc]
            } else {
                vec![]
            }
        })
        .collect();

    let new_abcs: Vec<_> = abcs.iter().filter(|c| abstract_bases.contains(c)).collect();

    let mut mros: Vec<&mut Vec<PyTypeReference>> = Vec::new();

    let mut cls_ref = vec![PyTypeReference::new(cls.clone().unbind())];
    mros.push(&mut cls_ref);

    let mut explicit_bases_mro = Vec::from_iter(explicit_bases.iter().map(|b| {
        c3_mro(
            py,
            b.wrapped().bind(py),
            new_abcs.iter().map(|abc| abc.clone_ref(py)).collect(),
        )
        .unwrap()
    }));
    mros.extend(&mut explicit_bases_mro);

    let mut abstract_bases_mro = Vec::from_iter(abstract_bases.iter().map(|b| {
        c3_mro(
            py,
            b.wrapped().bind(py),
            new_abcs.iter().map(|abc| abc.clone_ref(py)).collect(),
        )
        .unwrap()
    }));
    mros.extend(&mut abstract_bases_mro);

    let mut other_bases_mro = Vec::from_iter(other_bases.iter().map(|b| {
        c3_mro(
            py,
            b.wrapped().bind(py),
            new_abcs.iter().map(|abc| abc.clone_ref(py)).collect(),
        )
        .unwrap()
    }));
    mros.extend(&mut other_bases_mro);

    let mut explicit_bases_cloned = Vec::from_iter(explicit_bases.iter().map(|b| b.clone_ref(py)));
    mros.push(&mut explicit_bases_cloned);

    let mut abstract_bases_cloned = Vec::from_iter(abstract_bases.iter().map(|b| b.clone_ref(py)));
    mros.push(&mut abstract_bases_cloned);

    let mut other_bases_cloned = Vec::from_iter(other_bases.iter().map(|b| b.clone_ref(py)));
    mros.push(&mut other_bases_cloned);

    C3Mro::for_abcs(py, &mut mros)
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
        .copied()
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
                if !mro.contains(tref) {
                    mro.push(tref.clone_ref(py));
                }
            });
        }
    });

    c3_mro(py, &cls, mro)
}
