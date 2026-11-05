"""Posthoc contract audit; original invalid judgments remain immutable.

Separate audit levels preserve original scores: S1 singleton string container;
S2 correct per-artifact visual mapping; S3 known structural locator removal only.
No decision, severity, substantive content, missing field or whitespace is edited.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
import re

from run_evaluation_v2 import ROOT, OUT, read, write, digest, now, canonical
from evaluation_v2_grading import validate_judgment, _contains, JUDGE_INSTRUCTIONS

BASE = OUT / "invalid_judgment_audit"
TRANSFORM_VERSION = "posthoc-contract-audit-levels-v2"


def normalize_shape(judgment):
    normalized = copy.deepcopy(judgment)
    transforms = []
    rows = normalized.get("criteria", []) if isinstance(normalized, dict) else []
    if not isinstance(rows, list):
        return normalized, transforms
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        value = row.get("operative_sections_inspected")
        if isinstance(value, str) and value.strip():
            row["operative_sections_inspected"] = [value]
            transforms.append({"criterion_id": row.get("id"), "json_pointer": f"/criteria/{index}/operative_sections_inspected",
                               "before_type": "string", "after_type": "array", "original_text_verbatim": value,
                               "text_sha256": hashlib.sha256(value.encode()).hexdigest(), "transformation": "wrap exact value in singleton list; no splitting, trimming or new evidence"})
    return normalized, transforms


def content_only(item):
    units = item.get("units")
    return "\n".join(u.get("text", "") for u in units if isinstance(u, dict) and isinstance(u.get("text"), str)) if isinstance(units, list) and units else item.get("text", "")


def visual_relation(packet, row):
    """Check a global row-level view list against per-evidence artifacts."""
    ids = row.get("inspection_ids")
    artifacts = {a["id"] for a in packet.get("artifacts", [])}
    observations = {o["id"]: o for o in packet.get("inspection", {}).get("observations", []) if isinstance(o, dict) and isinstance(o.get("id"), str)}
    evidence = row.get("evidence")
    if not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids):
        return {"valid": False, "reason": "missing_or_malformed_inspection_ids"}
    if not isinstance(evidence, list) or not evidence or any(not isinstance(e, dict) for e in evidence):
        return {"valid": False, "reason": "missing_or_malformed_evidence"}
    for identity in ids:
        observation = observations.get(identity)
        if not observation or observation.get("image_supplied") is not True or observation.get("artifact_id") not in artifacts:
            return {"valid": False, "reason": "unknown_unsupplied_or_unknown_artifact_view", "view_id": identity}
    mapping = {}
    for ev in evidence:
        aid = ev.get("artifact_id")
        if aid not in artifacts:
            return {"valid": False, "reason": "unknown_evidence_artifact", "artifact_id": aid}
        mapped = [i for i in ids if observations[i].get("artifact_id") == aid]
        if not mapped:
            return {"valid": False, "reason": "cited_artifact_has_no_supplied_view", "artifact_id": aid}
        mapping[aid] = mapped
    return {"valid": True, "reason": "all_row_views_supplied_and_each_evidence_artifact_has_a_mapped_view", "artifact_view_mapping": mapping,
            "all_global_views": {i: observations[i]["artifact_id"] for i in ids}}


def validate_visual_contract(packet, judgment):
    errors = validate_judgment(packet, judgment)
    accepted = []
    for row in judgment.get("criteria", []) if isinstance(judgment, dict) else []:
        if not isinstance(row, dict):
            continue
        code = str(row.get("id")) + ":unverifiable_visual_observation"
        if code not in errors or row.get("evidence_kind") != "visual":
            continue
        relation = visual_relation(packet, row)
        if relation["valid"]:
            errors.remove(code)
            accepted.append({"criterion_id": row.get("id"), "original_error": code, "correction": "S2 per-artifact view mapping from a global row list", **relation})
    return errors, accepted


def remove_known_locator_wrappers(item, quote):
    """Remove only known structural prefixes from a whole exact raw substring.

    Positions come from rebuilding the entire locator-augmented extraction, not
    regex guesses. Altered content, skipped units and partial prefixes fail.
    """
    if not isinstance(quote, str) or not quote or _contains(item, quote):
        return None
    units = item.get("units")
    if not isinstance(units, list) or not units or any(not isinstance(u, dict) or not isinstance(u.get("locator"), str) or not isinstance(u.get("text"), str) for u in units):
        return None
    augmented = "\n".join(u["locator"] + "\t" + u["text"] for u in units)
    if augmented != item.get("text"):
        return None
    wrapper_ranges, position = [], 0
    for unit in units:
        wrapper = unit["locator"] + "\t"
        wrapper_ranges.append((position, position + len(wrapper), unit["locator"], wrapper))
        position += len(wrapper) + len(unit["text"]) + 1
    start = augmented.find(quote)
    while start >= 0:
        end = start + len(quote)
        overlaps = [r for r in wrapper_ranges if r[0] < end and r[1] > start]
        if overlaps and all(a >= start and b <= end for a, b, _, _ in overlaps):
            cursor, pieces, removals, segments = 0, [], [], []
            for a, b, locator, wrapper in overlaps:
                left, right = a - start, b - start
                piece = quote[cursor:left]
                pieces.append(piece)
                if piece:
                    segments.append({"original_quote_start": cursor, "original_quote_end": left, "content_verbatim": piece})
                removals.append({"original_quote_start": left, "original_quote_end": right, "locator": locator, "removed_wrapper_verbatim": wrapper})
                cursor = right
            final = quote[cursor:]
            pieces.append(final)
            if final:
                segments.append({"original_quote_start": cursor, "original_quote_end": len(quote), "content_verbatim": final})
            normalized = "".join(pieces)
            if normalized and normalized in content_only(item):
                return {"original_quote_verbatim": quote, "normalized_quote_verbatim": normalized,
                        "raw_quote_in_augmented_text": True, "raw_quote_start_in_augmented_text": start,
                        "whole_quote_continuity_verified": True, "normalized_quote_in_full_content_stream": True,
                        "removed_locator_wrappers": removals, "preserved_content_segments": segments,
                        "content_characters_preserved": sum(len(s["content_verbatim"]) for s in segments)}
        start = augmented.find(quote, start + 1)
    return None


def normalize_locator_quotes(packet, judgment):
    normalized = copy.deepcopy(judgment)
    transforms = []
    sources = {s["id"]: s for s in packet.get("source_documents", [])}
    artifacts = {a["id"]: a for a in packet.get("artifacts", [])}
    for row in normalized.get("criteria", []) if isinstance(normalized, dict) else []:
        if not isinstance(row, dict) or not isinstance(row.get("evidence"), list):
            continue
        for index, ev in enumerate(row["evidence"]):
            if not isinstance(ev, dict):
                continue
            for field, id_field, collection in [("source_quote", "source_id", sources), ("output_quote", "artifact_id", artifacts)]:
                if field == "output_quote" and row.get("evidence_kind") != "quoted":
                    continue
                item = collection.get(ev.get(id_field))
                if item is None:
                    continue
                change = remove_known_locator_wrappers(item, ev.get(field))
                if change:
                    ev[field] = change["normalized_quote_verbatim"]
                    transforms.append({"criterion_id": row.get("id"), "evidence_index": index, "quote_field": field,
                                       "evidence_id": ev.get(id_field), "operation": "S3 delete exact known structural locator+tab wrappers only", **change})
    return normalized, transforms


def quote_diagnostics(packet, row, field):
    source_side = field == "source_quote"
    collection = packet["source_documents"] if source_side else packet["artifacts"]
    id_field = "source_id" if source_side else "artifact_id"
    by_id = {d["id"]: d for d in collection}
    details = []
    for evidence in row.get("evidence", []) if isinstance(row.get("evidence"), list) else []:
        if not isinstance(evidence, dict):
            continue
        quote = evidence.get(field)
        item = by_id.get(evidence.get(id_field))
        if item is not None and _contains(item, quote):
            continue
        q = quote if isinstance(quote, str) else ""
        whitespace = lambda value: re.sub(r"\s+", " ", value).strip()
        classification = "quote_not_exactly_supported_by_referenced_extraction"
        if not item:
            classification = "missing_or_unknown_evidence_id"
        elif q and q in item.get("text", ""):
            classification = "exact_in_locator_augmented_text_not_content_units"
        elif q and whitespace(q) in whitespace(content_only(item)):
            classification = "whitespace_only_difference_candidate_not_repaired"
        elif q and q.casefold() in content_only(item).casefold():
            classification = "case_only_difference_candidate_not_repaired"
        elsewhere = [d["id"] for d in collection if d is not item and _contains(d, quote)]
        details.append({"evidence_reference": evidence.get(id_field), "quote_verbatim": quote, "quote_field": field,
                        "classification": classification, "exact_quote_in_other_evidence_ids": elsewhere,
                        "automatic_quote_repair_applied": False})
    return details


def diagnose_error(error, packet, judgment):
    cid, code = error.split(":", 1) if ":" in error else (None, error)
    row = next((r for r in judgment.get("criteria", []) if isinstance(r, dict) and str(r.get("id")) == cid), {}) if isinstance(judgment, dict) else {}
    category = "other_contract_violation"
    repair = False
    if code == "missing_operative_coverage":
        value = row.get("operative_sections_inspected")
        if isinstance(value, str) and value.strip():
            category, repair = "schema_shape_nonempty_operative_string", True
        else:
            category = "missing_operative_evidence_or_malformed_list"
    elif code == "pass_conflicts_with_coverage_or_honoring":
        category = "pass_with_partial_or_unavailable_coverage" if row.get("coverage_status") != "complete" else "pass_with_rule_not_honored"
    elif code in ("unverifiable_source_quote", "unverifiable_output_quote"):
        category = code
    elif code == "unverifiable_visual_observation":
        category = "visual_evidence_reference_or_delivery_mismatch"
    elif "token_limit" in code or "output_token" in code:
        category = "output_token_budget"
    elif code.startswith(("invalid_", "criteria_", "judgment_")) or code == "missing_duplicate_or_unknown_criteria":
        category = "schema_shape_or_enum"
    elif code.startswith("missing_"):
        category = "missing_required_judgment_evidence"
    details = {"criterion_id": cid, "validator_error": error, "category": category,
               "lossless_shape_repair_applied": repair,
               "raw_status": row.get("status"), "raw_coverage_status": row.get("coverage_status"),
               "raw_rule_honored": row.get("rule_honored"), "raw_operative_sections_inspected": row.get("operative_sections_inspected"),
               "raw_coverage_limitations": row.get("coverage_limitations"), "raw_rationale": row.get("rationale")}
    if code in ("unverifiable_source_quote", "unverifiable_output_quote"):
        details["quote_diagnostics"] = quote_diagnostics(packet, row, "source_quote" if "source" in code else "output_quote")
    if code == "unverifiable_visual_observation":
        details.update(raw_inspection_ids=row.get("inspection_ids"), raw_evidence=row.get("evidence"),
                       supplied_observations=packet["inspection"].get("observations", []))
        inspections = row.get("inspection_ids")
        observations = {o["id"]: o for o in packet["inspection"].get("observations", []) if isinstance(o, dict) and isinstance(o.get("id"), str)}
        evidence_artifacts = {e.get("artifact_id") for e in row.get("evidence", []) if isinstance(e, dict)} if isinstance(row.get("evidence"), list) else set()
        all_delivered = isinstance(inspections, list) and bool(inspections) and all(isinstance(i, str) and i in observations and observations[i].get("image_supplied") is True for i in inspections)
        cited_artifacts = {observations[i].get("artifact_id") for i in inspections} if all_delivered else set()
        details.update(all_cited_visuals_were_supplied=all_delivered, evidence_artifacts=sorted(str(x) for x in evidence_artifacts),
                       cited_visual_artifacts=sorted(str(x) for x in cited_artifacts))
        if all_delivered and len(cited_artifacts) > 1 and evidence_artifacts <= cited_artifacts:
            details["category"] = "visual_global_list_spans_artifacts_all_views_supplied"
            details["contract_observation"] = "Each referenced evidence artifact has a supplied view, but validator requires every global inspection_id to belong to each evidence artifact. This rejects a multi-artifact inspection list; it does not establish missing image access. No visual remapping applied."
    return details


def cohort(path, result):
    if "development_calibration" in path.parts:
        return "historical_development_calibration"
    if "judge_checks" in path.parts:
        return "judge_checks_" + result.get("study", "unknown")
    if result.get("recovery_stage") == "recovery" or "__recovery" in path.parent.name:
        return "recovery"
    return result.get("stage", "unspecified")


def invalid_units(path, result):
    folder = path.parent
    if result.get("batches"):
        for batch in result["batches"]:
            if batch.get("summary", {}).get("status") != "invalid_judgment":
                continue
            number = batch["batch"]
            yield (f"batch-{number:02d}", folder / f"packet-{number:02d}.json", folder / f"judgment-{number:02d}.json",
                   folder / f"response-{number:02d}.json", batch.get("summary", {}).get("validation_errors", []), batch.get("call_id"))
    else:
        packet = folder / ("packet-final.json" if (folder / "packet-final.json").exists() else "packet.json")
        responses = sorted(folder.glob("response-*.json"))
        yield "final", packet, folder / "judgment.json", responses[-1] if responses else None, result.get("summary", {}).get("validation_errors", []), None


def audit():
    roots = [OUT / "grades", OUT / "grades_continuations", OUT / "development_calibration", OUT / "judge_checks/jobs"]
    paths = sorted(p for root in roots for p in root.glob("*/result.json"))
    script_sha = digest(__file__)
    snapshot = {str(p.relative_to(ROOT)): digest(p) for p in paths}
    cases, aliases = [], []
    for path in paths:
        result = read(path)
        if result.get("status") == "reused_exact_fixed_request" and result.get("reused_result_status") == "invalid_judgment":
            aliases.append({"result_path": str(path.relative_to(ROOT)), "reused_result_path": result.get("reused_result_path"), "counted_as_new_invalid_response": False})
            continue
        if result.get("status") != "invalid_judgment":
            continue
        units = []
        for label, packet_path, judgment_path, response_path, errors, call_id in invalid_units(path, result):
            packet = read(packet_path) if packet_path.exists() else None
            judgment = read(judgment_path) if judgment_path.exists() else None
            response = read(response_path) if response_path and response_path.exists() else {}
            choice = (response.get("choices") or [{}])[0]
            raw_content = (choice.get("message") or {}).get("content")
            try:
                matches = json.loads(raw_content) == judgment if judgment is not None else None
            except (ValueError, TypeError):
                matches = False
            raw_validator = validate_judgment(packet, judgment) if packet is not None and judgment is not None else errors
            normalized, transformations = normalize_shape(judgment) if judgment is not None else (None, [])
            normalized_errors = validate_judgment(packet, normalized) if packet is not None and normalized is not None else errors
            visual_errors, visual_corrections = validate_visual_contract(packet, normalized) if packet is not None and normalized is not None else (errors, [])
            locator_normalized, locator_transforms = normalize_locator_quotes(packet, normalized) if packet is not None and normalized is not None else (None, [])
            locator_errors, _ = validate_visual_contract(packet, locator_normalized) if packet is not None and locator_normalized is not None else (errors, [])
            if choice.get("finish_reason") == "length":
                normalized_errors = sorted(set([*normalized_errors, "judgment_output_token_limit"]))
                visual_errors = sorted(set([*visual_errors, "judgment_output_token_limit"]))
                locator_errors = sorted(set([*locator_errors, "judgment_output_token_limit"]))
            diagnostics = [diagnose_error(e, packet, judgment) if packet is not None and judgment is not None else
                           {"validator_error": e, "category": "output_token_budget" if "token" in e else "unparseable_or_missing_response", "criterion_id": None, "lossless_shape_repair_applied": False} for e in errors]
            destination = BASE / "normalized_copies" / (path.parent.name + "__" + label + ".json")
            if normalized is not None:
                write(destination, {"notice": "Posthoc contract diagnostic only; not a replacement primary score", "transform_version": TRANSFORM_VERSION,
                                    "transform_script_sha256": script_sha, "original_judgment_path": str(judgment_path.relative_to(ROOT)),
                                    "original_judgment_sha256": digest(judgment_path), "transformations": transformations, "judgment": normalized,
                                    "S2_visual_relation_corrections": visual_corrections, "S3_locator_transformations": locator_transforms,
                                    "S3_locator_normalized_judgment": locator_normalized})
            units.append({"unit": label, "call_id": call_id, "raw_status": "invalid_judgment",
                          "raw_recorded_validation_errors": errors, "raw_revalidated_errors": raw_validator,
                          "raw_errors_reproduced": raw_validator == errors,
                          "raw_response_matches_saved_judgment": matches, "raw_finish_reason": choice.get("finish_reason"),
                          "normalized_status": "contract_valid_after_lossless_shape_only" if not normalized_errors and normalized is not None else "still_invalid_or_unparseable",
                          "normalized_validation_errors": normalized_errors, "transformations": transformations, "diagnostics": diagnostics,
                          "posthoc_levels": {
                              "S1_shape_only": {"contract_valid": normalized is not None and not normalized_errors, "validation_errors": normalized_errors, "transform_count": len(transformations)},
                              "S2_shape_and_visual_relation": {"contract_valid": normalized is not None and not visual_errors, "validation_errors": visual_errors, "visual_relation_corrections": visual_corrections},
                              "S3_shape_visual_and_exact_locator_wrappers": {"contract_valid": locator_normalized is not None and not locator_errors, "validation_errors": locator_errors, "locator_transformations": locator_transforms}},
                          "normalized_copy_path": str(destination.relative_to(ROOT)) if normalized is not None else None,
                          "evidence_files": {str(p.relative_to(ROOT)): digest(p) for p in [packet_path, judgment_path, response_path] if p is not None and p.exists()},
                          "raw_reply_excerpt": raw_content if judgment is None else None})
        levels = {name: {"contract_valid": bool(units) and all(u["posthoc_levels"][name]["contract_valid"] for u in units),
                         "validation_errors": sorted({e for u in units for e in u["posthoc_levels"][name]["validation_errors"]})}
                  for name in ("S1_shape_only", "S2_shape_and_visual_relation", "S3_shape_visual_and_exact_locator_wrappers")}
        cases.append({"case_id": result.get("case_id"), "task_id": result.get("task_id"), "solver_run_id": result.get("solver_run_id"),
                      "judge_model": result.get("model"), "cohort": cohort(path, result), "result_path": str(path.relative_to(ROOT)),
                      "result_sha256": digest(path), "raw_status": result["status"],
                      "normalized_status": "contract_valid_after_lossless_shape_only" if units and all(u["normalized_status"] == "contract_valid_after_lossless_shape_only" for u in units) else "still_invalid_or_unparseable",
                      "posthoc_levels": levels, "units": units, "human_acceptance": None})
    categories = {}
    required_categories = {"schema_shape_nonempty_operative_string", "schema_shape_or_enum", "missing_operative_evidence_or_malformed_list",
                           "unverifiable_source_quote", "unverifiable_output_quote", "pass_with_partial_or_unavailable_coverage",
                           "visual_global_list_spans_artifacts_all_views_supplied", "visual_evidence_reference_or_delivery_mismatch", "output_token_budget"}
    for category in sorted(required_categories | {d["category"] for case in cases for unit in case["units"] for d in unit["diagnostics"]}):
        hit_cases = [c for c in cases if any(d["category"] == category for u in c["units"] for d in u["diagnostics"])]
        criterion_rows = {(c["result_path"], u["unit"], d.get("criterion_id")) for c in hit_cases for u in c["units"] for d in u["diagnostics"] if d["category"] == category}
        categories[category] = {"case_count": len(hit_cases), "criterion_row_count": len(criterion_rows), "case_paths": [c["result_path"] for c in hit_cases]}
    cohort_counts = {}
    for name in sorted({c["cohort"] for c in cases}):
        rows = [c for c in cases if c["cohort"] == name]
        cohort_counts[name] = {"raw_invalid_cases": len(rows), "contract_valid_after_shape_only": sum(c["normalized_status"] == "contract_valid_after_lossless_shape_only" for c in rows),
                               "still_invalid": sum(c["normalized_status"] != "contract_valid_after_lossless_shape_only" for c in rows),
                               "contract_valid_after_S2": sum(c["posthoc_levels"]["S2_shape_and_visual_relation"]["contract_valid"] for c in rows),
                               "contract_valid_after_S3": sum(c["posthoc_levels"]["S3_shape_visual_and_exact_locator_wrappers"]["contract_valid"] for c in rows)}
    report = {"schema": "evaluation-v2-posthoc-invalid-contract-audit-v1", "created_at": now(), "transform_version": TRANSFORM_VERSION,
              "transform_script_sha256": script_sha, "frozen_validator_sha256": digest(ROOT / "scripts/evaluation_v2_grading.py"),
              "prompt_contract_observation": "Prompt says enumerate operative_sections_inspected but does not explicitly require an array; validator requires list. Nonempty strings can contain substantive coverage evidence.",
              "prompt_instructions_sha256": hashlib.sha256(JUDGE_INSTRUCTIONS.encode()).hexdigest(),
              "transformation_policy": "Separate nested levels: S1 wraps nonempty operative strings in singleton lists verbatim; S2 maps global supplied visual IDs to each evidence artifact; S3 deletes only exact known locator+tab wrappers from a whole contiguous raw quote and verifies the entire remaining content stream. No verdict, coverage, severity, substantive quote content, whitespace, evidence ID, missing field or truncation repair.",
              "primary_scores_modified": False, "api_calls": 0, "human_acceptance": None,
              "all_result_snapshot_hashes": snapshot, "cohort_counts": cohort_counts, "cause_counts": categories, "cases": cases, "reused_aliases": aliases,
              "limits": ["A normalized contract-valid response is not established correct", "Shape validity does not establish actual inspection or source entailment", "Unverifiable quotes are traceability failures, not proof of factual errors in a solver output", "Missing visual coverage and pass/partial conflicts require substantive review", "Overlapping causes mean category counts do not sum to unique cases", "Snapshot excludes unfinished future results"]}
    write(BASE / "diagnostics.json", report)
    lines = ["Posthoc invalid-judgment contract audit", "Snapshot: " + report["created_at"], "", report["prompt_contract_observation"],
             "Separate levels: S1 exact nonempty string -> singleton list; S2 supplied views mapped to each evidence artifact; S3 exact known locator prefixes removed with entire ordered quote verified. All original invalid results remain unchanged.",
             "Contract validity is not accuracy, expert acceptance, or proof of actual inspection.", "", "Counts by cohort (raw invalid / contract-valid after shape-only / still invalid):"]
    for name, count in cohort_counts.items():
        lines.append(f"  {name}: {count['raw_invalid_cases']} / {count['contract_valid_after_shape_only']} / {count['still_invalid']}")
        lines.append(f"    Contract-valid after S2: {count['contract_valid_after_S2']}; after S3: {count['contract_valid_after_S3']}")
    lines.extend(["", "Overlapping causes (cases; criterion rows):"])
    for name, count in categories.items(): lines.append(f"  {name}: {count['case_count']}; {count['criterion_row_count']}")
    lines.extend(["", "Case details:"])
    for case in cases:
        codes = sorted({d["category"] for u in case["units"] for d in u["diagnostics"]})
        remaining = sorted({e for u in case["units"] for e in u["normalized_validation_errors"]})
        lines.append(f"  {case['result_path']}: {case['normalized_status']}; causes={', '.join(codes)}; remaining={', '.join(remaining) or 'none'}")
        lines.append("    S2=" + str(case["posthoc_levels"]["S2_shape_and_visual_relation"]["contract_valid"]) + "; S3=" + str(case["posthoc_levels"]["S3_shape_visual_and_exact_locator_wrappers"]["contract_valid"]) + "; final remaining=" + ", ".join(case["posthoc_levels"]["S3_shape_visual_and_exact_locator_wrappers"]["validation_errors"]))
    (BASE / "summary.txt").write_text("\n".join(lines) + "\n")
    return report


if __name__ == "__main__":
    report = audit()
    print(json.dumps({"cohort_counts": report["cohort_counts"], "cause_counts": {k: {x: v[x] for x in ("case_count", "criterion_row_count")} for k, v in report["cause_counts"].items()}}, indent=2))
