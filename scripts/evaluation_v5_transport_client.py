"""Explicit transport-only amendment retaining the locked cumulative budget.

Original requests and failed-call reservations remain immutable. The request
body, judge parameters, model routing and budget formula are unchanged; only
the one-dispatch HTTPS transport changes to standard-library Python.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
import uuid

from evaluation_v5_budget import ReconciledClient
from run_evaluation_v2 import ROOT, BudgetStop, canonical, digest, now, write

PYTHON = Path("/Users/tusu18/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3")
TRANSPORT = ROOT / "scripts/evaluation_v5_transport.py"


class PythonTransportClient(ReconciledClient):
    def call(self, body, route="chat/completions", scope="judge", label="call"):
        if route != "chat/completions":
            raise ValueError("This amended inference client supports chat/completions only")
        if (self.root / "BUDGET_BOUND_BREACH.json").exists():
            raise BudgetStop("Budget accounting requires review")
        body = json.loads(json.dumps(body))
        pricing = self.models[body["model"]]["pricing"]
        body.setdefault("provider", {}).update(allow_fallbacks=False, require_parameters=True,
            max_price={"prompt": float(pricing["prompt"]) * 1e6, "completion": float(pricing["completion"]) * 1e6})
        if len(canonical(body).encode()) > 12_000_000:
            raise ValueError("Request size exceeds preflight limit")
        reservation = self.reservation(body)
        with self.locked():
            totals = self.totals()
            ceiling = min(30.0, self.cfg["authorized_available_budget_usd"])
            if totals["committed_usd"] + reservation > ceiling:
                raise BudgetStop("Request would exceed global dollar reservation ceiling")
            if scope.startswith("solver") and totals["solver_committed_usd"] + reservation > self.cfg["solver_ceiling_usd"]:
                raise BudgetStop("Solver ceiling reached; preserve money for grading")
            ident = uuid.uuid4().hex
            folder = self.root / "calls" / ident
            folder.mkdir(parents=True)
            record = {"id": ident, "label": label, "scope": scope, "route": route, "model": body["model"],
                      "reserved_usd": reservation, "actual_cost_usd": None, "status": "reserved_before_dispatch",
                      "created_at": now(), "request_sha256": hashlib.sha256(canonical(body).encode()).hexdigest(),
                      "transport": "evaluation_v5_python_http_client_single_dispatch",
                      "transport_sha256": digest(TRANSPORT)}
            write(folder / "request.json", body)
            write(folder / "reservation.json", record)
        started = time.monotonic()
        timeout = min(240, self.cfg["request_timeout_seconds"])
        try:
            process = subprocess.run([str(PYTHON), str(TRANSPORT)],
                input=json.dumps({"key": self.key, "route": route, "body": body, "timeout_ms": timeout * 1000}),
                capture_output=True, text=True, timeout=timeout + 15)
            if process.returncode:
                raise RuntimeError("Transport process failed: " + process.stderr.replace(self.key, "[REDACTED]")[:300])
            envelope = json.loads(process.stdout)
            if not isinstance(envelope, dict):
                raise ValueError("Transport envelope is not an object")
        except Exception as error:
            envelope = {"status": None, "transport_error": str(error).replace(self.key, "[REDACTED]")[:300],
                        "request_body_sent": "unknown"}
        write(folder / "response.json", envelope)
        result = envelope.get("body", {})
        if not isinstance(result, dict):
            result = {"invalid_response_body_type": type(result).__name__}
        usage = result.get("usage") or {}
        if not isinstance(usage, dict):
            usage = {}
        cost = usage.get("cost")
        if cost is None:
            cost = (usage.get("cost_details") or {}).get("total_cost")
        if type(cost) in (int, float) and math.isfinite(cost) and cost >= 0:
            record["actual_cost_usd"] = cost
        routing = result.get("openrouter_metadata") or {}
        selected = [x for x in (routing.get("endpoints") or {}).get("available", []) if x.get("selected") is True]
        served = selected[0] if len(selected) == 1 else {}
        record.update(status="response_recorded" if envelope.get("status") == 200 and not result.get("error") else "failed_unknown_charge",
                      http_status=envelope.get("status"), elapsed_seconds=round(time.monotonic() - started, 3),
                      completed_at=now(), response_id=result.get("id"), served_provider=result.get("provider") or served.get("provider"),
                      served_model=served.get("model"), routing_metadata=routing or None, usage=usage)
        with self.locked():
            write(folder / "reservation.json", record)
            if record["actual_cost_usd"] is not None and record["actual_cost_usd"] > reservation:
                write(self.root / "BUDGET_BOUND_BREACH.json", {"request_id": ident, "actual": cost, "reservation": reservation})
        if (self.root / "BUDGET_BOUND_BREACH.json").exists():
            raise BudgetStop("Observed charge exceeded conservative request reservation; inspect before continuing")
        if record["status"] != "response_recorded":
            message = envelope.get("transport_error") or str(result.get("error") or envelope.get("status"))
            raise RuntimeError(f"Physical request {ident} failed; retained charge reserve; no retry: {message[:350]}")
        return result, {"call_id": ident, **record}


def make_client(key_file=None):
    """Reuse the frozen runner's catalog/settings and change transport explicitly."""
    from run_evaluation_v5_crossjudge import make_client as original_make_client
    client = original_make_client(key_file)
    client.__class__ = PythonTransportClient
    return client
