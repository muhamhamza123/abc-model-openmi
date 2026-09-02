# ABC-Model — OpenMI-wrapped

The classic ABC-Model (Myron B. Fiering, *Streamflow synthesis*, Harvard
University Press, 1967) — a minimal 3-parameter linear conceptual
rainfall-runoff model.

`abcmodel_core.py` is vendored, unmodified, from
[kratzert/RRMPG](https://github.com/kratzert/RRMPG) (MIT license, see
`LICENSE_ABCMODEL_ORIGINAL`).

`abc_bridge_service.py` wraps it in the generic OpenMI bridge contract
used by [openmi-coupling](https://github.com) (this project's Coupling
Canvas) — `/health`, `/initialize`, `/update`, `/finalize`, speaking the
`{"inputs": {...}} -> {"outputs": {...}}` shape `GenericBridgeComponent`
expects, so it needs zero new C# code to register.

Real model note: the vendored `run_abcmodel()` is pre-vectorized (takes
the whole precipitation series at once). The bridge calls the exact same
published two-equation recursion one real timestep at a time instead,
including its (real, deliberate) quirk that the very first precipitation
value in a series is never used — verified to reproduce the vendored
function's output bit-for-bit, day by day.

## Files

- `abcmodel_core.py` — the real, unmodified model core (needs `numpy` + `numba`)
- `abc_bridge_service.py` — the OpenMI bridge (needs `flask`, `pandas`)
- `abc_config.yaml` — example config (a, b, c, forcing CSV)
- `abc_calibration.yaml` — real published parameter bounds, with a documented
  known limitation (a real cross-parameter constraint the calibration engine
  doesn't enforce)

## Run

```
python abc_bridge_service.py
```
