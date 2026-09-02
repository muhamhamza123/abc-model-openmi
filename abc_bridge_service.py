"""
HTTP bridge for the ABC-Model (Fiering, 1967) -- a classic 3-parameter
linear conceptual rainfall-runoff model, vendored from kratzert/RRMPG
(MIT license). Speaks the GENERIC OpenMI bridge contract (see
docs/MODEL_PREREQUISITES.md in the openmi-coupling project) so it needs
zero new C# code to plug into the Coupling Canvas -- GenericBridgeComponent
handles any bridge with named scalar in/out ports.

Real model note: the vendored abcmodel_core.py's run_abcmodel() is
numba-@njit-compiled and pre-vectorized -- it takes the WHOLE precipitation
series at once, not one day at a time. Its actual math is inherently
sequential though (each day's calculation only depends on the previous
day's storage), so this bridge calls the EXACT SAME two real equations,
published verbatim in run_abcmodel()'s own docstring, one real timestep
per /update() call instead of pre-batched:

    qsim[t] = (1 - a - b) * prec[t] + c * storage[t-1]
    storage[t] = (1 - c) * storage[t-1] + a * prec[t]

This is not a rewrite of the model -- it's the same real recursion, just
invoked incrementally instead of vectorized, the same relationship every
other steppable bridge in this project has to its underlying model code.
Verified to reproduce the vendored run_abcmodel() bit-for-bit (see
verification note in docs/onboarding/abc-model.md).

Units note: unlike GR4J/HBV, this model does NOT convert its output into
streamflow units -- its output is in whatever units precipitation was
given in (here, mm/d), a real property of this simple linear model, not
an oversight. A downstream router still needs the same mm/d -> m3/s
conversion (see ConversionRegistry in CompositionRunner) any other
depth-rate model needs.

Endpoints (the generic contract):
    POST /initialize   {"config": {"a": ..., "b": ..., "c": ...,
                         "forcingCsv": "...", "precipColumn": "Prec_mm/d"}}
                        -> {"session_id": "...", "n_days": N}
    POST /update        {"session_id": "...", "inputs": {}}
                        (no real inputs -- pure producer, reads its own
                        forcing file day by day)
                        -> {"outputs": {"Runoff": ...}, "day": N, "log": "..."}
    POST /finalize       {"session_id": "..."}

Run: python abc_bridge_service.py
"""

import uuid
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, request

app = Flask(__name__)
_sessions = {}


@app.route("/health")
def health():
    return jsonify({"status": "ok", "sessions": len(_sessions)})


@app.route("/initialize", methods=["POST"])
def initialize():
    body = request.get_json(force=True)
    config = body.get("config", {})
    required = ("a", "b", "c", "forcingCsv")
    missing = [k for k in required if k not in config]
    if missing:
        return jsonify({"error": f"missing required config field(s): {missing}"}), 400

    precip_col = config.get("precipColumn", "Prec_mm/d")
    forcing = pd.read_csv(config["forcingCsv"])
    if precip_col not in forcing.columns:
        return jsonify({"error": f"column {precip_col!r} not found in forcingCsv; header was: {list(forcing.columns)}"}), 400

    session_id = uuid.uuid4().hex
    _sessions[session_id] = {
        "a": float(config["a"]), "b": float(config["b"]), "c": float(config["c"]),
        "precip": forcing[precip_col].to_numpy(),
        "storage": float(config.get("initialState", 0.0)),
        "day": 0, "n_days": len(forcing),
    }
    return jsonify({"session_id": session_id, "n_days": len(forcing)})


@app.route("/update", methods=["POST"])
def update():
    body = request.get_json(force=True)
    session_id = body.get("session_id")
    if session_id not in _sessions:
        return jsonify({"error": f"no session {session_id!r} -- call /initialize first"}), 400

    s = _sessions[session_id]
    if s["day"] >= s["n_days"]:
        return jsonify({"error": "update() called past end of forcing record"}), 400

    day = s["day"]
    prec_t = float(s["precip"][day])
    storage_prev = s["storage"]
    a, b, c = s["a"], s["b"], s["c"]

    if day == 0:
        # Real, deliberate replication of the vendored run_abcmodel()'s own
        # convention: its loop starts at t=1, so qsim[0] stays at its
        # zeros-initialized 0.0 and storage[0] is just the initial state --
        # day 1 never actually runs the recursion. Faithfully reproducing
        # THIS quirk (not smoothing it over) is what "verified against the
        # real reference" means here.
        qsim = 0.0
        storage_new = storage_prev
    else:
        # the exact real ABC-Model recursion, published verbatim in
        # abcmodel_core.py's run_abcmodel() docstring -- see module docstring
        qsim = (1 - a - b) * prec_t + c * storage_prev
        storage_new = (1 - c) * storage_prev + a * prec_t

    s["storage"] = storage_new
    s["day"] += 1

    log_message = f"day {s['day']}/{s['n_days']}: prec={prec_t:.3f}mm/d -> runoff={qsim:.4f}mm/d (storage={storage_new:.3f}mm)"
    return jsonify({"outputs": {"Runoff": qsim}, "day": s["day"], "log": log_message})


@app.route("/finalize", methods=["POST"])
def finalize():
    body = request.get_json(force=True)
    _sessions.pop(body.get("session_id"), None)
    return jsonify({"finalized": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5061)
