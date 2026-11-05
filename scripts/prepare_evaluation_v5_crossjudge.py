"""Offline, author-hidden evidence bundles for regrading the 40 original tasks.

This script never calls a model, changes a submitted artifact, or imports judge
verdicts/human labels into a packet. The private inventory records baseline paths
for later comparison; packet.json is the judge-facing evidence catalogue.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/evaluation_v5"


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text() == payload:
        return
    path.write_text(payload)


def copy_verified(source, target, expected=None):
    source, target = Path(source), Path(target)
    actual = sha(source)
    if expected and actual != expected:
        raise ValueError(f"Input hash differs from recorded hash: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha(target) != actual:
            raise ValueError(f"Refusing to replace different prepared evidence: {target}")
    else:
        shutil.copyfile(source, target)
    return actual


def clean_extraction(extraction, identity):
    # Only native content and extraction limitations; no prior review metadata.
    allowed = ("kind", "sha256", "full_text_available", "units", "text", "extraction_limits")
    value = {key: copy.deepcopy(extraction[key]) for key in allowed if key in extraction}
    value["id"] = identity
    return value


def register_evidence(folder, identity, native, extraction, views, *, filename=None, external=None):
    native = Path(native)
    dest = folder / "evidence" / (identity + native.suffix.lower())
    digest = copy_verified(native, dest, extraction.get("sha256"))
    extracted = clean_extraction(extraction, identity)
    if extracted.get("sha256") and extracted["sha256"] != digest:
        raise ValueError("Extraction belongs to a different native file")
    extracted["sha256"] = digest
    extract_path = folder / "evidence" / (identity + ".extraction.json")
    write(extract_path, extracted)
    view_records = []
    for index, view in enumerate(views, 1):
        source = Path(view["path"])
        record = {"id": f"{identity}-V{index}", "label": view.get("label", view.get("locator", f"View {index}"))}
        if source.is_file():
            target = folder / "views" / f"{identity}-V{index}{source.suffix.lower()}"
            record.update(path=str(target), sha256=copy_verified(source, target, view.get("sha256")), available=True)
        else:
            record.update(path=None, sha256=None, available=False, limitation="Recorded render unavailable")
        view_records.append(record)
    record = {
        "id": identity, "kind": extracted.get("kind", native.suffix.lstrip(".")),
        "sha256": digest, "native_path": str(dest), "extraction_path": str(extract_path),
        "extraction_sha256": sha(extract_path), "full_text_available": extracted.get("full_text_available") is True,
        "text_chars": len(extracted.get("text", "")), "unit_count": len(extracted.get("units", [])),
        "views": view_records,
    }
    if filename:
        record["original_filename"] = filename
    if external:
        record["external_provenance"] = external
    return record


def base_packet(task, rubric_format, rubric, rubric_hash, criteria):
    return {
        "schema": "evaluation-v5-author-hidden-evidence-catalogue-1",
        "task_id": task["task_id"], "occupation": task["occupation"],
        "original_prompt": task["prompt"],
        "original_prompt_sha256": hashlib.sha256(task["prompt"].encode()).hexdigest(),
        "task_today": "2026-11-05", "rubric_format": rubric_format,
        "rubric": rubric, "rubric_sha256": rubric_hash, "criteria": criteria,
        "source_documents": [], "artifacts": [],
        "blinding": {"author_identity_provided": False, "prior_judge_results_provided": False, "human_labels_provided": False,
                     "limit": "Content can reveal identity. Local file metadata is not proof of true anonymization."},
        "coverage": {"evidence_mode": "Full native extractions and recorded views are available through neutral IDs; not all evidence has been inspected merely by listing it.",
                     "behavior_execution": "not_executed_by_this_packet_builder",
                     "prior_judge_behavior_tests_included": False,
                     "visual_policy": "Only claim visual inspection for actual image content supplied to the judge; filenames are not visual evidence.",
                     "native_policy": "Native bytes are available for separately logged read-only inspection or disposable-copy tests. Formula text alone does not prove recalculated behavior."},
    }


def prepare_inapp(task, version, folder):
    path = ROOT / f"output/evaluation_v{version}/judge-packets" / task["task_id"] / "packet.json"
    source = read(path)
    if source["original_prompt"] != task["prompt"]:
        raise ValueError("Original prompt differs from selected task")
    packet = base_packet(task, f"v{version}", source["rubric"], source["rubric_sha256"], source["rubric"]["criteria"])
    for key in ("global_rules", "severity_scale", "aggregation", "judgment_record_contract"):
        if key in source:
            packet[key] = copy.deepcopy(source[key])
    for field, target in (("sources", "source_documents"), ("artifacts", "artifacts")):
        for record in source[field]:
            external = {k: record[k] for k in ("url", "title", "retrieved_at", "provenance") if k in record}
            packet[target].append(register_evidence(folder, record["id"], record["path"], read(record["extraction"]), record.get("views", []),
                                                     filename=record.get("original_name", record.get("submitted_filename")), external=external or None))
    baseline = ROOT / f"output/evaluation_v{version}/assessments" / (task["task_id"] + ".json")
    return packet, {"selected_run_id": f"v{version}-in-app/{task['task_id']}", "selected_solver_requested_model": "gpt-6.1-sol",
                    "original_packet_path": str(path), "original_packet_sha256": sha(path),
                    "astra_baseline": {"available": baseline.is_file(), "path": str(baseline), "sha256": sha(baseline),
                                       "comparison_limit": "Same frozen criterion content and artifact bytes, but earlier Astra had agentic inspection capabilities. Match evidence/capabilities before claiming a judge-family effect."}}


def prepare_v2(task, row, folder):
    from grade_evaluation_v2 import prepare_run
    candidates = []
    for run in row.get("runs", []):
        if run.get("model") != "openai/gpt-6.1-sol" or run.get("status") != "submitted":
            continue
        run_path = ROOT / "output/evaluation_v2/runs" / run["run_id"]
        result = read(run_path / "result.json")
        date = result.get("completed_at") or result.get("ended_at") or result.get("started_at") or ""
        candidates.append((date, run["run_id"], run_path))
    if not candidates:
        raise ValueError("No submitted primary-model output for selected original task")
    _, run_id, run_dir = max(candidates)
    rubrics_path = ROOT / "data/evaluation_v2/rubrics.json"
    rubrics = read(rubrics_path)
    effective = {t["task_id"]: t for t in map(json.loads, (ROOT / "data/evaluation_v2/effective-inputs.jsonl").read_text().splitlines()) if t}
    prepared, private, _, _ = prepare_run(run_dir, effective[task["task_id"]], rubrics)
    state = read(run_dir / "workspace/state.json")
    packet = base_packet(task, "v2", {"task_id": task["task_id"], "criteria": rubrics[task["task_id"]]}, sha(rubrics_path), rubrics[task["task_id"]])
    prompt = next(x for x in prepared["source_documents"] if x["id"] == "original_request")["text"]
    if prompt != task["prompt"]:
        raise ValueError("v2 prompt changed relative to original selected task")
    for extraction in prepared["source_documents"]:
        if extraction["id"] == "original_request":
            continue
        entry = private["sources"][extraction["id"]]
        views = state.get("source_views", {}).get(entry["name"], [])
        packet["source_documents"].append(register_evidence(folder, extraction["id"], entry["path"], extraction, views, filename=entry["name"]))
    submitted = {a["filename"]: a for a in state["submitted"]}
    for extraction in prepared["artifacts"]:
        entry = private["artifacts"][extraction["id"]]
        artifact = submitted[entry["name"]]
        packet["artifacts"].append(register_evidence(folder, extraction["id"], entry["path"], extraction, artifact.get("previews", []), filename=entry["name"]))
    packet["coverage"]["original_source_access_notes"] = prepared["inspection"].get("source_access_notes", "")
    packet["coverage"]["original_full_sources_flag"] = prepared["coverage"]["full_sources"]
    return packet, {"selected_run_id": run_id, "selected_solver_requested_model": "openai/gpt-6.1-sol",
                    "selection_rule": "Latest completed submitted GPT-6.1 Sol run; primary, recovery or adapter repair. No output quality or judge verdict used.",
                    "eligible_submitted_runs": len(candidates),
                    "astra_baseline": {"available": False, "path": None, "sha256": None,
                                       "comparison_limit": "No existing Astra assessment for this selected original-task output. Do not count as a paired Astra comparison."}}


def evidence_read(packet, evidence_id, offset=0, limit=12000):
    """Bounded text retrieval. Exact offset/coverage remain explicit, no silent truncation."""
    if not isinstance(offset, int) or offset < 0 or not isinstance(limit, int) or not 1 <= limit <= 40000:
        raise ValueError("offset >=0 and limit 1..40000 required")
    record = next((r for r in packet["source_documents"] + packet["artifacts"] if r["id"] == evidence_id), None)
    if record is None:
        raise ValueError("Unknown evidence ID")
    extraction = read(record["extraction_path"])
    text = extraction.get("text", "")
    end = min(offset + limit, len(text))
    return {"id": evidence_id, "offset": offset, "end": end, "total_chars": len(text), "text": text[offset:end],
            "has_more": end < len(text), "full_text_available": record["full_text_available"],
            "extraction_sha256": record["extraction_sha256"]}


def public_catalogue(packet):
    """Local paths stay out of API messages; a tool runner resolves neutral IDs."""
    value = copy.deepcopy(packet)
    for record in value["source_documents"] + value["artifacts"]:
        record.pop("native_path", None)
        record.pop("extraction_path", None)
        for view in record["views"]:
            view.pop("path", None)
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", help="Optional task prefix for preparation checks")
    args = parser.parse_args()
    report_path = ROOT / "output/evaluation_v4/report.json"
    report = read(report_path)
    roster = [json.loads(line) for line in (ROOT / "data/evaluation_v4/tasks.jsonl").read_text().splitlines() if line.strip()]
    tasks = {t["task_id"]: t for t in roster}
    records = []
    for row in report["tasks"]:
        tid = row["task_id"]
        if args.task and not tid.startswith(args.task):
            continue
        task = tasks[tid]
        folder = OUT / "packets" / tid
        version = 4 if row["status"] == "not_run" else (3 if "v3" in row["cohort"] else 2)
        # Cohort is authoritative: report status fields preserve pre-execution values.
        if "v4 in-app" in row["cohort"]:
            version = 4
        packet, private = prepare_inapp(task, version, folder) if version in (3, 4) else prepare_v2(task, row, folder)
        path = folder / "packet.json"
        write(path, packet)
        write(folder / "catalogue.json", public_catalogue(packet))
        evidence = packet["source_documents"] + packet["artifacts"]
        record = {"task_id": tid, "occupation": task["occupation"], "cohort": row["cohort"], "rubric_format": packet["rubric_format"],
                  "packet_path": str(path), "packet_sha256": sha(path), "catalogue_path": str(folder / "catalogue.json"),
                  "criteria_count": len(packet["criteria"]), "source_count": len(packet["source_documents"]), "artifact_count": len(packet["artifacts"]),
                  "text_chars": sum(e["text_chars"] for e in evidence), "view_count": sum(len(e["views"]) for e in evidence),
                  "available_view_count": sum(v["available"] for e in evidence for v in e["views"]),
                  "artifact_hashes": {e["id"]: e["sha256"] for e in packet["artifacts"]}, **private}
        records.append(record)
    if args.task:
        destination = OUT / f"packet-inventory-{args.task}.json"
    else:
        if len(records) != 40 or len({r["task_id"] for r in records}) != 40:
            raise ValueError("Expected exactly 40 original task bundles")
        destination = OUT / "packet-inventory.json"
    inventory = {"schema": "evaluation-v5-crossjudge-packet-inventory-1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
                 "private_routing_only": True, "send_inventory_to_judge": False,
                 "selection": "Existing frozen forty-task roster; one latest submitted primary-model bundle per original task, including prior recoveries. No solver reruns; alternate solver outputs excluded.",
                 "source_report_path": str(report_path), "source_report_sha256": sha(report_path),
                 "task_count": len(records), "astra_baseline_task_count": sum(r["astra_baseline"]["available"] for r in records),
                 "cohort_counts": dict(Counter(r["rubric_format"] for r in records)), "criterion_count": sum(r["criteria_count"] for r in records),
                 "api_calls": 0, "new_human_labels": 0, "tasks": records}
    write(destination, inventory)
    print(json.dumps({k: inventory[k] for k in ("task_count", "astra_baseline_task_count", "cohort_counts", "criterion_count", "api_calls")}, indent=2))
    print(json.dumps({"total_text_chars": sum(r["text_chars"] for r in records), "total_views": sum(r["view_count"] for r in records), "inventory": str(destination)}))


if __name__ == "__main__":
    main()
