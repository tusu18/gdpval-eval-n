"""Post-hoc criterion-level diagnostics; never changes frozen grading records.

The whole-response validity rule stays unchanged. A separate, explicitly named
analysis checks each original criterion using the same frozen validator. Human
labels are loaded only here, after judging, and are never added to API packets.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import copy
import hashlib
import json
from pathlib import Path

from evaluation_v2_grading import validate_judgment
from run_evaluation_v2 import ROOT, OUT, read, write, now, digest

TARGET = "source_and_authority_consistency"
EXPECTED = ROOT / "data/evaluation_v2/development-calibration-expected.private.json"
PUBLIC = ROOT / "data/evaluation_v2/development-calibration.json"


def analyze_rows(packet, judgment):
    """Keep full invalidity; check a uniquely identified row in isolation."""
    full_errors = validate_judgment(packet, judgment)
    result = {"whole_response_valid": not full_errors, "whole_response_validation_errors": full_errors, "criteria": []}
    rows = judgment.get("criteria", []) if isinstance(judgment, dict) else []
    if not isinstance(rows, list):
        rows = []
    for criterion in packet["criteria"]:
        cid = criterion["id"]
        matching = [r for r in rows if isinstance(r, dict) and r.get("id") == cid]
        record = {"criterion_id": cid, "criterion_text": criterion["criterion"], "row_valid": False,
                  "row_validation_errors": [], "row_status": None, "severity": None,
                  "coverage_status": None, "judge_consequential_flag": None, "binary_eligible": False}
        if len(matching) != 1:
            record["row_validation_errors"] = ["missing_or_duplicate_target_criterion"]
            result["criteria"].append(record)
            continue
        row = matching[0]
        single_packet = copy.deepcopy(packet)
        single_packet["criteria"] = [copy.deepcopy(criterion)]
        single_judgment = {"task_defect": copy.deepcopy(judgment.get("task_defect")), "criteria": [copy.deepcopy(row)]}
        errors = validate_judgment(single_packet, single_judgment)
        record.update(row_valid=not errors, row_validation_errors=errors,
                      row_status=row.get("status"), severity=row.get("severity"),
                      coverage_status=row.get("coverage_status"),
                      coverage_limitations=row.get("coverage_limitations"),
                      rationale=row.get("rationale"), evidence=copy.deepcopy(row.get("evidence")),
                      assumptions=row.get("assumptions"), counterevidence=row.get("counterevidence"),
                      consequence=row.get("consequence"), minimum_correction=row.get("minimum_correction"),
                      rule_stated=row.get("rule_stated"), rule_honored=row.get("rule_honored"),
                      operative_sections_inspected=row.get("operative_sections_inspected"))
        task_clear = isinstance(judgment.get("task_defect"), dict) and judgment["task_defect"].get("status") == "no"
        packet_complete = packet.get("coverage", {}).get("full_sources") is True and packet.get("coverage", {}).get("full_artifact_extracts") is True
        record["packet_coverage"] = copy.deepcopy(packet.get("coverage", {}))
        if not errors and task_clear:
            if row.get("status") == "fail" and row.get("severity") == "consequential":
                record.update(judge_consequential_flag=True, binary_eligible=True)
            elif packet_complete and (row.get("status") == "pass" or (row.get("status") == "fail" and row.get("severity") in ("minor", "substantive"))):
                # Negative means no consequential flag from this criterion;
                # it is not acceptance of the document or absence of all errors.
                record.update(judge_consequential_flag=False, binary_eligible=True)
        if row.get("status") == "pass" and row.get("coverage_status") != "complete":
            record["invalidity_explanation"] = "Judge returned pass while declaring incomplete evidence coverage; this is a coverage/status inconsistency, not a quote-normalization failure."
        result["criteria"].append(record)
    return result


def comparison_cell(flag, human):
    if flag is None or human not in ("yes", "no"):
        return None
    return ("T" if bool(flag) == (human == "yes") else "F") + ("P" if flag else "N")


def summarize_cases(cases):
    matrix = Counter({"TP": 0, "FP": 0, "TN": 0, "FN": 0})
    outside = Counter()
    for case in cases:
        cell = case.get("diagnostic_matrix_cell")
        if cell:
            matrix[cell] += 1
        else:
            outside[case.get("matrix_exclusion_reason", "unknown")] += 1
    n = sum(matrix.values())
    tp, fp, tn, fn = [matrix[k] for k in ("TP", "FP", "TN", "FN")]
    def ratio(a, b):
        return {"numerator": a, "denominator": b, "value": a / b if b else None}
    return {"matrix": dict(matrix), "binary_comparable_cases": n, "outside_matrix": dict(outside),
            "whole_response_statuses": dict(Counter(c["raw_whole_response_status"] for c in cases)),
            "diagnostic_target_flags_matching_human_errors": ratio(tp, tp + fn),
            "diagnostic_target_misses": ratio(fn, tp + fn),
            "diagnostic_target_false_alarms": ratio(fp, fp + tn),
            "diagnostic_agreement": ratio(tp + tn, n),
            "target_criterion": TARGET,
            "not_estimated": ["whole-output acceptance accuracy", "population judge accuracy", "generalization across occupations", "independent expert acceptance rate"],
            "intervals": "Not estimated: five deliberately selected outputs from two previously studied task families; report counts and case evidence."}


def analyze_calibration():
    expected = read(EXPECTED)
    if expected["public_packet_sha256"] != digest(PUBLIC):
        raise ValueError("Historical source bank differs from the label-provenance record")
    labels = {x["case_id"]: x for x in expected["cases"]}
    folders = list((OUT / "development_calibration").glob("*"))
    models = sorted({read(p / "result.json")["model"] for p in folders if (p / "result.json").exists()})
    if not models:
        models = [read(ROOT / "config/evaluation_v2_run.json")["primary_judge"]]
    all_cases = []
    input_hashes = {str(EXPECTED.relative_to(ROOT)): digest(EXPECTED), str(PUBLIC.relative_to(ROOT)): digest(PUBLIC),
                    "scripts/evaluation_v2_grading.py": digest(ROOT / "scripts/evaluation_v2_grading.py")}
    for model in models:
        for case_id, label in labels.items():
            folder = OUT / "development_calibration" / (case_id + "__" + model.replace("/", "_"))
            base = {"case_id": case_id, "judge_model": model,
                    "task_family": label.get("source_provenance", {}).get("family_id"),
                    "human_consequential_error": label["expected"]["consequential_error"],
                    "human_content_acceptable": label["expected"]["content_acceptable"],
                    "human_evaluation_defect": label["expected"]["evaluation_defect"],
                    "human_label_export_sha256": label["label_provenance"]["export_sha256"],
                    "reviewer_scope": "Previously exposed project-owner extracted-text review; native visuals not confirmed; expertise and independence unestablished",
                    "raw_whole_response_status": "pending", "diagnostic_matrix_cell": None,
                    "matrix_exclusion_reason": "pending", "criteria": [], "human_acceptance_inferred": False}
            if not (folder / "result.json").exists():
                all_cases.append(base); continue
            raw_result = read(folder / "result.json")
            base.update(raw_whole_response_status=raw_result["status"], known_cost_usd=raw_result.get("known_cost_usd"),
                        original_result_path=str((folder / "result.json").relative_to(ROOT)))
            input_hashes[base["original_result_path"]] = digest(folder / "result.json")
            packet_path, judgment_path = folder / "packet-01.json", folder / "judgment-01.json"
            if not packet_path.exists() or not judgment_path.exists():
                base["matrix_exclusion_reason"] = "missing_parsed_response"
                all_cases.append(base); continue
            packet, judgment = read(packet_path), read(judgment_path)
            for p in (packet_path, judgment_path):
                input_hashes[str(p.relative_to(ROOT))] = digest(p)
            rows = analyze_rows(packet, judgment)
            base.update(rows)
            target = next((c for c in rows["criteria"] if c["criterion_id"] == TARGET), None)
            if target is None or not target["row_valid"]:
                base["matrix_exclusion_reason"] = "invalid_or_missing_business_criterion"
            elif label["expected"]["evaluation_defect"] != "no":
                base["matrix_exclusion_reason"] = "human_task_defect_or_uncertainty"
            elif not target["binary_eligible"]:
                base["matrix_exclusion_reason"] = "uncertain_not_applicable_or_judge_task_defect"
            else:
                base["diagnostic_matrix_cell"] = comparison_cell(target["judge_consequential_flag"], label["expected"]["consequential_error"])
                base["matrix_exclusion_reason"] = None if base["diagnostic_matrix_cell"] else "missing_human_label"
            base["target_criterion_result"] = target
            all_cases.append(base)
    grouped = defaultdict(list)
    for case in all_cases:
        grouped[case["judge_model"]].append(case)
    return {"schema": "evaluation-v2-posthoc-criterion-calibration-v1", "created_at": now(),
            "analysis_status": "post_hoc_separate_diagnostic_not_a_change_to_frozen_grader",
            "input_hashes": input_hashes,
            "semantics": "The broad source-and-authority criterion is compared to the earlier consequential-business-error label. Their constructs overlap but are not identical. Read case-level evidence; matching binary labels alone do not verify matching error rationale.",
            "preservation": "Original whole-response invalid statuses remain invalid. No global acceptance, pass or rejection is reconstructed from selected rows. All criteria, including invalid rows, are shown.",
            "limitations": ["Five selected historical cases, two task families, one project-owner reviewer; not a fresh holdout.",
                            "Prompt/rubric design already used lessons from these cases.",
                            "Human tooling judgments rely on the stated single-toolset assumption, not a proven inventory fact.",
                            "Human approval finding identifies a proposed-routing risk, not observed financial loss.",
                            "No native visual-acceptance labels; missing visual evidence is not a human rejection.",
                            "A valid evidence citation can still support an incorrect inference."],
            "per_judge": {model: summarize_cases(cases) for model, cases in grouped.items()}, "cases": all_cases}


def analyze_primary_rows():
    results = []
    for file in sorted((OUT / "grades").glob("*/result.json")):
        result = read(file)
        for packet_file in sorted(file.parent.glob("packet-[0-9][0-9].json")):
            judgment_file = packet_file.with_name(packet_file.name.replace("packet-", "judgment-"))
            if not judgment_file.exists():
                continue
            rows = analyze_rows(read(packet_file), read(judgment_file))
            results.append({"task_id": result.get("task_id"), "judge_model": result.get("model"),
                            "solver_run_id": result.get("solver_run_id"), "raw_whole_response_status": result["status"],
                            "packet_path": str(packet_file.relative_to(ROOT)), "packet_sha256": digest(packet_file),
                            "judgment_path": str(judgment_file.relative_to(ROOT)), "judgment_sha256": digest(judgment_file),
                            "analysis_scope": "Post-hoc row-validity diagnostic; no new human comparison or global grade", **rows})
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--include-primary", action="store_true")
    p.add_argument("--out", type=Path, default=OUT / "calibration_analysis.json")
    args = p.parse_args()
    report = analyze_calibration()
    if args.include_primary:
        report["primary_row_diagnostics"] = analyze_primary_rows()
    write(args.out, report)
    print(json.dumps({"path": str(args.out), "per_judge": report["per_judge"]}, indent=2))


if __name__ == "__main__":
    main()
