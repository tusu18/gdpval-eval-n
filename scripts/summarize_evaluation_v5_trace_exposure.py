"""Read-only snapshot of primary judge inspection traces; never infers accuracy.

Only this script's new JSON output is written. Ongoing cells can change during a
snapshot and are flagged. Secondary record-completion calls are not independent
primary judgments and are outside this trace summary.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/evaluation_v5"
MODELS = ("google/gemini-4-argon", "anthropic/claude-sonnet-5.5")
TOOLS = ("read_evidence", "search_evidence", "view_image", "native_structure", "numeric_table")
AXES = ("text", "formulas", "visual", "behavior")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def relative(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def load(path, provenance=None):
    path = Path(path)
    if not path.is_file():
        return None
    raw = path.read_bytes()
    if provenance is not None:
        provenance[relative(path)] = sha(raw)
    return json.loads(raw)


def interval_count(intervals, total):
    ordered = sorted((max(0, a), min(total, b)) for a, b in intervals if b > a)
    merged = []
    for start, end in ordered:
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return sum(b - a for a, b in merged), merged


def model_message(envelope):
    body = envelope.get("body") if isinstance(envelope, dict) else None
    choices = body.get("choices") if isinstance(body, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    return message if isinstance(message, dict) and envelope.get("status") == 200 else None


def error_category(reply):
    if not isinstance(reply, dict):
        return "malformed_local_reply"
    if reply.get("status") == "unsupported_format":
        return "unsupported_format"
    if "error" not in reply:
        return None
    text = str(reply["error"]).lower()
    if "at most4" in text or "at most 4" in text:
        return "image_batch_limit"
    if "unknown evidence" in text:
        return "unknown_evidence_id"
    if "unknown worksheet" in text:
        return "unknown_worksheet"
    if "unavailable" in text:
        return "unavailable_evidence"
    if "hash" in text or "outside" in text:
        return "evidence_integrity_or_path_rejection"
    return "other_tool_error"


def acknowledged_payload(request):
    """Extract supplied evidence metadata, never save text/image payloads."""
    tool_replies, initial, images = {}, [], []
    for message in (request or {}).get("messages", []):
        content = message.get("content")
        if message.get("role") == "tool" and isinstance(content, str):
            try:
                tool_replies[message.get("tool_call_id")] = json.loads(content)
            except ValueError:
                pass
        elif message.get("role") == "user" and isinstance(content, str) and '"initial_extractions"' in content:
            try:
                decoded = json.loads(content)
                if isinstance(decoded, dict):
                    initial.extend(decoded.get("initial_extractions") or [])
            except ValueError:
                pass
        elif message.get("role") == "user" and isinstance(content, list):
            pending_view = None
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    match = re.match(r"Actual recorded image (\S+):", part.get("text", ""))
                    pending_view = match.group(1) if match else None
                elif part.get("type") == "image_url":
                    url = part.get("image_url")
                    url = url.get("url") if isinstance(url, dict) else url
                    if pending_view and isinstance(url, str) and url.startswith("data:image/"):
                        images.append(pending_view)
                    pending_view = None
    return tool_replies, initial, images


def cell_summary(task, model, ledger):
    ident = task["task_id"] + "__" + model.replace("/", "_")
    folder = OUT / "judges" / ident
    provenance = {}
    packet = load(task["packet_path"], provenance)
    result = load(folder / "result.json", provenance) or {}
    exposure = load(folder / "evidence-exposure.json", provenance) or {}
    assessment = load(folder / "assessment.json", provenance)
    validation = load(folder / "validation.json", provenance) or {}
    final = load(folder / "final-response.json", provenance) or {}
    calls = sorted(ledger.get("v5:" + ident + ":", []), key=lambda r: r["created_at"])
    ack = None
    # Last valid model-message request has the accumulated tool history. A mere
    # HTTP200/whitespace body does not establish model receipt or a judgment.
    for record in reversed(calls):
        path = ROOT / "output/evaluation_v2/calls" / record["id"] / "response.json"
        envelope = load(path)
        if model_message(envelope) is not None:
            ack = record
            load(path, provenance)
            break
    request = load(ROOT / "output/evaluation_v2/calls" / ack["id"] / "request.json", provenance) if ack else None
    replies, initial, image_ids = acknowledged_payload(request)
    acknowledged_views = set(image_ids)
    events = exposure.get("tool_events") or []
    tool_stats = {name: {"attempts": 0, "successful_local_replies": 0, "errors_or_unsupported": 0,
                         "replies_in_acknowledged_model_request": 0} for name in TOOLS}
    error_types = Counter()
    error_records = []
    for event in events:
        name = event.get("name", "unknown")
        stats = tool_stats.setdefault(name, {"attempts": 0, "successful_local_replies": 0,
                                            "errors_or_unsupported": 0, "replies_in_acknowledged_model_request": 0})
        stats["attempts"] += 1
        error = error_category(event.get("reply"))
        stats["errors_or_unsupported" if error else "successful_local_replies"] += 1
        if event.get("tool_call_id") in replies:
            stats["replies_in_acknowledged_model_request"] += 1
        if error:
            error_types[name + ":" + error] += 1
            error_records.append({"tool_call_id": event.get("tool_call_id"), "name": name, "category": error,
                                  "turn": event.get("turn")})

    evidence = packet["source_documents"] + packet["artifacts"]
    by_evidence = {e["id"]: e for e in evidence}
    ranges = defaultdict(list)
    range_flags = []
    text_replies = list(initial)
    for event in events:
        if event.get("name") == "read_evidence" and event.get("tool_call_id") in replies:
            text_replies.append(replies[event["tool_call_id"]])
    for reply in text_replies:
        if not isinstance(reply, dict) or reply.get("id") not in by_evidence:
            continue
        identity = reply["id"]
        start, end, total = reply.get("offset"), reply.get("end"), reply.get("total_chars")
        expected = by_evidence[identity]["text_chars"]
        if (type(start) is not int or type(end) is not int or type(total) is not int
                or not 0 <= start <= end <= total or total != expected
                or not isinstance(reply.get("text"), str) or len(reply["text"]) != end - start
                or reply.get("extraction_sha256") != by_evidence[identity]["extraction_sha256"]):
            range_flags.append({"evidence_id": identity, "reason": "offset/length/total/hash metadata inconsistent"})
            continue
        ranges[identity].append((start, end))
    text_coverage = []
    artifact_ids = {e["id"] for e in packet["artifacts"]}
    for e in evidence:
        covered, merged = interval_count(ranges[e["id"]], e["text_chars"])
        text_coverage.append({"evidence_id": e["id"], "role": "artifact" if e["id"] in artifact_ids else "source",
                              "extraction_sha256": e["extraction_sha256"], "extracted_text_chars": e["text_chars"],
                              "acknowledged_read_interval_union_chars": covered, "read_intervals": merged,
                              "whole_extracted_text_supplied": covered == e["text_chars"] if e["text_chars"] else None,
                              "extraction_full_text_available_flag": e.get("full_text_available")})
    available_packet_views = {v["id"] for e in evidence for v in e["views"] if v.get("available")}
    available_artifact_views = {v["id"] for e in packet["artifacts"] for v in e["views"] if v.get("available")}

    terminal = result.get("status") not in (None, "running")
    final_record = ledger_record = None
    if final.get("call_id"):
        final_path = ROOT / "output/evaluation_v2/calls" / final["call_id"]
        final_envelope = load(final_path / "response.json", provenance)
        final_record = model_message(final_envelope)
        ledger_record = next((r for r in calls if r["id"] == final["call_id"]), None)
    final_content = final.get("content")
    genuine_final = (terminal and final_record is not None and ledger_record is not None
                     and isinstance(final_content, str) and bool(final_content.strip())
                     and final_record.get("content") == final_content)
    parsed = None
    if genuine_final:
        try:
            parsed = json.loads(final_content)
        except ValueError:
            pass
    actual_assessment = isinstance(parsed, dict) and isinstance(parsed.get("criteria"), list) and parsed == assessment
    valid = (actual_assessment and result.get("status") == "graded" and result.get("contract_valid") is True
             and validation.get("contract_valid") is True and parsed.get("task_id") == task["task_id"]
             and result.get("packet_sha256") == task["packet_sha256"]
             and parsed.get("rubric_sha256") == packet["rubric_sha256"])
    if valid:
        record_state = "valid_primary_model_assessment"
    elif actual_assessment:
        record_state = "model_assessment_with_invalid_contract"
    elif genuine_final:
        record_state = "model_final_response_without_valid_assessment_json"
    elif terminal and final and final_record is None:
        record_state = "provider_response_without_model_message"
    else:
        record_state = "no_completed_model_assessment"

    criteria = parsed.get("criteria", []) if actual_assessment else []
    coverage_counts = {axis: Counter() for axis in AXES}
    criterion_records = []
    criterion_map = {str(c.get("criterion_id", c.get("id"))): c for c in packet["criteria"]}
    for criterion in criteria:
        if not isinstance(criterion, dict):
            continue
        coverage = criterion.get("coverage") or {}
        if not isinstance(coverage, dict):
            coverage = {}
        for axis in AXES:
            coverage_counts[axis][str(coverage.get(axis, "missing"))] += 1
        cited = criterion.get("inspected_view_ids")
        cited = [v for v in cited if isinstance(v, str)] if isinstance(cited, list) else []
        cid = str(criterion.get("criterion_id"))
        requirement = criterion_map.get(cid, {})
        required = requirement.get("required_visual_view_ids", requirement.get("required_view_ids"))
        explicit_mapping = isinstance(required, list) and bool(required) and all(isinstance(v, str) for v in required)
        criterion_records.append({"criterion_id": cid, "declared_coverage": coverage,
            "declared_inspected_view_ids": cited,
            "cited_views_not_in_acknowledged_request": sorted(set(cited) - acknowledged_views),
            "all_cited_views_supplied_with_model_response": set(cited) <= acknowledged_views if cited else None,
            "declared_visual_complete_without_any_cited_acknowledged_view": coverage.get("visual") == "complete" and not (set(cited) & acknowledged_views),
            "explicit_required_view_map_present": explicit_mapping,
            "required_views_supplied": set(required) <= acknowledged_views if explicit_mapping else None,
            "all_requirement_relevant_visuals_inspected": None,
            "interpretation": "Trace establishes delivery of listed views, not cognitive inspection. No complete criterion-to-view map is inferred from prose or tool counts."})

    changed = [p for p, h in provenance.items() if not (ROOT / p).is_file() or sha((ROOT / p).read_bytes()) != h]
    return {"cell_id": ident, "task_id": task["task_id"], "model": model, "cohort": task["cohort"],
        "rubric_format": task["rubric_format"], "occupation": task["occupation"], "raw_runner_status": result.get("status", "not_started"),
        "record_state": record_state, "actual_model_final_response": genuine_final,
        "actual_model_assessment_json": actual_assessment, "valid_primary_model_assessment": valid,
        "snapshot_stable": not changed, "files_changed_during_cell_snapshot": changed,
        "physical_call_count_observed": len(calls), "latest_acknowledged_call_id": ack["id"] if ack else None,
        "tool_stats": tool_stats, "tool_error_category_counts": dict(error_types), "tool_error_records": error_records,
        "images": {"trace_delivery_records": len(exposure.get("delivered_images") or []),
            "trace_unique_delivered_view_ids": sorted({r.get("view_id") for r in exposure.get("delivered_images", []) if r.get("view_id")}),
            "pending_view_ids": [r.get("view_id") for r in exposure.get("pending_images", [])],
            "image_parts_in_latest_acknowledged_request": len(image_ids),
            "unique_views_in_latest_acknowledged_request": sorted(acknowledged_views),
            "packet_available_view_count": len(available_packet_views), "artifact_available_view_count": len(available_artifact_views),
            "available_artifact_views_supplied": len(available_artifact_views & acknowledged_views),
            "all_available_artifact_views_supplied": available_artifact_views <= acknowledged_views if available_artifact_views else None,
            "all_available_packet_views_supplied": available_packet_views <= acknowledged_views if available_packet_views else None,
            "interpretation": "Successful model-message response acknowledges the request containing these image parts. Delivery does not prove the judge inspected or correctly interpreted them; images were downscaled to1024px."},
        "extracted_text_exposure": text_coverage, "text_interval_metadata_flags": range_flags,
        "declared_coverage_counts": {k: dict(v) for k, v in coverage_counts.items()}, "criterion_trace_records": criterion_records,
        "criteria_with_explicit_required_view_map": sum(r["explicit_required_view_map_present"] for r in criterion_records),
        "provenance": {"paths_and_sha256": provenance, "exposure_path": relative(folder / "evidence-exposure.json"),
                       "result_path": relative(folder / "result.json"), "packet_path": relative(task["packet_path"])}}


def aggregate(cells, **identity):
    stable = [c for c in cells if c["snapshot_stable"]]
    tools = {name: Counter() for name in TOOLS}
    errors = Counter()
    coverage = {axis: Counter() for axis in AXES}
    coverage_valid = {axis: Counter() for axis in AXES}
    for cell in stable:
        for name, stats in cell["tool_stats"].items():
            tools.setdefault(name, Counter()).update(stats)
        errors.update(cell["tool_error_category_counts"])
        for axis in AXES:
            coverage[axis].update(cell["declared_coverage_counts"][axis])
            if cell["valid_primary_model_assessment"]:
                coverage_valid[axis].update(cell["declared_coverage_counts"][axis])
    criteria = [r for c in stable for r in c["criterion_trace_records"]]
    return {**identity, "planned_cells": len(cells), "stable_snapshot_cells": len(stable),
        "changed_during_snapshot_cells_excluded": len(cells) - len(stable),
        "record_states": dict(Counter(c["record_state"] for c in stable)),
        "raw_runner_statuses": dict(Counter(c["raw_runner_status"] for c in stable)),
        "actual_model_final_responses": sum(c["actual_model_final_response"] for c in stable),
        "actual_model_assessment_json_records": sum(c["actual_model_assessment_json"] for c in stable),
        "valid_primary_model_assessment_records": sum(c["valid_primary_model_assessment"] for c in stable),
        "tool_stats": {k: dict(v) for k, v in tools.items()}, "tool_error_category_counts": dict(errors),
        "unique_acknowledged_view_count_summed_per_cell": sum(len(c["images"]["unique_views_in_latest_acknowledged_request"]) for c in stable),
        "available_artifact_view_count_summed_per_cell": sum(c["images"]["artifact_available_view_count"] for c in stable),
        "available_artifact_views_supplied_summed_per_cell": sum(c["images"]["available_artifact_views_supplied"] for c in stable),
        "cells_with_all_available_artifact_views_supplied": sum(c["images"]["all_available_artifact_views_supplied"] is True for c in stable),
        "cells_with_available_artifact_views": sum(c["images"]["artifact_available_view_count"] > 0 for c in stable),
        "declared_coverage_counts_all_actual_assessment_json": {k: dict(v) for k, v in coverage.items()},
        "declared_coverage_counts_valid_primary_only": {k: dict(v) for k, v in coverage_valid.items()},
        "criteria_citing_views_not_acknowledged": sum(bool(r["cited_views_not_in_acknowledged_request"]) for r in criteria),
        "criteria_declaring_visual_complete_without_cited_acknowledged_view": sum(r["declared_visual_complete_without_any_cited_acknowledged_view"] for r in criteria),
        "criteria_with_explicit_required_view_map": sum(r["explicit_required_view_map_present"] for r in criteria),
        "all_required_visuals_inspected_estimate": None}


def main():
    started = datetime.now(timezone.utc).isoformat()
    inventory_path = OUT / "packet-inventory.json"
    inventory_raw = inventory_path.read_bytes()
    inventory = json.loads(inventory_raw)
    ledger = defaultdict(list)
    for path in (ROOT / "output/evaluation_v2/calls").glob("*/reservation.json"):
        record = load(path)
        if record.get("scope") == "judge_v5_crossfamily" and record.get("label", "").startswith("v5:"):
            prefix = record["label"].rsplit("turn", 1)[0]
            ledger[prefix].append(record)
    cells = [cell_summary(task, model, ledger) for task in inventory["tasks"] for model in MODELS]
    groups = []
    for model in MODELS:
        for cohort in sorted({t["cohort"] for t in inventory["tasks"]}):
            selected = [c for c in cells if c["model"] == model and c["cohort"] == cohort]
            groups.append(aggregate(selected, model=model, cohort=cohort))
    result = {"schema": "evaluation-v5-primary-trace-exposure-summary-1", "snapshot_started_at": started,
        "snapshot_completed_at": datetime.now(timezone.utc).isoformat(), "inventory_sha256": sha(inventory_raw),
        "summary_script_path": relative(__file__), "summary_script_sha256": sha(Path(__file__).read_bytes()),
        "scope": "80 planned primary Gemini/Claude cells on40existing outputs; current resumed traces retain prior history. Secondary record-completion calls excluded.",
        "method": "Read-only trace snapshot. Tool events describe local invocations; acknowledgment requires the reply/image to occur in a saved request with a genuine model-message response. Full extracted-text exposure uses the union of exact validated character intervals, not tool-call counts. Search snippets do not count toward full-text intervals.",
        "limitations": ["No semantic pass/fail, judge accuracy or model ranking is inferred from inspection counts.",
            "Supplying an image or text does not establish cognitive inspection, correctness or native behavior execution.",
            "Full extracted-text exposure is not full-file coverage; extraction may omit content, and images are downscaled.",
            "Available rendered views need not exhaust all views relevant to a requirement. Required visual completeness is unknown without a frozen explicit criterion-to-view mapping.",
            "Coverage fields are judge declarations; valid and invalid assessments remain separate.",
            "Active execution can change cells during the snapshot. Detected changing cells are excluded from aggregates; the snapshot is not a transactional global freeze."],
        "overall": aggregate(cells),
        "by_model": [aggregate([c for c in cells if c["model"] == model], model=model) for model in MODELS],
        "by_model_and_cohort": groups,
        "by_model_and_record_state": [aggregate([c for c in cells if c["model"] == model and c["record_state"] == state], model=model, record_state=state)
                                     for model in MODELS for state in sorted({c["record_state"] for c in cells if c["model"] == model})],
        "cells": cells}
    destination = OUT / "trace-exposure-summary.json"
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2) + "\n")
    temporary.replace(destination)
    print(json.dumps({"path": str(destination), "planned_cells": len(cells),
                      "valid_primary_records": result["overall"]["valid_primary_model_assessment_records"],
                      "model_final_responses": result["overall"]["actual_model_final_responses"],
                      "changed_snapshot_cells": result["overall"]["changed_during_snapshot_cells_excluded"],
                      "required_view_mapped_criteria": result["overall"]["criteria_with_explicit_required_view_map"]}))


if __name__ == "__main__":
    main()
