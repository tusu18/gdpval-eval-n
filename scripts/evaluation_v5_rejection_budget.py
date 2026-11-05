"""Release only frozen, verified provider rejections before upstream inference.

This append-only layer preserves both raw null costs and every ambiguous
transport reservation. Future rejections require their own reviewed amendment.
"""
from decimal import Decimal

from evaluation_v5_transport_client import PythonTransportClient
from run_evaluation_v2 import BudgetStop, ROOT, digest, read

AMENDMENT = ROOT / "config/evaluation_v5_provider_rejection_reconciliation.json"


def confirmed_pre_inference_rejection(record, envelope):
    """Require positive provider evidence; a generic HTTP402 is insufficient."""
    if not isinstance(record, dict) or not isinstance(envelope, dict):
        return False
    body = envelope.get("body")
    if not isinstance(body, dict) or not isinstance(body.get("error"), dict):
        return False
    error = body["error"]
    metadata = error.get("metadata")
    routing = body.get("openrouter_metadata")
    if not isinstance(metadata, dict) or not isinstance(routing, dict):
        return False
    endpoints = routing.get("endpoints")
    available = endpoints.get("available") if isinstance(endpoints, dict) else None
    return (record.get("scope") == "judge_v5_crossfamily"
            and record.get("actual_cost_usd") is None
            and record.get("status") == "failed_unknown_charge"
            and record.get("http_status") == envelope.get("status") == error.get("code") == 402
            and metadata.get("reason") == "in_flight_budget_exhausted"
            and metadata.get("limit_source") == "openrouter_in_flight_budget"
            and type(routing.get("attempt")) is int and routing["attempt"] == 0
            and isinstance(available, list) and bool(available)
            and all(isinstance(item, dict) and item.get("selected") is False for item in available)
            and "provider_name" in metadata and metadata["provider_name"] is None
            and record.get("served_provider") is None
            and not body.get("id") and not record.get("response_id")
            and not body.get("usage")
            and str((envelope.get("headers") or {}).get("retry-after")) == "120")


class ProviderRejectionReconciledClient(PythonTransportClient):
    def totals(self):
        base = super().totals()
        amendment = read(AMENDMENT)
        if amendment["api_total_limit_usd"] != 30:
            raise BudgetStop("Provider rejection amendment may not raise USD30 ceiling")
        calls = amendment["rejected_requests"]
        if len(calls) != amendment["verified_request_count"] or len({r["id"] for r in calls}) != len(calls):
            raise BudgetStop("Provider rejection amendment has duplicate or missing identities")
        released = Decimal(0)
        for row in calls:
            reservation_path = ROOT / row["reservation_path"]
            response_path = ROOT / row["response_path"]
            if digest(reservation_path) != row["reservation_sha256"] or digest(response_path) != row["response_sha256"]:
                raise BudgetStop("Reviewed provider rejection evidence changed; inspect before new spending")
            record, envelope = read(reservation_path), read(response_path)
            if record.get("id") != row["id"] or not confirmed_pre_inference_rejection(record, envelope):
                raise BudgetStop("Request no longer meets strict pre-inference rejection criteria")
            amount = Decimal(str(record["reserved_usd"]))
            if not amount.is_finite() or amount < 0 or amount != Decimal(str(row["reserved_usd"])):
                raise BudgetStop("Provider rejection reservation amount changed")
            released += amount
        if released != Decimal(amendment["released_reservation_usd"]):
            raise BudgetStop("Provider rejection release arithmetic changed")
        if Decimal(str(base["unresolved_reserved_usd"])) + Decimal("0.00000001") < released:
            raise BudgetStop("Provider rejection release exceeds current unresolved reserves")
        return {**base,
                "commitment_before_provider_rejection_release_usd": base["committed_usd"],
                "provider_pre_inference_released_reservation_usd": float(released),
                "confirmed_pre_inference_rejection_count": len(calls),
                "unresolved_reserved_usd": round(base["unresolved_reserved_usd"] - float(released), 10),
                "committed_usd": round(base["committed_usd"] - float(released), 10),
                "provider_rejection_reconciliation_path": str(AMENDMENT)}


def make_client(key_file=None):
    from evaluation_v5_transport_client import make_client as transport_make_client
    client = transport_make_client(key_file)
    client.__class__ = ProviderRejectionReconciledClient
    return client
