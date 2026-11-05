"""Describe the new cross-family judging extension without rewriting old grades.

Reads only the current forty-task packet inventory and the runner's result records.
Missing, invalid, transport-failed and budget-blocked calls never become verdicts.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/evaluation_v5"
VERDICTS = ("pass", "fail", "uncertain", "not_assessed")
FAMILIES = ("Gemini", "Claude")
LIMITATIONS = [
    "The forty original tasks span v2 API, v3 in-app and v4 in-app solver cohorts. Report these conditions separately; this is not a model ranking.",
    "Existing Astra assessments cover 25 selected outputs, not 40. Missing baselines are excluded from paired comparisons rather than treated as passes or failures.",
    "Astra used agentic inspection. New API judges may have different evidence retrieval, visual exposure, native execution and external research capabilities. Matching artifacts and rubrics does not isolate a judge-family effect.",
    "Agreement measures consistency between judgments, not correctness. No majority, unanimous or AND rule creates a ground-truth verdict. Any-judge flags are review candidates only.",
    "The four existing selected, evidence-assisted, nonblind human reviews are diagnostic. They do not establish expert acceptance, representative accuracy or a false-accept rate.",
    "Structural validity and quotation verification are distinct from substantive accuracy. A valid judgment may still apply an inappropriate criterion or misread evidence.",
    "The original order-audit robustness criterion remains frozen. The user's optional-improvement decision is preserved separately; no retrospective score repair is performed.",
    "Construct-preserving and construct-changing probe tests remain proposed unless a separate executed test ledger and human direction labels establish otherwise. No S/R result is inferred from judge agreement.",
]


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local_path(path):
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def relative(path):
    return os.path.relpath(local_path(path), ROOT)


def family(model):
    model = str(model).lower()
    if "gemini" in model:
        return "Gemini"
    if "claude" in model:
        return "Claude"
    return None


def aggregate(criteria):
    values = [c["verdict"] for c in criteria]
    if "fail" in values:
        return "fail"
    if any(v != "pass" for v in values):
        return "uncertain"
    return "pass" if values else None


def normalized_overall(value):
    value = str(value or "")
    return value.removeprefix("project_rubric_") if value else None


def safe_assessment(value):
    """Normalize only the analysis view; the linked raw file remains untouched."""
    if not isinstance(value, dict):
        return {"criteria": [], "_analysis_input_shape_errors": ["Assessment is not a JSON object"]}
    value = dict(value)
    rows = value.get("criteria")
    errors = []
    if not isinstance(rows, list):
        rows = []
        errors.append("criteria is not a list")
    kept = [r for r in rows if isinstance(r, dict) and isinstance(r.get("criterion_id"), str) and r.get("verdict") in VERDICTS]
    if len(kept) != len(rows):
        errors.append(f"{len(rows)-len(kept)} malformed criterion records retained only in raw assessment")
    value["criteria"] = kept
    value["_analysis_input_shape_errors"] = errors
    return value


def check_record(assessment, task, packet):
    """Analysis-integrity check only; never substitute it for the runner validator."""
    problems = list(assessment.get("_analysis_input_shape_errors", []))
    if assessment.get("task_id") != task["task_id"]:
        problems.append("task_id mismatch")
    if assessment.get("rubric_sha256") != packet.get("rubric_sha256"):
        problems.append("rubric hash mismatch")
    expected = [c.get("criterion_id", c.get("id")) for c in packet["criteria"]]
    actual = [c.get("criterion_id") for c in assessment.get("criteria", [])]
    if Counter(expected) != Counter(actual):
        problems.append("criterion set does not match frozen packet exactly")
    if any(c.get("verdict") not in VERDICTS for c in assessment.get("criteria", [])):
        problems.append("invalid criterion verdict")
    if not problems:
        observed = normalized_overall(assessment.get("overall"))
        if observed and observed != aggregate(assessment["criteria"]):
            problems.append("overall does not follow criterion aggregation")
    return problems


def evidence_summary(criterion):
    return {
        "criterion_id": criterion["criterion_id"],
        "verdict": criterion["verdict"],
        "severity": criterion.get("severity"),
        "failure_class": criterion.get("failure_class"),
        "reason": criterion.get("reason"),
        "rubric_scope_objection": criterion.get("rubric_scope_objection"),
        "coverage": criterion.get("coverage"),
        "evidence_location_note": "Exact source/output quotations remain in the linked raw assessment; this summary is not a new judgment.",
    }


def criterion_record_diagnostics(assessment, validation):
    """Retain usable segments while keeping the original document status intact."""
    criteria = assessment.get("criteria", [])
    ids = {str(c.get("criterion_id")) for c in criteria}
    per_criterion = defaultdict(list)
    global_errors = list(assessment.get("_analysis_input_shape_errors", []))
    for message in validation.get("contract_errors", []):
        prefix = str(message).split(":", 1)[0]
        if prefix in ids and ":" in str(message):
            per_criterion[prefix].append(message)
        else:
            global_errors.append(message)
    diagnostics = []
    for criterion in criteria:
        cid = criterion.get("criterion_id")
        quotes = [x for x in validation.get("quote_checks", []) if x.get("criterion_id") == cid]
        flags = [x for x in validation.get("provenance_flags", []) if x.get("criterion_id") == cid]
        diagnostics.append({
            "criterion_id": cid, "raw_verdict": criterion.get("verdict"),
            "criterion_contract_valid": not per_criterion[cid] and not global_errors,
            "criterion_contract_errors": per_criterion[cid], "global_contract_errors": global_errors,
            "source_evidence_records": len(criterion.get("source_evidence", [])),
            "output_evidence_records": len(criterion.get("output_evidence", [])),
            "quote_records": len(quotes),
            "text_verified_quote_records": sum(x.get("status") == "text_verified" for x in quotes),
            "unverified_quote_records": sum(x.get("status") != "text_verified" for x in quotes),
            "provenance_flag_count": len(flags),
            "interpretation": "A retained structural/evidence-record diagnostic, not independent proof of accuracy. An invalid full assessment remains excluded from primary paired statistics.",
        })
    return diagnostics


def load_repair(row, task, packet):
    repairs = {}
    for fam in FAMILIES:
        candidates = []
        for rp in sorted((OUT / "record-repairs").glob("*/result.json")):
            r = read(rp)
            if r.get("task_id") == task["task_id"] and family(r.get("judge_requested_model")) == fam:
                candidates.append((rp, r))
        cell = {"status": "not_repaired", "valid_for_comparison": False, "overall": None, "criteria": []}
        if len(candidates) > 1:
            cell.update(status="ambiguous_multiple_repairs", result_paths=[relative(x[0]) for x in candidates])
        elif candidates:
            rp, r = candidates[0]
            cell.update(status=r.get("status"), requested_model=r.get("judge_requested_model"), result_path=relative(rp),
                        not_independent_judgment=True, source="post_hoc_record_completion", calls=r.get("calls"))
            ap = local_path(r["assessment_path"]) if r.get("assessment_path") else rp.parent / "assessment.json"
            vp = local_path(r["validation_path"]) if r.get("validation_path") else rp.parent / "validation.json"
            cp = local_path(r["changes_path"]) if r.get("changes_path") else rp.parent / "changes.json"
            if cp.exists():
                cell.update(changes=read(cp), changes_path=relative(cp))
            if ap.exists() and vp.exists():
                a, v = safe_assessment(read(ap)), read(vp)
                errors = check_record(a, task, packet)
                for kind in ("result", "assessment"):
                    field = "original_" + kind + "_path"
                    original = row["judges"][fam].get(kind + "_path")
                    reported = r.get(field)
                    hash_value = r.get("original_" + kind + "_sha256", r.get("original_" + kind + "_hash"))
                    if not original or not reported or local_path(original) != local_path(reported):
                        errors.append(f"original {kind} path does not match first-pass record")
                    elif hash_value != sha(local_path(original)):
                        errors.append(f"original {kind} hash does not match first-pass record")
                if r.get("packet_sha256") != task["packet_sha256"] or r.get("rubric_sha256") != packet["rubric_sha256"]:
                    errors.append("repair packet/rubric hashes differ")
                if r.get("contract_valid") is not True or v.get("contract_valid") is not True or r.get("status") != "graded":
                    errors.append("repair record has not passed runner validation")
                if r.get("not_independent_judgment") is not True:
                    errors.append("repair must disclose dependence on the first assessment")
                valid = not errors and row["packet_integrity_verified"]
                cell.update(valid_for_comparison=valid, overall=aggregate(a["criteria"]) if valid else None,
                            criteria=a.get("criteria", []), assessment_path=relative(ap),
                            assessment_sha256=sha(ap), analysis_integrity_problems=errors,
                            criterion_record_diagnostics=criterion_record_diagnostics(a, v))
                if r.get("status") == "graded" and errors:
                    cell["status"] = "analysis_integrity_failure"
        repairs[fam] = cell
    return repairs


def scoped_human_comparisons(rows):
    allowed = {"43dc9778-450b-4b46-b77e-b6d82b202035": "TAX-05",
               "1137e2bb-bdf9-4876-b572-f29b7de5e595": "PRICE-03",
               "0fad6023-767b-42c1-a1b3-027cd4f583cb": "POG-05",
               "4520f882-715a-482d-8e87-1cb3cbdfe975": "PAY-04"}
    results = []
    for row in rows:
        human = row.get("existing_human_review")
        if not human or allowed.get(row["task_id"]) != human.get("criterion_id"):
            continue
        opinions = {}
        for judge in ("Astra", *FAMILIES):
            c = row["judges"][judge]
            match = next((x for x in c.get("criteria", []) if x["criterion_id"] == human["criterion_id"]), None)
            if not match:
                opinions[judge] = {"status": c["status"], "verdict": None}
                continue
            opinions[judge] = {"status": c["status"], "assessment_contract_valid": c["valid_for_comparison"],
                "raw_verdict": match["verdict"], "criterion": evidence_summary(match), "assessment_path": c["assessment_path"],
                "issue_match": "Requires manual comparison of the judge's reason with the exact human-reviewed issue; sharing a criterion ID is insufficient."}
        results.append({"task_id": row["task_id"], "rubric_format": row["rubric_format"], "criterion_id": human["criterion_id"],
            "human_review_path": human["path"], "human_scope": human["scope"],
            "human_classification": human.get("user_classification"), "human_acceptance_on_this_basis": human["human_acceptance"],
            "expert_gold": False, "blind_label": False, "judge_findings": opinions,
            "interpretation": "Selected non-specialist, evidence-assisted review. This side-by-side comparison is scoped to the stated issue, not the whole criterion or document. No accuracy, false-accept or missed-error rate is estimated."})
    return results


def assistant_evidence_checks(rows):
    task_ids = {r["task_id"] for r in rows}
    checks = []
    for path in sorted((OUT / "analyst-checks").glob("*-interpretation.json")):
        note = read(path)
        if note.get("task_id") not in task_ids:
            continue
        item = dict(note)
        item["interpretation_path"] = relative(path)
        item["interpretation_sha256"] = sha(path)
        item["human_review"] = False
        item["expert_validation"] = False
        item["replacement_benchmark_grade"] = False
        vp = local_path(note["verification_path"]) if note.get("verification_path") else None
        if vp and vp.exists():
            verification = read(vp)
            item.update(verification_path=relative(vp), verification_sha256=sha(vp),
                        verification_method=verification.get("method", verification.get("check")),
                        verification_scope=verification.get("scope", verification.get("limits")))
            if verification.get("native_path"):
                native = local_path(verification["native_path"])
                item.update(native_path=relative(native), native_hash_still_matches=(native.exists() and sha(native) == verification.get("before_sha256") == verification.get("after_sha256")))
                item["verification_artifacts"] = [{"path": relative(native), "hash_matches": item["native_hash_still_matches"]}]
            elif isinstance(verification.get("hashes"), dict):
                artifacts = [{"path": relative(path), "expected_sha256": expected,
                    "hash_matches": local_path(path).exists() and sha(local_path(path)) == expected}
                    for path, expected in verification["hashes"].items()]
                item["verification_artifacts"] = artifacts
                item["native_hash_still_matches"] = bool(artifacts) and all(x["hash_matches"] for x in artifacts)
            else:
                item["native_hash_still_matches"] = None
        row = next(r for r in rows if r["task_id"] == note["task_id"])
        item["packet_path"] = row["packet_path"]
        item["raw_judge_records"] = {fam: {"status": cell["status"], "overall": cell.get("overall"),
            "assessment_path": cell.get("assessment_path"), "valid_for_comparison": cell["valid_for_comparison"]}
            for fam, cell in row["judges"].items()}
        item["secondary_completion_records"] = {fam: {"status": cell["status"], "overall": cell.get("overall"),
            "assessment_path": cell.get("assessment_path"), "valid_for_comparison": cell["valid_for_comparison"]}
            for fam, cell in row["record_repairs"].items()}
        checks.append(item)
    return checks


def trace_behavior_summary(inventory_hash):
    path = OUT / "trace-exposure-summary.json"
    if not path.exists():
        return {"status": "not_available", "matched_sets": []}
    trace = read(path)
    if trace.get("inventory_sha256") != inventory_hash:
        return {"status": "inventory_mismatch", "path": relative(path), "matched_sets": []}
    indexed = defaultdict(dict)
    for cell in trace["cells"]:
        fam = family(cell.get("model"))
        if fam and cell.get("snapshot_stable"):
            indexed[cell["task_id"]][fam] = cell

    def summarize(cells):
        stats = {}
        for name in ("read_evidence", "search_evidence", "view_image", "native_structure", "numeric_table"):
            stats[name] = {key: sum(c.get("tool_stats", {}).get(name, {}).get(key, 0) for c in cells)
                          for key in ("attempts", "successful_local_replies", "errors_or_unsupported", "replies_in_acknowledged_model_request")}
        return {"cells": len(cells), "tool_stats": stats,
            "acknowledged_view_exposures_summed_by_cell": sum(len(c.get("images", {}).get("unique_views_in_latest_acknowledged_request", [])) for c in cells),
            "cells_with_any_acknowledged_image": sum(bool(c.get("images", {}).get("unique_views_in_latest_acknowledged_request")) for c in cells),
            "artifact_views_supplied": sum(c.get("images", {}).get("available_artifact_views_supplied", 0) for c in cells),
            "available_artifact_views": sum(c.get("images", {}).get("artifact_available_view_count", 0) for c in cells),
            "image_batch_limit_errors": sum(c.get("tool_error_category_counts", {}).get("view_image:image_batch_limit", 0) for c in cells),
            "required_visual_completeness": None}

    matched = []
    for key, label in (("actual_model_final_response", "Both judges returned a genuine final model response"),
                       ("valid_primary_model_assessment", "Both judges have valid primary assessments")):
        ids = sorted(tid for tid, values in indexed.items() if all(f in values and values[f].get(key) for f in FAMILIES))
        matched.append({"selection": key, "label": label, "matched_task_count": len(ids), "task_ids": ids,
            "cohort_counts": dict(Counter(indexed[tid]["Gemini"]["rubric_format"] for tid in ids)),
            "models": {fam: summarize([indexed[tid][fam] for tid in ids]) for fam in FAMILIES}})
    return {"status": "available", "path": relative(path), "sha256": sha(path),
        "snapshot_completed_at": trace.get("snapshot_completed_at"),
        "snapshot_overall_counts": {k: trace["overall"].get(k) for k in ("planned_cells", "actual_model_final_responses", "actual_model_assessment_json_records", "valid_primary_model_assessment_records", "record_states")},
        "matched_sets": matched,
        "all_stable_cells_image_batch_limit_errors": trace["overall"].get("tool_error_category_counts", {}).get("view_image:image_batch_limit", 0),
        "interpretation": "Tool-use differences are compared on the same completed task sets, with a separate valid-record subset. Counts show execution and evidence delivery, not cognitive inspection or accuracy. The four-image-per-turn tool limit itself causes some image failures. Required visual completeness is unknown without a criterion-to-view mapping. Native recalculation and external web remain unavailable to both new judges; Astra had broader capabilities. The tax case shows that receiving the correct rule can still be followed by an incorrect pass."}


def physical_call_classification(record, response_path):
    from evaluation_v5_rejection_budget import confirmed_pre_inference_rejection
    envelope = read(response_path) if response_path.exists() else {}
    if confirmed_pre_inference_rejection(record, envelope):
        return "provider_credit_limit_pre_inference"
    status = envelope.get("status", record.get("http_status"))
    if status == 402:
        return "provider_http_402_unresolved"
    if status == 200:
        body = envelope.get("body")
        choices = body.get("choices") if isinstance(body, dict) else None
        # A model-authored malformed JSON string still has a genuine message
        # envelope. Whitespace/non-JSON HTTP bodies without choices/messages do
        # not constitute an LLM judgment, regardless of the runner's label.
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict) or not isinstance(choices[0].get("message"), dict):
            return "provider_empty_or_malformed_response"
    if record.get("status") == "response_recorded":
        return "successful_api_response"
    if status is not None:
        return "provider_http_error"
    if record.get("status") == "failed_unknown_charge":
        return "transport_error_ambiguous_charge"
    return "dispatch_pending_or_unknown"


def execution_category(result):
    status = result.get("status", "unknown_status")
    if status not in ("transport_or_runner_error", "invalid_judgment"):
        return status
    calls = result.get("calls") or []
    if calls:
        folder = ROOT / "output/evaluation_v2/calls" / calls[-1]
        rp = folder / "reservation.json"
        if rp.exists():
            category = physical_call_classification(read(rp), folder / "response.json")
            if category == "provider_empty_or_malformed_response":
                return category
            if category == "provider_credit_limit_pre_inference":
                return "provider_credit_limit"
            if category == "provider_http_402_unresolved":
                return "provider_http_402_unresolved"
            if category == "transport_error_ambiguous_charge":
                return "transport_error_ambiguous_charge"
    return status


def budget():
    from evaluation_v5_rejection_budget import make_client
    # The no-key factory cannot dispatch. It layers both verified reservation
    # amendments over the preserved ledger without reading a credential.
    client = make_client()
    records = []
    reconciliation_error = None
    with client.locked():
        for p in sorted((client.root / "calls").glob("*/reservation.json")):
            item = read(p)
            records.append({
                k: item.get(k) for k in ("id", "label", "scope", "model", "status", "actual_cost_usd", "reserved_usd", "created_at", "http_status", "served_provider", "served_model")
            } | {"reservation_path": relative(p), "reservation_sha256": sha(p),
                 "execution_category": physical_call_classification(item, p.parent / "response.json") if str(item.get("scope", "")).startswith("judge_v5") else "historical_ledger_record"})
        try:
            reconciled = client.totals()
        except Exception as error:
            reconciled = None
            reconciliation_error = f"{type(error).__name__}: {error}"

    def summarize(items):
        known = sum((Decimal(str(x["actual_cost_usd"])) for x in items if x["actual_cost_usd"] is not None), Decimal(0))
        unresolved = sum((Decimal(str(x.get("reserved_usd") or 0)) for x in items if x["actual_cost_usd"] is None), Decimal(0))
        return {"request_count": len(items), "confirmed_cost_usd": float(known),
                "unresolved_reserved_usd": float(unresolved), "committed_usd": float(known + unresolved)}

    new = [x for x in records if str(x.get("scope", "")).startswith("judge_v5")]
    old = [x for x in records if x not in new]
    raw_total = summarize(records)
    total = ({"request_count": reconciled["physical_requests"],
              "confirmed_cost_usd": reconciled["known_cost_usd"],
              "unresolved_reserved_usd": reconciled["unresolved_reserved_usd"],
              "committed_usd": reconciled["committed_usd"]} if reconciled else raw_total)
    by_model = defaultdict(list)
    for x in new:
        by_model[x["model"]].append(x)
    new_raw = summarize(new)
    new_effective = dict(new_raw)
    if reconciled:
        new_effective["unresolved_reserved_usd"] = round(new_raw["unresolved_reserved_usd"] - reconciled["provider_pre_inference_released_reservation_usd"], 10)
        new_effective["committed_usd"] = round(new_effective["confirmed_cost_usd"] + new_effective["unresolved_reserved_usd"], 10)
    released_ids = {x["id"] for x in read(ROOT / "config/evaluation_v5_provider_rejection_reconciliation.json")["rejected_requests"]}
    unreleased_rejections = [x for x in new if x["execution_category"] == "provider_credit_limit_pre_inference" and x["actual_cost_usd"] is None and x["id"] not in released_ids]
    unreleased_rejection_reserves = sum(float(x.get("reserved_usd") or 0) for x in unreleased_rejections)
    return {
        "api_limit_usd": 30, "total_shared_evaluation_ledger": total,
        "raw_total_shared_evaluation_ledger": raw_total,
        "effective_total_shared_evaluation_ledger": total if reconciled else None,
        "before_this_crossjudge_extension": summarize(old), "this_extension": new_raw,
        "this_extension_effective": new_effective if reconciled else None,
        "this_extension_by_requested_model": {k: summarize(v) for k, v in sorted(by_model.items())},
        "headroom_usd": 30 - total["committed_usd"], "within_limit": bool(reconciled) and total["committed_usd"] <= 30 + 1e-9,
        "budget_reconciliation_path": "config/evaluation_v5_budget_reconciliation.json",
        "budget_reconciliation_sha256": sha(ROOT / "config/evaluation_v5_budget_reconciliation.json"),
        "reconciliation_verified": reconciled is not None, "reconciliation_error": reconciliation_error,
        "aggregate_released_reservation_usd": reconciled["aggregate_released_reservation_usd"] if reconciled else None,
        "retained_historical_delayed_billing_contingency_usd": reconciled["historical_delayed_billing_contingency_usd"] if reconciled else None,
        "provider_pre_inference_released_reservation_usd": reconciled["provider_pre_inference_released_reservation_usd"] if reconciled else None,
        "confirmed_pre_inference_rejection_count": reconciled["confirmed_pre_inference_rejection_count"] if reconciled else None,
        "provider_rejection_reconciliation_path": "config/evaluation_v5_provider_rejection_reconciliation.json",
        "provider_rejection_reconciliation_sha256": sha(ROOT / "config/evaluation_v5_provider_rejection_reconciliation.json"),
        "verified_pre_inference_rejections_still_reserved": {"request_count": len(unreleased_rejections), "reserved_usd": unreleased_rejection_reserves, "request_ids": [x["id"] for x in unreleased_rejections]},
        "other_retained_uncertainty_and_historical_contingency_usd": round(total["unresolved_reserved_usd"] - unreleased_rejection_reserves, 10) if reconciled else None,
        "new_request_scope_filter": "scope starts with judge_v5",
        "new_requests": new, "in_app_inference_cost_usd": None,
        "interpretation": "The raw ledger is preserved. One dated amendment replaces the eight historical calls' aggregate reservation with a USD0.50 contingency. A second releases only 57 immutable, positively evidenced HTTP402 rejections before upstream inference. Individual raw costs remain null, not rewritten to zero. Other ambiguous calls retain their reservations, and future rejections are not automatically released. Effective totals use the same keyless reconciliation factory as the serial runner. In-app inference cost remains unavailable. Separate study_v3 and unrelated v5 development costs are not silently attributed to this extension.",
    }


def pair_stats(rows, left, right, cohort=None):
    from evaluation_v5_pair_metrics import paired_agreement
    task_matrix = {a: {b: 0 for b in ("pass", "fail", "uncertain")} for a in ("pass", "fail", "uncertain")}
    criterion_matrix = {a: {b: 0 for b in VERDICTS} for a in VERDICTS}
    paired_tasks, criterion_pairs, disagreements, metrics_input = [], 0, [], []
    for row in rows:
        if cohort is not None and row["rubric_format"] != cohort:
            continue
        a, b = row["judges"][left], row["judges"][right]
        if not (a.get("valid_for_comparison") and b.get("valid_for_comparison")):
            continue
        paired_tasks.append(row["task_id"])
        task_matrix[a["overall"]][b["overall"]] += 1
        ca = {c["criterion_id"]: c for c in a["criteria"]}
        cb = {c["criterion_id"]: c for c in b["criteria"]}
        metrics_input.append({"task_id": row["task_id"], "left_overall": a["overall"], "right_overall": b["overall"],
                              "criteria": [{"criterion_id": cid, "left": ca[cid]["verdict"], "right": cb[cid]["verdict"]} for cid in sorted(ca.keys() & cb.keys())]})
        for cid in sorted(ca.keys() & cb.keys()):
            va, vb = ca[cid]["verdict"], cb[cid]["verdict"]
            criterion_matrix[va][vb] += 1
            criterion_pairs += 1
            if va != vb:
                disagreements.append({"task_id": row["task_id"], "rubric_format": row["rubric_format"],
                    "criterion_id": cid, "left": evidence_summary(ca[cid]), "right": evidence_summary(cb[cid]),
                    "left_assessment": a["assessment_path"], "right_assessment": b["assessment_path"],
                    "interpretation": "Disagreement requiring evidence review; neither side is automatically correct."})
    same_tasks = sum(task_matrix[v][v] for v in task_matrix)
    same_criteria = sum(criterion_matrix[v][v] for v in criterion_matrix)
    diagnostics = paired_agreement(metrics_input, bootstrap_samples=2000, seed=20261105, min_tasks_for_ci=10)
    return {
        "left": left, "right": right, "cohort": cohort or "all_descriptive_only",
        "paired_task_count": len(paired_tasks), "paired_task_ids": paired_tasks,
        "task_agreement_count": same_tasks, "task_agreement_rate": same_tasks / len(paired_tasks) if paired_tasks else None,
        "task_confusion_matrix": task_matrix, "paired_criterion_count": criterion_pairs,
        "criterion_agreement_count": same_criteria,
        "criterion_agreement_rate": same_criteria / criterion_pairs if criterion_pairs else None,
        "criterion_confusion_matrix": criterion_matrix, "disagreements": disagreements,
        "accuracy": None, "agreement_diagnostics": diagnostics,
        "cohens_kappa": diagnostics["task_overall"]["cohens_kappa"],
        "fail_positive_agreement": diagnostics["task_overall"]["fail_positive_agreement"],
        "confidence_intervals": diagnostics["intervals"],
        "interpretation": "Descriptive paired agreement only; different evidence/capabilities may explain differences. Criteria within tasks are not independent observations. No judge ranking or accuracy claim.",
    }


def build(inventory_path):
    inv = read(inventory_path)
    tasks = inv["tasks"]
    if len({t["task_id"] for t in tasks}) != len(tasks):
        raise ValueError("duplicate inventory task")
    validations = {}
    for cohort in ("v3", "v4"):
        p = ROOT / f"output/evaluation_{cohort}/assessments/validation.json"
        if p.exists():
            validations.update({x["task_id"]: x for x in read(p)["checks"]})

    result_index = defaultdict(list)
    unexpected_results = []
    tids = {x["task_id"] for x in tasks}
    for p in sorted((OUT / "judges").glob("*/result.json")):
        data = read(p)
        fam = family(data.get("judge_requested_model"))
        if fam and data.get("task_id") in tids:
            result_index[(data["task_id"], fam)].append((p, data))
        else:
            unexpected_results.append(relative(p))

    rows = []
    all_errors = []
    for task in tasks:
        packet_path = local_path(task["packet_path"])
        packet = read(packet_path)
        packet_ok = sha(packet_path) == task["packet_sha256"]
        row = {k: task[k] for k in ("task_id", "occupation", "cohort", "rubric_format", "criteria_count", "artifact_hashes")}
        row.update(title=packet.get("rubric", {}).get("title", task["task_id"]),
                   packet_path=relative(packet_path), packet_sha256=task["packet_sha256"],
                   packet_integrity_verified=packet_ok, judges={})
        row["frozen_criteria"] = [{
            "criterion_id": c.get("criterion_id", c.get("id")),
            "title": c.get("title", c.get("criterion", "Criterion")),
            "requirement_text": c.get("criterion") or c.get("pass_condition") or " ".join(x.get("pass_condition", "") for x in c.get("checks", [])),
            "source_requirements": c.get("requirements", []), "source_anchor": c.get("source_anchor")
        } for c in packet["criteria"]]
        row["native_artifacts"] = [{"id": a["id"], "path": relative(a["native_path"]), "sha256": a["sha256"], "kind": a.get("kind")} for a in packet["artifacts"]]
        if not packet_ok:
            all_errors.append(f"{task['task_id']}: packet hash differs from inventory")
        baseline = task["astra_baseline"]
        basecell = {"status": "baseline_missing", "valid_for_comparison": False, "overall": None, "criteria": []}
        if baseline["available"]:
            bp = local_path(baseline["path"])
            a = safe_assessment(read(bp))
            errors = check_record(a, task, packet)
            if sha(bp) != baseline["sha256"]:
                errors.append("baseline hash changed")
            if validations.get(task["task_id"], {}).get("contract_valid") is not True:
                errors.append("baseline lacks a passing original contract validation")
            valid = packet_ok and not errors
            basecell = {"status": "existing_valid" if valid else "baseline_not_comparable",
                        "valid_for_comparison": valid, "overall": aggregate(a["criteria"]) if valid else None,
                        "reported_overall": a.get("overall"), "criteria": a.get("criteria", []),
                        "requested_model": a.get("reviewer_requested_model"), "assessment_path": relative(bp),
                        "assessment_sha256": sha(bp), "analysis_integrity_problems": errors,
                        "capability_note": baseline.get("comparison_limit")}
        row["judges"]["Astra"] = basecell

        for fam in FAMILIES:
            candidates = result_index.get((task["task_id"], fam), [])
            cell = {"status": "not_run", "valid_for_comparison": False, "overall": None, "criteria": []}
            if len(candidates) > 1:
                cell.update(status="ambiguous_multiple_model_versions", result_paths=[relative(x[0]) for x in candidates])
                all_errors.append(f"{task['task_id']}: multiple {fam} result directories require an explicit selection")
            elif candidates:
                rp, result = candidates[0]
                cell.update(status=execution_category(result), runner_status=result.get("status"), requested_model=result.get("judge_requested_model"),
                            result_path=relative(rp), reported_overall=result.get("overall"),
                            packet_sha256=result.get("packet_sha256"), rubric_sha256=result.get("rubric_sha256"),
                            served_models=result.get("served_models", []), served_providers=result.get("served_providers", []),
                            calls=result.get("calls"), coverage=result.get("coverage"),
                            evidence_exposure_path=result.get("evidence_exposure_path"),
                            validation_path=result.get("validation_path"), contract_valid=result.get("contract_valid"))
                archived = OUT / "serial-recovery" / rp.parent.name / "before/result.json"
                initial_result = read(archived) if archived.exists() else result
                cell["initial_batch_execution"] = {
                    "status": execution_category(initial_result), "runner_status": initial_result.get("status"),
                    "record_path": relative(archived if archived.exists() else rp),
                    "archived_before_serial_recovery": archived.exists(), "calls": initial_result.get("calls", [])}
                cell["serial_recovery_receipt"] = result.get("serial_recovery_receipt")
                final_path = rp.parent / "final-response.json"
                cell["final_response_artifact_present"] = final_path.exists()
                genuine_final = False
                if final_path.exists():
                    final_record = read(final_path)
                    final_call = final_record.get("call_id")
                    call_folder = ROOT / "output/evaluation_v2/calls" / str(final_call)
                    call_record_path = call_folder / "reservation.json"
                    if call_record_path.exists():
                        genuine_final = physical_call_classification(read(call_record_path), call_folder / "response.json") == "successful_api_response"
                cell["final_model_response_recorded"] = genuine_final
                if cell["status"] == "provider_empty_or_malformed_response":
                    cell["execution_classification_note"] = "Raw runner status is preserved as invalid_judgment, but the last HTTP200 body has no usable model message envelope. This is a provider-response failure, not a model-authored schema error; its ambiguous cost reserve remains retained."
                ap = local_path(result["assessment_path"]) if result.get("assessment_path") else rp.parent / "assessment.json"
                if ap.exists():
                    a = safe_assessment(read(ap))
                    errors = check_record(a, task, packet)
                    if result.get("packet_sha256") != task["packet_sha256"]:
                        errors.append("runner packet hash does not match inventory")
                    if result.get("rubric_sha256") != packet.get("rubric_sha256"):
                        errors.append("runner rubric hash does not match packet")
                    if result.get("status") != "graded":
                        errors.append("runner did not classify assessment as graded")
                    vp = local_path(result["validation_path"]) if result.get("validation_path") else rp.parent / "validation.json"
                    validation = read(vp) if vp.exists() else {}
                    if result.get("contract_valid") is not True or validation.get("contract_valid") is not True:
                        errors.append("runner result and validation file must both establish contract validity")
                    cell["validation_summary"] = {k: validation.get(k) for k in ("contract_valid", "contract_errors", "provenance_flags")}
                    cell["criterion_record_diagnostics"] = criterion_record_diagnostics(a, validation)
                    valid = packet_ok and not errors
                    cell.update(valid_for_comparison=valid, overall=aggregate(a["criteria"]) if valid else None,
                                criteria=a.get("criteria", []), assessment_path=relative(ap), assessment_sha256=sha(ap),
                                analysis_integrity_problems=errors)
                    if result.get("status") == "graded" and errors:
                        cell["status"] = "analysis_integrity_failure"
                        all_errors.extend(f"{task['task_id']} {fam}: {x}" for x in errors)
                elif result.get("status") == "graded":
                    cell["status"] = "analysis_integrity_failure"
                    all_errors.append(f"{task['task_id']} {fam}: graded result has no assessment")
            row["judges"][fam] = cell

        hp = ROOT / "output/evaluation_v4/human-reviews" / (task["task_id"] + ".json")
        row["existing_human_review"] = None
        if hp.exists():
            h = read(hp)
            if h.get("status") == "complete":
                row["existing_human_review"] = {"path": relative(hp), "human_acceptance": h.get("human_acceptance"),
                    "scope": h.get("review_scope"), "expert_validation": h.get("expert_validation", False),
                    "blind_calibration_label": h.get("blind_calibration_label", False), "minutes": h.get("review_minutes"),
                    "criterion_id": h.get("criterion_review", {}).get("criterion_id"),
                    "user_classification": h.get("criterion_review", {}).get("user_classification")}
        row["record_repairs"] = load_repair(row, task, packet)
        rows.append(row)

    model_summary = {}
    for fam in ("Astra", *FAMILIES):
        cells = [r["judges"][fam] for r in rows]
        valid = [c for c in cells if c["valid_for_comparison"]]
        model_summary[fam] = {"selected_tasks": len(tasks), "valid_assessments": len(valid),
            "status_counts": dict(Counter(c["status"] for c in cells)),
            "task_verdict_counts": dict(Counter(c["overall"] for c in valid)),
            "criterion_verdict_counts": dict(Counter(x["verdict"] for c in valid for x in c["criteria"])),
            "requested_models": dict(Counter(c.get("requested_model") for c in cells if c.get("requested_model"))),
            "per_cohort": {co: {"tasks": sum(r["rubric_format"] == co for r in rows),
                "valid_assessments": sum(r["rubric_format"] == co and r["judges"][fam]["valid_for_comparison"] for r in rows),
                "task_verdict_counts": dict(Counter(r["judges"][fam]["overall"] for r in rows if r["rubric_format"] == co and r["judges"][fam]["valid_for_comparison"]))}
                for co in ("v2", "v3", "v4")}}
        invalid_with_records = [c for c in cells if c.get("criteria") and not c["valid_for_comparison"]]
        segments = [x for c in invalid_with_records for x in c.get("criterion_record_diagnostics", [])]
        model_summary[fam]["invalid_record_diagnostics"] = {
            "invalid_assessments_with_retained_criteria": len(invalid_with_records),
            "raw_criterion_verdict_counts": dict(Counter(x["verdict"] for c in invalid_with_records for x in c["criteria"])),
            "criterion_records_with_diagnostics": len(segments),
            "criterion_contract_valid_records": sum(x["criterion_contract_valid"] for x in segments),
            "criterion_contract_invalid_records": sum(not x["criterion_contract_valid"] for x in segments),
            "text_verified_quote_records": sum(x["text_verified_quote_records"] for x in segments),
            "interpretation": "Raw verdicts and structurally usable segments are retained descriptively, not included in primary valid-assessment paired statistics. Missing source quotations are a grader-record defect, not proof of a business error in the deliverable.",
        }
    comparisons = []
    for left, right in (("Astra", "Gemini"), ("Astra", "Claude"), ("Gemini", "Claude")):
        comparisons.append(pair_stats(rows, left, right))
        comparisons.extend(pair_stats(rows, left, right, co) for co in ("v2", "v3", "v4"))
    valid_new = sum(model_summary[f]["valid_assessments"] for f in FAMILIES)
    repaired_rows = []
    repair_summary = {}
    for row in rows:
        revised = dict(row)
        revised["judges"] = dict(row["judges"])
        for fam in FAMILIES:
            if not row["judges"][fam]["valid_for_comparison"] and row["record_repairs"][fam]["valid_for_comparison"]:
                revised["judges"][fam] = row["record_repairs"][fam]
        repaired_rows.append(revised)
    for fam in FAMILIES:
        repairs = [r["record_repairs"][fam] for r in rows]
        repair_summary[fam] = {"status_counts": dict(Counter(x["status"] for x in repairs)),
            "valid_repaired_assessments": sum(x["valid_for_comparison"] for x in repairs),
            "recorded_verdict_flips": sum(x.get("changes", {}).get("verdict_flip_count", 0) for x in repairs),
            "valid_unique_assessments_after_completion": sum(r["judges"][fam]["valid_for_comparison"] for r in repaired_rows)}
    after_completion = sum(x["valid_unique_assessments_after_completion"] for x in repair_summary.values())
    repair_comparisons = []
    for left, right in (("Astra", "Gemini"), ("Astra", "Claude"), ("Gemini", "Claude")):
        repair_comparisons.append(pair_stats(repaired_rows, left, right))
        repair_comparisons.extend(pair_stats(repaired_rows, left, right, co) for co in ("v2", "v3", "v4"))
    complete_humans = [r["existing_human_review"] for r in rows if r["existing_human_review"]]
    cost = budget()
    new_cells = [r["judges"][fam] for r in rows for fam in FAMILIES]
    initial_by_cell = defaultdict(list)
    for request in cost["new_requests"]:
        if request["scope"] == "judge_v5_crossfamily":
            label = str(request.get("label", ""))
            if label.startswith("v5:") and ":turn" in label:
                initial_by_cell[label.split(":turn", 1)[0]].append(request)
    first_requests = [min(v, key=lambda x: x.get("created_at") or "") for v in initial_by_cell.values()]
    execution_history = {
        "requested_task_judge_cells": 2 * len(tasks),
        "cells_with_physical_api_attempts": sum(bool(c.get("calls")) for c in new_cells),
        "cells_with_final_model_response_record": sum(bool(c.get("final_model_response_recorded")) for c in new_cells),
        "cells_with_parseable_assessment_records": sum(bool(c.get("assessment_path")) for c in new_cells),
        "current_execution_category_counts": dict(Counter(c["status"] for c in new_cells)),
        "initial_batch_execution_category_counts": dict(Counter(c.get("initial_batch_execution", {}).get("status", "not_run") for c in new_cells)),
        "physical_request_category_counts": dict(Counter(r["execution_category"] for r in cost["new_requests"])),
        "first_physical_request_per_cell_category_counts": dict(Counter(r["execution_category"] for r in first_requests)),
        "serially_recovered_or_recovering_cells": sum(bool(c.get("serial_recovery_receipt")) for c in new_cells),
        "interpretation": "A physical HTTP request, an attempted task/judge cell and a completed model assessment are distinct denominators. Provider credit-limit rejections and HTTP200 bodies without a usable model-message envelope are infrastructure/provider events, not model reviews or business failures. A null final-response placeholder is excluded from final model-response counts. Genuine model-authored malformed JSON remains a grader-record failure. Current results may improve after explicit serial continuation; archived initial outcomes and immutable request records preserve the original failures.",
    }
    execution_status_path = OUT / "execution-status.json"
    execution_status = read(execution_status_path) if execution_status_path.exists() else {}
    coverage_status = "completed_requested_coverage" if valid_new == 2 * len(tasks) and not all_errors else execution_status.get("status", "incomplete_requested_coverage")
    return {
        "schema": "evaluation-v5-crossjudge-analysis-1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "inventory_path": relative(inventory_path), "inventory_sha256": sha(inventory_path),
        "status": coverage_status, "execution_status": execution_status,
        "execution_status_path": relative(execution_status_path) if execution_status_path.exists() else None,
        "selected_original_tasks": len(tasks), "requested_new_assessments": 2 * len(tasks),
        "valid_new_assessments": valid_new, "uncompleted_or_invalid_new_assessments": 2 * len(tasks) - valid_new,
        "astra_baselines_available": sum(t["astra_baseline"]["available"] for t in tasks),
        "astra_baselines_missing": sum(not t["astra_baseline"]["available"] for t in tasks),
        "cohort_counts": dict(Counter(t["rubric_format"] for t in tasks)), "models": model_summary,
        "comparisons": comparisons, "tasks": rows, "costs": cost, "execution_history": execution_history,
        "trace_exposure_summary_path": "output/evaluation_v5/trace-exposure-summary.json" if (OUT / "trace-exposure-summary.json").exists() else None,
        "inspection_behavior": trace_behavior_summary(sha(inventory_path)),
        "record_completion": {"models": repair_summary, "valid_unique_new_assessments_after_completion": after_completion,
            "coverage_status": "complete" if after_completion == 2 * len(tasks) else "incomplete",
            "secondary_comparisons": repair_comparisons,
            "execution_note": execution_status.get("record_completion_note", "No record-completion execution is inferred without result records."),
            "interpretation": "Secondary accounting retains valid first-pass records and substitutes a validated record-completion response only where the first assessment was invalid. These repairs are dependent, post hoc responses, not independent replications. First-pass records, counts and comparisons remain unchanged; changed verdicts are disclosed separately."},
        "scoped_human_review_comparisons": scoped_human_comparisons(rows),
        "assistant_evidence_checks": assistant_evidence_checks(rows),
        "existing_human_reviews": {"completed": len(complete_humans), "expert_validated": sum(bool(x["expert_validation"]) for x in complete_humans),
            "blind_calibration_labels": sum(bool(x["blind_calibration_label"]) for x in complete_humans),
            "use": "Selected diagnostic evidence only; no representative judge-accuracy denominator."},
        "expert_acceptance_rate": None, "judge_accuracy": None, "false_accept_rate": None, "model_ranking": None,
        "ensemble_verdict": None, "construct_validity": {"status": "proposed_not_executed", "S": None, "R": None,
            "protocol_path": "docs/evaluation_v5/research-and-construct-validity.txt",
            "primary_source": "https://arxiv.org/html/2608.24419v1",
            "application": "Keep meaning-preserving controls separate from changes to a required condition. Confirm intended direction with humans, test the targeted criterion, and report invariance and sensitivity separately. Agreement among three judges supplies neither result.",
            "source_corrections": "The pasted summary misnames Claude Haiku 4.5 and presents predicted accuracy-pressure effects as measured. The source-checked note records these corrections."},
        "limitations": LIMITATIONS, "analysis_integrity_problems": all_errors, "unexpected_result_paths": unexpected_results,
    }


def render_text(data):
    lines = ["Cross-family judging extension — current execution record", "",
        f"Status: {data['status']}",
        f"Selected original tasks: {data['selected_original_tasks']}; requested new assessments: {data['requested_new_assessments']} (Gemini and Claude).",
        f"Valid new assessments: {data['valid_new_assessments']}; incomplete/invalid: {data['uncompleted_or_invalid_new_assessments']}.",
        f"Existing Astra baselines: {data['astra_baselines_available']}; missing: {data['astra_baselines_missing']}.",
        "No solver output was regenerated for this extension. Missing grades are not passes or failures.", ""]
    history = data["execution_history"]
    if data.get("execution_status", {}).get("stop_reason"):
        lines += ["Execution stop: " + data["execution_status"]["stop_reason"],
                  "The project API ceiling has not been raised. A provider limit is separate from the remaining project budget.", ""]
    lines += [f"Attempted task/judge cells: {history['cells_with_physical_api_attempts']}; cells with a final model response: {history['cells_with_final_model_response_record']}; cells with a parseable assessment: {history['cells_with_parseable_assessment_records']}.",
        f"Initial batch execution categories: {history['initial_batch_execution_category_counts']}",
        f"Current execution categories: {history['current_execution_category_counts']}",
        f"All physical API-request categories: {history['physical_request_category_counts']}",
        "An HTTP402 before inference is a provider credit-limit rejection, not a completed model review. Serial continuation preserves the initial archived outcomes.", ""]
    for fam, m in data["models"].items():
        lines.append(f"{fam}: {m['valid_assessments']} valid assessments; states {m['status_counts']}; outcomes {m['task_verdict_counts']}.")
        for co, v in m["per_cohort"].items():
            lines.append(f"  {co}: {v['valid_assessments']}/{v['tasks']} valid; {v['task_verdict_counts']}")
        diag = m["invalid_record_diagnostics"]
        if diag["invalid_assessments_with_retained_criteria"]:
            lines.append(f"  Invalid-record diagnostics only: {diag['invalid_assessments_with_retained_criteria']} assessments retain {diag['criterion_records_with_diagnostics']} criterion records; {diag['criterion_contract_valid_records']} meet criterion structural checks, {diag['criterion_contract_invalid_records']} do not. Raw verdicts {diag['raw_criterion_verdict_counts']}; excluded from primary paired statistics.")
    lines += ["", "Record completion is secondary, not an independent regrade:",
        f"Unique valid new assessments after any recorded completion: {data['record_completion']['valid_unique_new_assessments_after_completion']}/{data['requested_new_assessments']}."]
    for fam, repair in data["record_completion"]["models"].items():
        lines.append(f"{fam}: {repair['valid_repaired_assessments']} validated completion records; {repair['recorded_verdict_flips']} recorded criterion-verdict changes. First-pass counts above remain unchanged.")
    lines.append(data["record_completion"]["execution_note"])
    lines += ["", "Scoped human diagnostic comparisons (not expert accuracy):"]
    for case in data["scoped_human_review_comparisons"]:
        lines.append(f"{case['task_id']} {case['criterion_id']}: user={case['human_classification']}. Scope: {case['human_scope']}")
        for judge, finding in case["judge_findings"].items():
            lines.append(f"  {judge}: {finding.get('raw_verdict') or finding['status']}; full assessment valid={finding.get('assessment_contract_valid')}. Match the specific reason to the reviewed issue before inferring agreement.")
    lines += ["", "Assistant evidence checks (not human reviews or replacement grades):"]
    for note in data["assistant_evidence_checks"]:
        lines += [f"{note['task_id']}: {note.get('title')}",
            "Original requirement (analyst summary): " + str(note.get("original_requirement")),
            "Method: " + str(note.get("verification_method")),
            "Scope: " + str(note.get("verification_scope"))]
        for finding in note.get("observed_evidence", []):
            lines.append(f"  {finding.get('location')}: {finding.get('quote', finding.get('finding'))}")
        lines += ["First-pass judge observation: " + str(note.get("first_pass_judge_observation")),
            "Interpretation: " + str(note.get("interpretation")), "Causal limit: " + str(note.get("causal_limit")),
            "Data hypothesis: " + str(note.get("data_hypothesis")),
            "Evidence: " + str(note.get("verification_path")), "Interpretation record: " + note["interpretation_path"],
            "No human acceptance or expert validation is added by this assistant check."]
        if note.get("prior_human_review_path"):
            lines.append("Previously recorded scoped user review (not a new label): " + note["prior_human_review_path"])
    lines += ["", "Paired descriptive comparisons (agreement, not accuracy):"]
    for p in data["comparisons"]:
        if p["cohort"] == "all_descriptive_only":
            lines.append(f"{p['left']} vs {p['right']}: {p['task_agreement_count']}/{p['paired_task_count']} task agreements; {p['criterion_agreement_count']}/{p['paired_criterion_count']} criterion agreements; {len(p['disagreements'])} criterion disagreements.")
            metric = p["agreement_diagnostics"]["task_overall"]
            lines.append(f"  Task Cohen's kappa={metric['cohens_kappa']}; fail-positive agreement={metric['fail_positive_agreement']} on {metric['decided_binary_pairs']} jointly decided pairs, excluding {metric['uncertain_or_not_assessed_pairs_excluded_from_binary']} uncertain pairs. Intervals: {p['confidence_intervals']['task_raw_agreement']['ci_status']}. These are agreement diagnostics, not accuracy.")
    behavior = data["inspection_behavior"]
    if behavior.get("status") == "available":
        lines += ["", "Inspection behavior snapshot: " + str(behavior["snapshot_completed_at"])]
        for match in behavior["matched_sets"]:
            lines.append(f"{match['label']}: {match['matched_task_count']} matched tasks.")
            for fam, value in match["models"].items():
                lines.append(f"  {fam}: {value['acknowledged_view_exposures_summed_by_cell']} distinct view exposures summed by task; {value['tool_stats']['native_structure']['attempts']} native-structure attempts; {value['tool_stats']['numeric_table']['attempts']} saved-cell calculation attempts; {value['image_batch_limit_errors']} image-cap errors.")
        lines.append(f"Across the snapshot, {behavior['all_stable_cells_image_batch_limit_errors']} image requests hit the four-image batch limit. Tool counts do not establish accuracy; the tax judge retrieved the correct rule and still passed the wrong calculation.")
        lines.append(behavior["interpretation"])
    c = data["costs"]
    effective_new = c.get("this_extension_effective")
    effective_extension_text = (
        f"Effective extension-only commitment: ${effective_new['committed_usd']:.6f}, including ${effective_new['confirmed_cost_usd']:.6f} confirmed charges and ${effective_new['unresolved_reserved_usd']:.6f} retained reservations. Commitment is not all confirmed spending."
        if effective_new else "Effective extension-only commitment is unavailable because reconciliation verification failed."
    )
    lines += ["", "API cost and remaining limit:",
        f"This extension: {c['this_extension']['request_count']} physical request records; confirmed ${c['this_extension']['confirmed_cost_usd']:.6f}; raw unresolved reservations before reviewed releases ${c['this_extension']['unresolved_reserved_usd']:.6f}.",
        effective_extension_text,
        f"Raw shared ledger (preserved): confirmed ${c['raw_total_shared_evaluation_ledger']['confirmed_cost_usd']:.6f}; unresolved reserve ${c['raw_total_shared_evaluation_ledger']['unresolved_reserved_usd']:.6f}; unadjusted commitment ${c['raw_total_shared_evaluation_ledger']['committed_usd']:.6f}.",
        f"Effective commitment after verified aggregate reconciliation: ${c['total_shared_evaluation_ledger']['committed_usd']:.6f}; headroom ${c['headroom_usd']:.6f} under $30.",
        f"Historical reservation released: ${c['aggregate_released_reservation_usd']}; retained delayed-billing contingency: ${c['retained_historical_delayed_billing_contingency_usd']}. Individual unknown charges remain unknown, not zero.",
        f"Positively evidenced pre-inference rejections: {c['confirmed_pre_inference_rejection_count']}; additional released reservations: ${c['provider_pre_inference_released_reservation_usd']}.",
        f"Still-retained reserves include ${c['verified_pre_inference_rejections_still_reserved']['reserved_usd']:.6f} for {c['verified_pre_inference_rejections_still_reserved']['request_count']} later verified pre-inference rejections that have not been released, plus ${c['other_retained_uncertainty_and_historical_contingency_usd']:.6f} for ambiguous charges and the historical contingency.",
        "Amendments: config/evaluation_v5_budget_reconciliation.json and config/evaluation_v5_provider_rejection_reconciliation.json. Other ambiguous calls retain their full reservations; future rejections are not automatically released. App inference cost remains unknown. Separate study costs are not attributed to this extension.", "", "Limits:"]
    lines.extend("- " + x for x in data["limitations"])
    lines += ["", "Research-informed improvement:", data["construct_validity"]["application"],
              "Construct probes: proposed, not executed; S and R remain unmeasured.",
              "Source and corrections: docs/evaluation_v5/research-and-construct-validity.txt", "", "Task matrix:"]
    for r in data["tasks"]:
        labels = [f"{fam}={r['judges'][fam]['overall'] or r['judges'][fam]['status']}" for fam in ("Astra", *FAMILIES)]
        lines.append(f"{r['task_id']} [{r['rubric_format']}] " + "; ".join(labels))
    if data["analysis_integrity_problems"]:
        lines += ["", "Analysis integrity problems:"] + data["analysis_integrity_problems"]
    return "\n".join(lines) + "\n"


def render_html(data):
    e = lambda x: html.escape(str(x))
    def link(path, label):
        return f'<a href="{e(os.path.relpath(ROOT / path, OUT))}">{e(label)}</a>'
    cards = "".join(f'<div class="card"><b>{e(v)}</b><span>{e(k)}</span></div>' for k, v in [
        ("Original tasks", data["selected_original_tasks"]), ("Requested new reviews", data["requested_new_assessments"]),
        ("Valid first-pass reviews", data["valid_new_assessments"]), ("Existing Astra baselines", data["astra_baselines_available"])])
    table = []
    for row in data["tasks"]:
        cells = []
        for fam in ("Astra", *FAMILIES):
            c = row["judges"][fam]
            label = c["overall"] or c["status"].replace("_", " ")
            text = link(c["assessment_path"], label) if c.get("assessment_path") else e(label)
            cells.append(f'<td>{text}</td>')
        table.append(f'<tr><td>{e(row["title"])}<small>{e(row["task_id"])}</small></td><td>{e(row["rubric_format"])}</td>{"".join(cells)}</tr>')
    comparisons = []
    fmt_metric = lambda value: "undefined" if value is None else f"{value:.3f}"
    for p in data["comparisons"]:
        if p["cohort"] != "all_descriptive_only":
            continue
        comparisons.append(f'<p><b>{e(p["left"])} / {e(p["right"])}</b>: {p["task_agreement_count"]}/{p["paired_task_count"]} task agreements; {p["criterion_agreement_count"]}/{p["paired_criterion_count"]} criterion agreements.</p>')
        metric = p["agreement_diagnostics"]["task_overall"]
        interval = p["confidence_intervals"]["task_raw_agreement"]
        interval_text = ("Not estimated: fewer than ten paired tasks." if interval["ci_status"] == "too_few_matched_tasks" else
                         "Undefined for this matched set." if interval["ci_status"] == "undefined_point_estimate" else
                         str(interval.get("ci95")) + " (whole-task bootstrap; exploratory selected sample).")
        comparisons.append(f'<p><small>Task κ: {fmt_metric(metric["cohens_kappa"])}. Agreement on a fail flag: {fmt_metric(metric["fail_positive_agreement"])} among {metric["decided_binary_pairs"]} jointly decided pass/fail pairs; {metric["uncertain_or_not_assessed_pairs_excluded_from_binary"]} uncertain pairs excluded from that binary statistic. Interval: {e(interval_text)} These are agreement measures, not error-detection accuracy.</small></p>')
        for d in p["disagreements"]:
            comparisons.append(f'<details><summary>{e(d["task_id"])} · {e(d["criterion_id"])}: {e(d["left"]["verdict"])} / {e(d["right"]["verdict"])}</summary><p>{link(d["left_assessment"],p["left"])}: {e(d["left"].get("reason"))}</p><p>{link(d["right_assessment"],p["right"])}: {e(d["right"].get("reason"))}</p><p>Unresolved disagreement; inspect the original requirement and evidence.</p></details>')
    c = data["costs"]
    limits = "".join(f"<li>{e(x)}</li>" for x in data["limitations"])
    raw = c["raw_total_shared_evaluation_ledger"]
    costnote = f'<p>The preserved raw ledger has ${raw["confirmed_cost_usd"]:.6f} confirmed charges and ${raw["unresolved_reserved_usd"]:.6f} unresolved reservations (${raw["committed_usd"]:.6f} before adjustment). A dated {link(c["budget_reconciliation_path"], "historical billing amendment")} releases ${c["aggregate_released_reservation_usd"]} of historical reservations and retains ${c["retained_historical_delayed_billing_contingency_usd"]} for delayed billing. A separate {link(c["provider_rejection_reconciliation_path"], "pre-inference rejection amendment")} releases ${c["provider_pre_inference_released_reservation_usd"]} for {c["confirmed_pre_inference_rejection_count"]} positively evidenced provider rejections. Individual raw unknown costs remain null, not rewritten as zero. Other ambiguous charges retain their full reservations; future rejections are not automatically released.</p>'
    effective_new = c.get("this_extension_effective")
    if effective_new:
        costnote += f'<p><b>Effective extension-only commitment:</b> ${effective_new["committed_usd"]:.6f}, comprising ${effective_new["confirmed_cost_usd"]:.6f} confirmed charges plus ${effective_new["unresolved_reserved_usd"]:.6f} retained reservations. A commitment is not all confirmed spending.</p>'
    pending_rejections = c["verified_pre_inference_rejections_still_reserved"]
    costnote += f'<p>The total retained reserve includes ${pending_rejections["reserved_usd"]:.6f} for {pending_rejections["request_count"]} later verified pre-inference rejections that have not been released, plus ${c["other_retained_uncertainty_and_historical_contingency_usd"]:.6f} for ambiguous charges and the historical contingency.</p>'
    history = data["execution_history"]
    history_html = f'<h2>Execution coverage</h2><p>{history["cells_with_physical_api_attempts"]} task/judge cells have physical request attempts; {history["cells_with_final_model_response_record"]} have a final model response and {history["cells_with_parseable_assessment_records"]} have a parseable assessment. These are different denominators. A provider credit-limit rejection before inference is not a model review or a business failure.</p><p><b>Initial batch:</b> {e(history["initial_batch_execution_category_counts"])}.</p><p><b>Current state after any serial continuation:</b> {e(history["current_execution_category_counts"])}.</p><p><b>All physical API requests:</b> {e(history["physical_request_category_counts"])}. Archived initial outcomes and raw call records remain available.</p>'
    if data.get("trace_exposure_summary_path"):
        history_html += f'<p>{link(data["trace_exposure_summary_path"], "Tool and evidence exposure summary")}</p>'
    if data.get("execution_status", {}).get("stop_reason"):
        history_html += f'<p class="note">{e(data["execution_status"]["stop_reason"])} The $30 project ceiling has not been reached. {link(data["execution_status_path"],"Recorded pause and continuation limits")}</p>'
    behavior = data["inspection_behavior"]
    behavior_html = ""
    if behavior.get("status") == "available":
        parts = [f'<h2>How the judges inspected the files</h2><p>Trace snapshot: {e(behavior["snapshot_completed_at"])}. The table compares the same tasks within each row group. A valid-record subset is shown separately; it is selected by record validity and is not representative.</p>']
        for match in behavior["matched_sets"]:
            tr = []
            for fam, value in match["models"].items():
                tr.append(f'<tr><td>{e(fam)}</td><td>{value["cells"]}</td><td>{value["acknowledged_view_exposures_summed_by_cell"]}</td><td>{value["tool_stats"]["native_structure"]["attempts"]}</td><td>{value["tool_stats"]["numeric_table"]["attempts"]}</td><td>{value["image_batch_limit_errors"]}</td></tr>')
            parts.append(f'<p><b>{e(match["label"])}:</b> {match["matched_task_count"]} paired tasks.</p><table><thead><tr><th>Judge</th><th>Same tasks</th><th>Distinct supplied views, summed by task</th><th>Native-structure attempts</th><th>Saved-cell calculation attempts</th><th>Image-cap errors</th></tr></thead><tbody>{"".join(tr)}</tbody></table>')
        parts.append(f'<p>Across all stable cells, {behavior["all_stable_cells_image_batch_limit_errors"]} image requests hit the four-image batch limit. An attempted tool call, a locally returned result and evidence received before a genuine model response are different events; their full counts are in the linked trace summary. Required visual completeness is unknown.</p><p>{e(behavior["interpretation"])}</p>')
        behavior_html = "".join(parts)
    assistant_parts = ['<h2>Assistant evidence checks</h2><p>These checks inspect evidence behind a candidate disagreement. They are not new model grades, human reviews or expert validation, and do not replace any frozen judgment.</p>']
    for note in data["assistant_evidence_checks"]:
        evidence = "".join(f'<tr><td>{e(x.get("location"))}</td><td>{("<q>" + e(x["quote"]) + "</q>") if x.get("quote") else e(x.get("finding"))}</td></tr>' for x in note.get("observed_evidence", []))
        refs = [link(note["packet_path"], "Original task and frozen rubric"), link(note["interpretation_path"], "Interpretation and limits")]
        if note.get("verification_path"):
            refs.append(link(note["verification_path"], "Read-only native evidence check"))
        if note.get("native_path"):
            refs.append(link(note["native_path"], "Existing native file"))
        for artifact in note.get("verification_artifacts", []):
            if artifact["path"] != note.get("native_path"):
                refs.append(link(artifact["path"], Path(artifact["path"]).name + " (checked evidence)"))
        if note.get("prior_human_review_path"):
            refs.append(link(note["prior_human_review_path"], "Previously recorded scoped human review — no new label"))
        raw = []
        for fam, cell in note["raw_judge_records"].items():
            label = cell.get("overall") or cell["status"]
            if cell.get("assessment_path"):
                label = link(cell["assessment_path"], label)
            else:
                label = e(label)
            raw.append(f'<li>{e(fam)} first-pass record: {label}; full assessment comparable: {e(cell["valid_for_comparison"])}.</li>')
        secondary = []
        for fam, cell in note["secondary_completion_records"].items():
            if cell["status"] != "not_repaired":
                label = cell.get("overall") or cell["status"]
                target = link(cell["assessment_path"], label) if cell.get("assessment_path") else e(label)
                secondary.append(f'<li>{e(fam)} secondary record completion: {target}; dependent and post hoc.</li>')
        assistant_parts.append(f'<article class="analyst-check"><h3>{e(note.get("title"))}</h3><p><small>Task {e(note["task_id"])} · scope {e(", ".join(note.get("criterion_scope", [])))}</small></p><p><b>Original requirement (analyst summary):</b> {e(note.get("original_requirement"))}</p><p><b>Inspection:</b> {e(note.get("verification_method"))} Saved evidence hashes still match: {e(note.get("native_hash_still_matches"))}.</p><table><thead><tr><th>Location</th><th>Observed evidence</th></tr></thead><tbody>{evidence}</tbody></table><p><b>First-pass observation:</b> {e(note.get("first_pass_judge_observation"))}</p><ul>{"".join(raw)}</ul>{("<p><b>Secondary completion, reported separately:</b></p><ul>" + "".join(secondary) + "</ul>") if secondary else ""}<p><b>Interpretation:</b> {e(note.get("interpretation"))}</p><p><b>Causal limit:</b> {e(note.get("causal_limit"))}</p><p><b>Data hypothesis:</b> {e(note.get("data_hypothesis"))}</p><p>{" · ".join(refs)}</p></article>')
    assistant_html = "".join(assistant_parts)
    diagnostic_parts = ['<h2>Retained evidence in invalid grader records</h2><p>Incomplete source quotations or other record defects do not prove a business error. Usable criterion records and verified quotation segments remain visible below. Their raw verdicts do not enter the primary valid-assessment comparisons.</p>']
    for fam in FAMILIES:
        diag = data["models"][fam]["invalid_record_diagnostics"]
        diagnostic_parts.append(f'<p><b>{e(fam)}</b>: {diag["invalid_assessments_with_retained_criteria"]} invalid assessments with retained criterion records; {diag["criterion_contract_valid_records"]} criterion records pass structural checks and {diag["criterion_contract_invalid_records"]} fail them. {diag["text_verified_quote_records"]} quotation records match extracted text. Structural and text matches do not establish accuracy.</p>')
    for row in data["tasks"]:
        for fam in FAMILIES:
            cell = row["judges"][fam]
            if cell["valid_for_comparison"] or not cell.get("criteria"):
                continue
            segments = "".join(f'<tr><td>{e(x["criterion_id"])}</td><td>{e(x["raw_verdict"])}</td><td>{"meets structural checks" if x["criterion_contract_valid"] else e("; ".join(x["criterion_contract_errors"] + x["global_contract_errors"]))}</td><td>{x["text_verified_quote_records"]}/{x["quote_records"]}</td><td>{x["provenance_flag_count"]}</td></tr>' for x in cell.get("criterion_record_diagnostics", []))
            diagnostic_parts.append(f'<details><summary>{e(fam)} · {e(row["title"])} · {e(cell["status"])}</summary><p>{link(cell["assessment_path"],"Unchanged raw assessment")}</p><table><thead><tr><th>Criterion</th><th>Raw verdict</th><th>Record structure</th><th>Text-matched quotes</th><th>Provenance flags</th></tr></thead><tbody>{segments}</tbody></table></details>')
    diagnostic_parts.append(f'<h2>Secondary record completion</h2><p>{data["record_completion"]["valid_unique_new_assessments_after_completion"]}/{data["requested_new_assessments"]} unique assessments have valid records after any recorded completion. Original first-pass records remain above; a completion request is dependent and post hoc.</p>')
    diagnostic_parts.append(f'<p>{e(data["record_completion"]["execution_note"])}</p>')
    for fam, rep in data["record_completion"]["models"].items():
        diagnostic_parts.append(f'<p>{e(fam)}: {rep["valid_repaired_assessments"]} valid completion records; {rep["recorded_verdict_flips"]} recorded criterion-verdict changes.</p>')
    diagnostic_parts.append('<h2>Four scoped human reviews</h2><p>These are non-specialist, evidence-assisted reviews of named issues. Judge reasons must be checked against that exact issue; matching a broad criterion label is insufficient. No expert accuracy or false-accept rate is calculated. The absence-procedure human decision is still pending.</p>')
    for case in data["scoped_human_review_comparisons"]:
        findings = []
        for judge, finding in case["judge_findings"].items():
            label = finding.get("raw_verdict") or finding["status"]
            if finding.get("assessment_path"):
                label = link(finding["assessment_path"], label)
            else:
                label = e(label)
            reason = finding.get("criterion", {}).get("reason") or "No comparable criterion record yet."
            findings.append(f'<p><b>{e(judge)}</b>: {label}. {e(reason)}</p>')
        diagnostic_parts.append(f'<details><summary>{e(case["criterion_id"])} · user: {e(case["human_classification"])}</summary><p>{e(case["human_scope"])} {link(case["human_review_path"],"Recorded human review")}</p>{"".join(findings)}</details>')
    diagnostic_html = "".join(diagnostic_parts)
    task_details = ['<h2>Inspect each task and criterion</h2><p>Expand a task for the frozen requirement, each judge’s reasoning, output excerpts, native files and traces. Raw verdicts in invalid records are provisional and excluded from primary metrics. Quoted excerpts are exactly the judge’s cited text; matching text does not establish relevance or accuracy.</p>']
    for row in data["tasks"]:
        native_links = " · ".join(link(a["path"], a["id"] + " (" + str(a["kind"]) + ")") for a in row["native_artifacts"])
        blocks = []
        for frozen in row["frozen_criteria"]:
            cid = frozen["criterion_id"]
            judge_blocks, labels, flags = [], [], []
            recorded_verdicts = []
            for fam in ("Astra", *FAMILIES):
                cell = row["judges"][fam]
                cr = next((x for x in cell.get("criteria", []) if x["criterion_id"] == cid), None)
                if cr is None:
                    labels.append(f"{fam}: {cell['status'].replace('_', ' ')}")
                    trace = link(cell["result_path"], "Raw execution record") if cell.get("result_path") else ""
                    explanation = cell.get("execution_classification_note", "")
                    judge_blocks.append(f'<article class="judge-card"><b>{e(fam)}</b><p>{e(cell["status"].replace("_", " "))}. No criterion verdict is inferred.</p><p>{e(explanation)}</p><p>{trace}</p></article>')
                    continue
                recorded_verdicts.append(cr["verdict"])
                labels.append(f"{fam}: {cr['verdict']}")
                if cr["verdict"] in ("uncertain", "not_assessed"):
                    flags.append("uncertainty")
                if cr.get("rubric_scope_objection"):
                    flags.append("scope objection")
                if cr["verdict"] == "fail":
                    flags.append("flagged requirement")
                record_note = "Structurally valid full assessment; accuracy remains provisional."
                if not cell["valid_for_comparison"]:
                    diag = next((x for x in cell.get("criterion_record_diagnostics", []) if x["criterion_id"] == cid), {})
                    structural = "this criterion meets structural checks" if diag.get("criterion_contract_valid") else "this criterion has incomplete or invalid record fields"
                    record_note = f"Invalid full assessment; {structural}. Raw verdict retained descriptively and excluded from primary comparisons."
                excerpts = []
                for ev in cr.get("output_evidence", [])[:2]:
                    if not isinstance(ev, dict) or not isinstance(ev.get("quote"), str) or not ev["quote"]:
                        continue
                    quote = ev["quote"]
                    excerpt = quote[:350]
                    reference = ev.get("evidence_id", ev.get("artifact", "output"))
                    trunc = " (excerpt; full quote in record)" if len(quote) > 350 else ""
                    excerpts.append(f'<blockquote>{e(excerpt)}</blockquote><small>{e(reference)} · {e(ev.get("locator", "location not supplied"))}{e(trunc)}</small>')
                if not excerpts:
                    excerpts.append('<p><small>No output quotation in this criterion record. Inspect its scope or visual evidence before accepting an absence claim.</small></p>')
                traces = [link(cell["assessment_path"], "Raw assessment")]
                for field, label in (("result_path", "Execution record"), ("evidence_exposure_path", "Evidence viewed"), ("validation_path", "Record validation")):
                    if cell.get(field) and local_path(cell[field]).exists():
                        traces.append(link(cell[field], label))
                scope = f'<p><b>Scope objection:</b> {e(cr["rubric_scope_objection"])}</p>' if cr.get("rubric_scope_objection") else ""
                extra = ""
                if fam in FAMILIES:
                    repair = row["record_repairs"][fam]
                    repaired_cr = next((x for x in repair.get("criteria", []) if x["criterion_id"] == cid), None)
                    if repaired_cr:
                        extra = f'<details><summary>Secondary record completion: {e(repaired_cr["verdict"])}</summary><p>Dependent, post hoc response; first-pass verdict above is unchanged. Completion status: {e(repair["status"])}.</p><p>{e(repaired_cr.get("reason"))}</p><p>{link(repair["assessment_path"], "Completion assessment")}</p></details>'
                judge_blocks.append(f'<article class="judge-card"><b>{e(fam)} · {e(cr["verdict"])} · severity {e(cr.get("severity") if cr.get("severity") is not None else "—")}</b><p class="record-note">{e(record_note)}</p><p>{e(cr.get("reason") or "No reason recorded.")}</p>{scope}{"".join(excerpts)}<p>{" · ".join(traces)}</p>{extra}</article>')
            if len(set(recorded_verdicts)) > 1:
                flags.append("verdict disagreement")
            summary = f"{cid} — {frozen['title']}"
            badges = " · ".join(sorted(set(flags))) or "no recorded verdict difference"
            source_anchor = frozen.get("source_anchor")
            source_note = f'<p><small>Original-task anchor: {e(source_anchor)}</small></p>' if source_anchor else ""
            blocks.append(f'<details><summary>{e(summary)} <small>{e(badges)} · {e(" / ".join(labels))}</small></summary><p><b>Frozen requirement:</b> {e(frozen["requirement_text"])}</p>{source_note}<div class="judge-grid">{"".join(judge_blocks)}</div></details>')
        task_details.append(f'<details class="task-detail"><summary>{e(row["title"])} <small>{e(row["occupation"])} · {e(row["rubric_format"])} · {e(row["task_id"])}</small></summary><p><b>Existing native files:</b> {native_links}</p><p>{link(row["packet_path"],"Frozen grading packet")}</p>{"".join(blocks)}</details>')
    task_detail_html = "".join(task_details)
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Cross-family judge comparison</title><style>body{{font:16px/1.55 system-ui,sans-serif;max-width:1180px;margin:36px auto;padding:0 24px;color:#172332;background:#f8fafc}}h1,h2{{line-height:1.2}}a{{color:#12559c}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}.card{{background:white;border:1px solid #cbd5e1;border-radius:10px;padding:18px}}.card b{{display:block;font-size:30px}}.card span,small{{display:block;color:#536373}}table{{border-collapse:collapse;width:100%;background:white}}th,td{{border-bottom:1px solid #d8e0e9;text-align:left;padding:10px;vertical-align:top}}small{{font-size:11px}}.note{{border-left:4px solid #c58c22;padding:12px 18px;background:#fff8e8}}.analyst-check{{background:white;border:1px solid #cbd5e1;border-radius:10px;padding:18px;margin:14px 0}}.judge-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}}.judge-card{{padding:12px;border:1px solid #d8e0e9;min-width:0;overflow-wrap:anywhere}}.record-note{{font-size:12px;color:#536373}}blockquote{{border-left:3px solid #cbd5e1;margin:10px 0;padding:0 10px;font-size:14px}}details{{background:#fff;padding:12px;margin:8px 0;border:1px solid #d8e0e9}}@media(max-width:700px){{.cards{{grid-template-columns:repeat(2,1fr)}}table{{font-size:13px}}}}</style><main><p>{link("output/evaluation_v4/report.html","Forty-task evaluation")}</p><h1>Gemini and Claude judge extension</h1><p>Existing outputs, frozen task rubrics, separate assessments. Updated {e(data["created_at_utc"])}.</p><div class="cards">{cards}</div><p class="note">{e(data["status"].replace("_"," "))}. {data["uncompleted_or_invalid_new_assessments"]} first-pass reviews remain incomplete or invalid; secondary record completion is reported separately below. Astra has no baseline for {data["astra_baselines_missing"]} tasks. No missing result is counted as a pass or failure.</p>{history_html}<h2>Comparison</h2><p>These are paired agreement counts, not accuracy. Cohort-specific matrices and complete provenance are in {link("output/evaluation_v5/analysis.json","analysis JSON")}.</p>{"".join(comparisons)}{behavior_html}{assistant_html}{diagnostic_html}<h2>Costs</h2><p>This extension: {c["this_extension"]["request_count"]} request records; ${c["this_extension"]["confirmed_cost_usd"]:.6f} confirmed and ${c["this_extension"]["unresolved_reserved_usd"]:.6f} in raw unresolved reservations before the amendment below. Effective committed API budget after reconciliation: ${c["total_shared_evaluation_ledger"]["committed_usd"]:.6f} of $30, leaving ${c["headroom_usd"]:.6f}. In-app inference cost is unknown.</p>{costnote}<h2>What the comparison can establish</h2><p>{link("docs/evaluation_v5/execution-and-interpretation.txt", "Read the execution and interpretation guide")}</p><ul>{limits}</ul><h2>Research-informed validation</h2><p>{e(data["construct_validity"]["application"])} Construct probes are proposed, not executed; S and R are unmeasured. {link("docs/evaluation_v5/research-and-construct-validity.txt","Read the verified research and proposed protocol")}.</p><h2>All selected tasks</h2><table><thead><tr><th>Task</th><th>Cohort</th><th>Astra baseline</th><th>Gemini</th><th>Claude</th></tr></thead><tbody>{"".join(table)}</tbody></table>{task_detail_html}<p>{link("output/evaluation_v5/task-judge-matrix.csv","Download task matrix")} · {link("output/evaluation_v5/analysis.txt","Plain-language analysis")} · {link("output/evaluation_v5/packet-inventory.json","Artifact selection and hashes")}</p></main></html>'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=OUT / "packet-inventory.json")
    args = parser.parse_args()
    data = build(args.inventory)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "analysis.json").write_text(json.dumps(data, indent=2) + "\n")
    (OUT / "analysis.txt").write_text(render_text(data))
    (OUT / "report.html").write_text(render_html(data))
    fields = ["task_id", "title", "cohort", "rubric_format", "Astra_status", "Astra_verdict", "Gemini_status", "Gemini_verdict", "Claude_status", "Claude_verdict"]
    with (OUT / "task-judge-matrix.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in data["tasks"]:
            item = {k: row[k] for k in fields[:4]}
            for fam in ("Astra", *FAMILIES):
                item[fam + "_status"] = row["judges"][fam]["status"]
                item[fam + "_verdict"] = row["judges"][fam]["overall"]
            writer.writerow(item)
    print(json.dumps({k: data[k] for k in ("status", "selected_original_tasks", "requested_new_assessments", "valid_new_assessments", "astra_baselines_available", "astra_baselines_missing", "analysis_integrity_problems")}))


if __name__ == "__main__":
    main()
