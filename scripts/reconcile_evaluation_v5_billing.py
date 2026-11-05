"""Offline reconciliation of a provider CSV; never changes request reservations.

The CSV is a timestamp-bounded observation, not an invoice or a guarantee that
an omitted request will never be billed. Preserve higher-precision API costs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/evaluation_v5"
D = Decimal


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def instant(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    args = parser.parse_args()
    source = Path(args.csv)
    raw = source.read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    rows = list(reader)
    required = {"generation_id", "created_at", "cost_total", "model_permaslug"}
    if not required <= set(reader.fieldnames or []):
        raise ValueError("Missing provider export columns")
    index = {r["generation_id"]: r for r in rows}
    if len(index) != len(rows):
        raise ValueError("Duplicate generation IDs; reconcile export before counting")
    if not rows:
        raise ValueError("Empty export")

    reservations = []
    before = {}
    for path in sorted((ROOT / "output/evaluation_v2/calls").glob("*/reservation.json")):
        b = path.read_bytes()
        before[str(path.relative_to(ROOT))] = sha(b)
        reservations.append(json.loads(b))
    study_path = ROOT / "output/study_v3/judge_ledger.json"
    study_raw = study_path.read_bytes()
    study = json.loads(study_raw)
    known_v2 = [r for r in reservations if r.get("actual_cost_usd") is not None]
    unknown_v2 = [r for r in reservations if r.get("actual_cost_usd") is None]
    known_study = [r for r in study if r.get("actual_cost_usd") is not None]
    known_ids = {r.get("response_id") for r in known_v2} | {r.get("generation_id") for r in known_study}
    known_ids.discard(None)
    by_id_v2 = {r["response_id"]: r for r in known_v2}
    by_id_study = {r["generation_id"]: r for r in known_study}

    def matched_summary(records, key):
        missing, mismatches, matches = [], [], []
        for record in records:
            gid = record.get(key)
            exported = index.get(gid)
            if exported is None:
                missing.append({"generation_id": gid, "api_cost_usd": record["actual_cost_usd"]})
                continue
            original, observed = D(str(record["actual_cost_usd"])), D(exported["cost_total"])
            gap = original - observed
            # This export truncates at six decimal places, including trailing zeros.
            precision_only = D(0) <= gap < D("0.000001")
            match = {"generation_id": gid, "api_cost_usd": str(original), "csv_cost_usd": str(observed),
                     "api_minus_csv_usd": str(gap), "matches_within_csv_precision": precision_only}
            matches.append(match)
            if not precision_only:
                mismatches.append(match)
        return {"known_records": len(records), "matched_records": len(matches), "missing_records": missing,
                "cost_discrepancies_beyond_csv_precision": mismatches,
                "known_api_cost_usd": str(sum((D(str(r["actual_cost_usd"])) for r in records), D(0))),
                "matched_csv_cost_usd": str(sum((D(r["csv_cost_usd"]) for r in matches), D(0))),
                "matches": matches}

    first_v2 = min(instant(r["created_at"]) for r in reservations)
    last_v2 = max(instant(r["completed_at"]) for r in reservations)
    export_end = max(instant(r["created_at"]) for r in rows)
    export_start = min(instant(r["created_at"]) for r in rows)
    project_window = [r for r in rows if instant(r["created_at"]) >= first_v2 - timedelta(seconds=5)]
    extra = [r for r in project_window if r["generation_id"] not in known_ids]
    failure_checks = []
    for r in sorted(unknown_v2, key=lambda x: x["created_at"]):
        start = instant(r["created_at"])
        end = instant(r["completed_at"])
        nearby = [p for p in rows if start - timedelta(minutes=2) <= instant(p["created_at"]) <= end + timedelta(minutes=2)]
        unmatched = [p for p in nearby if p["generation_id"] not in known_ids]
        failure_checks.append({"call_id": r["id"], "model": r["model"], "created_at": r["created_at"],
            "completed_at": r["completed_at"], "reserved_usd": r["reserved_usd"],
            "provider_generation_id": r.get("response_id"), "status": "no_additional_exported_charge_identified" if not unmatched else "unmatched_transaction_requires_review",
            "nearby_exported_generation_ids": [p["generation_id"] for p in nearby],
            "nearby_unmatched_generation_ids": [p["generation_id"] for p in unmatched],
            "individual_zero_charge_confirmed": False})

    OUT.mkdir(parents=True, exist_ok=True)
    safe_fields = ["generation_id", "created_at", "cost_total", "cost_web_search", "cost_cache", "cost_file_processing",
                   "tokens_prompt", "tokens_completion", "tokens_reasoning", "tokens_cached", "model_permaslug",
                   "provider_name", "cancelled", "finish_reason_normalized"]
    safe_fields = [f for f in safe_fields if f in reader.fieldnames]
    sanitized = OUT / "provider-transactions-sanitized.csv"
    with sanitized.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=safe_fields + ["matched_local_ledger"])
        writer.writeheader()
        for row in rows:
            gid = row["generation_id"]
            ledger = "evaluation_v2" if gid in by_id_v2 else "study_v3" if gid in by_id_study else "outside_reconciled_ledgers"
            writer.writerow({k: row.get(k) for k in safe_fields} | {"matched_local_ledger": ledger})

    v2_summary = matched_summary(known_v2, "response_id")
    study_summary = matched_summary(known_study, "generation_id")
    evidence_supports_review = (not v2_summary["missing_records"] and not v2_summary["cost_discrepancies_beyond_csv_precision"]
                               and not extra and export_start <= first_v2 and export_end >= last_v2)
    unchanged = all(sha((ROOT / p).read_bytes()) == h for p, h in before.items())
    result = {
        "schema": "evaluation-v5-offline-billing-reconciliation-1", "created_at": datetime.now(timezone.utc).isoformat(),
        "source_csv": {"path": str(source), "sha256": sha(raw), "rows": len(rows), "unique_generation_ids": len(index),
                       "earliest_record_utc": export_start.isoformat(), "latest_record_utc": export_end.isoformat(),
                       "timezone_interpretation": "CSV naive timestamps interpreted as UTC; consistent with generation-ID timestamps",
                       "cost_precision": "CSV values truncated to six decimal places; preserve higher-precision known API usage.cost"},
        "sanitized_csv": {"path": str(sanitized.relative_to(ROOT)), "sha256": sha(sanitized.read_bytes()),
                          "removed_identity_fields": ["user", "api_key_name", "api_key_disabled", "app_name"]},
        "v2": v2_summary, "separate_study_v3": study_summary,
        "separate_study_v3_snapshot": {"sha256": sha(study_raw), "records": len(study),
             "unresolved_records": sum(r.get("actual_cost_usd") is None for r in study),
             "changed_during_reconciliation": sha(study_path.read_bytes()) != sha(study_raw)},
        "v2_window": {"first_request_utc": first_v2.isoformat(), "last_completion_utc": last_v2.isoformat()},
        "provider_rows_since_v2_start": len(project_window),
        "unmatched_provider_rows_since_v2_start": [{k: r[k] for k in safe_fields} for r in extra],
        "unresolved_v2_requests": failure_checks,
        "reservation_review": {"evidence_supports_review_of_full_reservation": evidence_supports_review,
            "candidate_release_usd": str(sum((D(str(r["reserved_usd"])) for r in unknown_v2), D(0))) if evidence_supports_review else "0",
            "release_applied_usd": "0", "original_reservations_unchanged": unchanged,
            "interpretation": "All known v2 generation IDs and recorded charges are accounted for within export precision, with no additional exported charges in the observed project window. This supports a dated aggregate reservation-release review; it is not per-request zero-charge confirmation.",
            "required_before_release": "Root must verify export provenance/filter coverage and billing finality/lag assumptions. Use an explicit append-only budget amendment; do not rewrite raw failed requests as actual_cost_usd=0. Reconcile later account usage and competing study spending separately."},
        "limitations": ["Export ends at its latest listed transaction and does not establish coverage through current time.",
                        "A CSV's absence of a transaction is not proof no delayed charge can occur.",
                        "Separate study_v3 charges and unknown requests are not automatically part of, or excluded from, this task's authorized budget; scope requires explicit reconciliation.",
                        "No old reservation, solver output, assessment or API response was changed."]}
    (OUT / "billing-reconciliation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"v2_matched": v2_summary["matched_records"], "v2_known": len(known_v2),
                      "v2_missing": len(v2_summary["missing_records"]), "cost_discrepancies": len(v2_summary["cost_discrepancies_beyond_csv_precision"]),
                      "unmatched_provider_rows_since_v2_start": len(extra), "export_latest": export_end.isoformat(),
                      "candidate_release_usd": result["reservation_review"]["candidate_release_usd"], "release_applied_usd": "0"}))


if __name__ == "__main__":
    main()
