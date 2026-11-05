"""Append-only aggregate reconciliation for the existing evaluation budget.

Raw ambiguous calls remain unknown. The reviewed amendment changes only the
aggregate reservation used for future dispatch, and keeps a delayed-billing
contingency. A changed old record stops execution rather than double counting.
"""
from decimal import Decimal

from run_evaluation_v2 import Client, BudgetStop, ROOT, digest, read

AMENDMENT = ROOT / "config/evaluation_v5_budget_reconciliation.json"


class ReconciledClient(Client):
    def totals(self):
        raw = super().totals()
        amendment = read(AMENDMENT)
        if amendment["api_total_limit_usd"] != 30:
            raise BudgetStop("Reconciliation may not increase the USD30 ceiling")
        original = Decimal(0)
        for row in amendment["unknown_v2_requests"]:
            path = ROOT / row["reservation_path"]
            if digest(path) != row["original_reservation_sha256"]:
                raise BudgetStop("A reconciled historical request changed; review new billing evidence")
            record = read(path)
            if record.get("actual_cost_usd") is not None:
                raise BudgetStop("Historical charge resolved; refresh aggregate adjustment before dispatch")
            original += Decimal(str(record["reserved_usd"]))
        adjustment = amendment["aggregate_reservation_adjustment"]
        released = Decimal(adjustment["released_usd"])
        retained = Decimal(adjustment["retained_delayed_billing_contingency_usd"])
        if original != released + retained or retained < 0 or released < 0:
            raise BudgetStop("Invalid aggregate reservation arithmetic")
        if Decimal(str(raw["unresolved_reserved_usd"])) + Decimal("0.00000001") < released:
            raise BudgetStop("Reservation adjustment exceeds outstanding ledger reservations")
        return {**raw,
                "raw_ledger_committed_usd": raw["committed_usd"],
                "raw_ledger_unresolved_reserved_usd": raw["unresolved_reserved_usd"],
                "aggregate_released_reservation_usd": float(released),
                "historical_delayed_billing_contingency_usd": float(retained),
                "unresolved_reserved_usd": round(raw["unresolved_reserved_usd"] - float(released), 10),
                "committed_usd": round(raw["committed_usd"] - float(released), 10),
                "budget_reconciliation_path": str(AMENDMENT)}
