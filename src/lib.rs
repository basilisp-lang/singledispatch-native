use pyo3::prelude::*;

mod singledispatch;

#[pymodule]
fn singledispatch_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(singledispatch::core::singledispatch, m)?)?;
    Ok(())
}
