use pyo3::prelude::*;
use std::fmt::{Debug, Display, Formatter};
use std::hash::{Hash, Hasher};

pub struct PyTypeReference {
    wrapped: Py<PyAny>,
}

impl PyTypeReference {
    pub(crate) fn new(py_object: Py<PyAny>) -> Self {
        PyTypeReference { wrapped: py_object }
    }

    pub(crate) fn wrapped(&self) -> &Py<PyAny> {
        &self.wrapped
    }

    pub(crate) fn clone_ref(&self, py: Python) -> Self {
        Self {
            wrapped: self.wrapped.clone_ref(py),
        }
    }
}

impl Debug for PyTypeReference {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        Display::fmt(&self.wrapped, f)
    }
}

impl Display for PyTypeReference {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        Display::fmt(&self.wrapped, f)
    }
}

impl Hash for PyTypeReference {
    fn hash<H: Hasher>(&self, state: &mut H) {
        self.wrapped.as_ptr().hash(state)
    }
}

impl PartialEq for PyTypeReference {
    fn eq(&self, other: &Self) -> bool {
        self.wrapped.is(&other.wrapped)
    }
}

impl Eq for PyTypeReference {}
