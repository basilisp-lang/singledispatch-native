use pyo3::prelude::*;
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyBool, PyTuple};
use pyo3::{IntoPyObjectExt, PyAny, Python};

pub struct Builtins {
    pub object_type: Py<PyAny>,
    issubclass_func: Py<PyAny>,
}

static PY_BUILTINS: PyOnceLock<Builtins> = PyOnceLock::new();

impl Builtins {
    fn new(py: Python) -> Self {
        let builtins_module = py.import("builtins").unwrap();
        Builtins {
            object_type: builtins_module
                .getattr("object")
                .unwrap()
                .into_py_any(py)
                .unwrap(),
            issubclass_func: builtins_module
                .getattr("issubclass")
                .unwrap()
                .into_py_any(py)
                .unwrap(),
        }
    }

    pub fn cached(py: Python<'_>) -> &Self {
        PY_BUILTINS.get_or_init(py, || Builtins::new(py))
    }

    pub fn issubclass(
        &self,
        py: Python,
        cls: &Bound<'_, PyAny>,
        typ: &Bound<'_, PyAny>,
    ) -> PyResult<bool> {
        let args = PyTuple::new(py, [cls, typ]);
        match self.issubclass_func.call1(py, args?) {
            Ok(result) => Ok(result.cast_bound::<PyBool>(py)?.is_true()),
            Err(e) => Err(e),
        }
    }
}
