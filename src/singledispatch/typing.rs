use crate::singledispatch::typeref::PyTypeReference;
use pyo3::exceptions::PyTypeError;
use pyo3::prelude::*;
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyDict, PyTuple};
use pyo3::{Bound, IntoPyObjectExt, Py, PyAny, PyResult, Python};

pub struct TypingModule {
    get_args: Py<PyAny>,
    get_origin: Py<PyAny>,
    get_type_hints: Py<PyAny>,
    pub generic_alias_type: PyTypeReference,
    union_types: Vec<PyTypeReference>,
}

static TYPING_MODULE: PyOnceLock<TypingModule> = PyOnceLock::new();

impl TypingModule {
    fn new(py: Python) -> Self {
        let typing_module = py.import("typing").unwrap();
        let types_module = py.import("types").unwrap();
        let mut union_types = Vec::with_capacity(2);
        union_types.extend([
            PyTypeReference::new(
                typing_module
                    .getattr("Union")
                    .unwrap()
                    .into_py_any(py)
                    .unwrap(),
            ),
            PyTypeReference::new(
                types_module
                    .getattr("UnionType")
                    .unwrap()
                    .into_py_any(py)
                    .unwrap(),
            ),
        ]);

        TypingModule {
            get_args: typing_module
                .getattr("get_args")
                .unwrap()
                .into_py_any(py)
                .unwrap(),
            get_origin: typing_module
                .getattr("get_origin")
                .unwrap()
                .into_py_any(py)
                .unwrap(),
            get_type_hints: typing_module
                .getattr("get_type_hints")
                .unwrap()
                .into_py_any(py)
                .unwrap(),
            generic_alias_type: PyTypeReference::new(
                types_module
                    .getattr("GenericAlias")
                    .unwrap()
                    .into_py_any(py)
                    .unwrap(),
            ),
            union_types,
        }
    }

    pub fn cached(py: Python<'_>) -> &Self {
        TYPING_MODULE.get_or_init(py, || TypingModule::new(py))
    }

    pub fn get_args(&self, py: Python, cls: &Bound<'_, PyAny>) -> PyResult<Py<PyTuple>> {
        match self.get_args.call1(py, PyTuple::new(py, [cls])?) {
            Ok(maybe_args) => match maybe_args.cast_bound::<PyTuple>(py) {
                Ok(args) => Ok(args.clone().unbind().clone_ref(py)),
                Err(_) => Err(PyTypeError::new_err("Expected tuple return value")),
            },
            Err(e) => Err(e),
        }
    }

    pub fn get_type_hints<'py>(
        &self,
        py: Python<'py>,
        obj: &Bound<'_, PyAny>,
    ) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
        let ret = self.get_type_hints.call1(py, PyTuple::new(py, [obj])?)?;
        let hints = ret.cast_bound::<PyDict>(py)?;
        match hints.iter().next() {
            Some((argname, cls)) => Ok((argname, cls)),
            None => Err(PyTypeError::new_err(format!(
                "no type hints found for {obj}"
            ))),
        }
    }

    pub fn get_origin(&self, py: Python, cls: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
        self.get_origin.call1(py, PyTuple::new(py, [cls])?)
    }

    pub fn is_union_type(&self, py: Python, cls: &Bound<'_, PyAny>) -> PyResult<bool> {
        Ok(self.union_types.iter().any(|v| {
            let other_cls = &v.wrapped().bind_borrowed(py);
            cls.is(other_cls) || cls.is_instance(other_cls).unwrap_or(false)
        }))
    }
}
