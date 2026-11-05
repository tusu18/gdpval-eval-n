"""Budgeted original-task grading; preparation is offline unless --execute.

No gold or human labels are imported. All submitted bytes and source files are
hash-checked. Native image batches preserve uncertainty and every raw verdict.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from evaluation_v2_grading import build_packet, judge_messages, parse_judgment, summarize_judgment
from evaluation_v2_workspace import extract_native
from run_evaluation_v2 import Client, BudgetStop, ROOT, OUT, read, write, digest, canonical, now, image_part

RUBRICS = ROOT / "data/evaluation_v2/rubrics.json"
INPUTS = ROOT / "data/evaluation_v2/effective-inputs.jsonl"
INPUT_MANIFEST = ROOT / "data/evaluation_v2/effective-inputs-manifest.json"
MAX_IMAGES_PER_CALL = 16


def checked_file(path, expected=None, within=None):
    path = Path(path).resolve()
    if within and not path.is_relative_to(Path(within).resolve()):
        raise ValueError("File lies outside the recorded workspace")
    if not path.is_file():
        raise ValueError("Recorded file unavailable: " + path.name)
    actual = digest(path)
    if expected and expected != actual:
        raise ValueError("Recorded file hash changed: " + path.name)
    return path


def freeze_grader(execute=False):
    paths = [Path(__file__), ROOT / "scripts/evaluation_v2_grading.py", ROOT / "config/evaluation_v2_grader.json", RUBRICS, INPUTS, INPUT_MANIFEST]
    primary = OUT / "freeze.json"
    if primary.exists():
        paths.append(primary)
    calibration = ROOT / "data/evaluation_v2/development-calibration.json"
    if calibration.exists():
        paths.append(calibration)
    record = {"schema": "evaluation-v2-grader-execution-freeze-v1", "files": {str(p.relative_to(ROOT)): digest(p) for p in paths},
              "request_settings": {"max_tokens": 8000, "reasoning_effort": "medium", "automatic_retries": 0, "max_images_per_call": MAX_IMAGES_PER_CALL},
              "execution_authorization": "User explicitly authorized evaluation and grading within the confirmed remaining API budget; --execute is required. Prepared config execution_enabled=false is overridden only by that explicit execution flag.",
              "created_at": now()}
    target = OUT / "grader-execution-freeze.json"
    if target.exists():
        old = read(target)
        if old["files"] != record["files"] or old["request_settings"] != record["request_settings"]:
            raise ValueError("Grader inputs changed since freeze; retain prior results and create a separate protocol version")
        return old
    if execute:
        write(target, record)
    return record


def _extract(path, identity):
    item = extract_native(path, identity)
    # A successful parser does not make an empty scan a complete text source.
    if not item.get("units"):
        item["full_text_available"] = False
        item["extraction_limits"] = "No text units extracted; visual/OCR evidence is required."
    return item


def _source_gap(task):
    manifest = read(INPUT_MANIFEST)
    notes = manifest.get("grader_only_coverage_gaps", {}).get("task_notes", {})
    note = notes.get(task["task_id"], "")
    # These flags express the frozen source-access audit, not model outcomes.
    incomplete = task["task_id"] in {"5349dd7b-bf0a-4544-9a17-75b7013767e6", "a4a9195c-5ebe-4b8d-a0c2-4a6b7a49da8b"}
    return incomplete, note


def prepare_run(run_dir, task, rubrics):
    """Return base packet, private identity map, image descriptors, run record."""
    run_dir = Path(run_dir)
    result = read(run_dir / "result.json")
    if result.get("status") != "submitted":
        return None, None, [], result
    workspace = run_dir / "workspace"
    state = read(workspace / "state.json")
    submitted = result.get("submission") or state.get("submitted")
    if not submitted:
        return None, None, [], result
    sources, artifacts, images, inspections = [], [], [], []
    private = {"solver_run_id": run_dir.name, "solver_model": result.get("model"), "sources": {}, "artifacts": {}}
    expected_sources = []
    expected_native_hashes = {r.get("sha256") for r in task.get("references", [])}
    actual_source_hashes = {r.get("sha256") for r in state["sources"].values()}
    if expected_native_hashes != actual_source_hashes:
        raise ValueError("Workspace sources differ from the frozen effective task references")
    for index, (name, row) in enumerate(sorted(state["sources"].items()), 1):
        path = checked_file(row["path"], row["sha256"])
        identity = f"S{index:02d}{path.suffix.lower()}"
        sources.append(_extract(path, identity)); expected_sources.append(identity)
        private["sources"][identity] = {"name": name, "path": str(path), "sha256": row["sha256"]}
    actual_formats = []
    for index, row in enumerate(sorted(submitted, key=lambda x: x["filename"]), 1):
        path = checked_file(row["path"], row["sha256"], workspace)
        identity = f"A{index:02d}{path.suffix.lower()}"
        artifacts.append(_extract(path, identity)); actual_formats.append(path.suffix.lower()[1:])
        private["artifacts"][identity] = {"name": row["filename"], "path": str(path), "sha256": row["sha256"]}
        metadata = row.get("metadata") or {}
        inspections.append({"artifact_id": identity, "kind": row.get("kind"), "rendered_views": len(row.get("previews", [])),
                            "solver_inspected_latest_revision": row.get("inspected"), "solver_received_views": row.get("viewed_pages", []),
                            "recalculation_engine": metadata.get("recalculation_engine"), "formula_error_scan": metadata.get("formula_error_scan"),
                            "recalculated_sheets": metadata.get("sheets"), "slide_count": metadata.get("slide_count")})
        for page, view in enumerate(row.get("previews", []), 1):
            image_id = identity + f":view:{page}"
            try:
                preview = checked_file(view["path"], within=workspace)
                images.append({"id": image_id, "artifact_id": identity, "locator": view.get("label") or f"view:{page}",
                               "path": str(preview), "sha256": digest(preview), "available": True})
            except ValueError as error:
                images.append({"id": image_id, "artifact_id": identity, "locator": view.get("label") or f"view:{page}",
                               "available": False, "error": str(error)})
    contract = task.get("contract", {})
    required_formats = set(contract.get("required_formats", []))
    incomplete, gap_note = _source_gap(task)
    inspection = {"engineering_checks": {"actual_file_count": len(artifacts), "actual_formats": actual_formats,
                   "required_formats_present": required_formats <= set(actual_formats),
                   "minimum_file_count_pass": len(artifacts) >= (contract.get("min_files") or 0),
                   "role_page_sheet_semantics": "Judge assesses against original request; counts alone do not prove role compliance",
                   "native_observations": inspections},
                  "source_access_notes": gap_note,
                  "observations": [{k: v for k, v in image.items() if k != "path"} | {"image_supplied": False} for image in images],
                  "limitations": "Rendered views and formula readback are inspection evidence, not human acceptance. Some source visuals may not be represented by text extraction."}
    packet = build_packet(task, sources, artifacts, rubrics[task["task_id"]], inspection,
                          expected_source_ids=expected_sources, source_coverage_confirmed=not incomplete)
    return packet, private, images, result


def image_batches(packet, images):
    """Every available output view is scheduled; missing views remain explicit."""
    usable = [x for x in images if x.get("available")]
    groups = [usable[i:i + MAX_IMAGES_PER_CALL] for i in range(0, len(usable), MAX_IMAGES_PER_CALL)] or [[]]
    batches = []
    for number, group in enumerate(groups, 1):
        part = copy.deepcopy(packet)
        selected = {x["id"] for x in group}
        for obs in part["inspection"].get("observations", []):
            obs["image_supplied"] = obs["id"] in selected
        part["inspection"]["visual_coverage"] = {
            "batch": number, "batch_count": len(groups), "views_supplied_this_call": sorted(selected),
            "total_views_recorded": len(images), "missing_views": [x["id"] for x in images if not x.get("available")],
            "all_output_views_supplied_in_this_call": len(selected) == len(images) and bool(images),
            "policy": "All available pages are scheduled across batches. Do not infer whole-package visual compliance from a partial image batch. Keep incomplete checks uncertain."}
        part.pop("packet_sha256", None)
        part["packet_sha256"] = hashlib.sha256(canonical(part).encode()).hexdigest()
        batches.append((part, group))
    return batches


def combine_summaries(summaries, expected_batches):
    """Same-judge page-batch accounting, not multi-judge voting or accuracy."""
    complete = len(summaries) == expected_batches and all(s.get("status") != "invalid_judgment" for s in summaries)
    def combine(field):
        values = [s.get(field) for s in summaries]
        if field == "consequential_error_candidate":
            return True if any(v is True for v in values) else False if complete and values and all(v is False for v in values) else None
        return False if any(v is False for v in values) else True if complete and values and all(v is True for v in values) else None
    return {"status": "automated_assessment_not_human_acceptance" if complete else "incomplete_or_invalid_judging",
            "human_accepted": None, "project_rubric_pass": combine("project_rubric_pass"),
            "consequential_error_candidate": combine("consequential_error_candidate"),
            "failed_criteria": sorted({x for s in summaries for x in s.get("failed_criteria", [])}),
            "uncertain_criteria": sorted({x for s in summaries for x in s.get("uncertain_criteria", [])}),
            "validation_errors": sorted({x for s in summaries for x in s.get("validation_errors", [])}),
            "batches_received": len(summaries), "batches_expected": expected_batches,
            "coverage": summaries[0].get("coverage") if summaries else None,
            "native_engineering_checks": summaries[0].get("native_engineering_checks") if summaries else None,
            "task_defect_assessments": [s.get("task_defect") for s in summaries],
            "limit": "Every raw batch retained. Partial visual checks remain uncertain; this is not human acceptance or an official GDPval score."}


def grade_packet(client, packet, images, dest, model, *, identity, scope, execute):
    """Persist packet before dispatch and every response, including invalid ones."""
    dest = Path(dest)
    if (dest / "result.json").exists():
        return read(dest / "result.json")
    if (dest / "in_progress.json").exists():
        raise ValueError("Prior interrupted grader attempt requires explicit checkpoint review; no automatic duplicate request")
    batches = image_batches(packet, images)
    result = {**identity, "model": model, "status": "prepared_not_executed", "started_at": now(), "calls": [], "batches": [],
              "human_acceptance": None, "blinding": "Solver identity is in private routing metadata, excluded from judge packet."}
    for i, (part, _) in enumerate(batches, 1):
        write(dest / f"packet-{i:02d}.json", part)
    write(dest / "packet.json", packet)
    if not execute:
        write(dest / "prepared.json", {**result, "expected_batches": len(batches)})
        return result
    if client is None:
        raise ValueError("An authenticated budget client is required for explicit execution")
    write(dest / "in_progress.json", {"started_at": now(), "identity": identity, "expected_batches": len(batches)})
    summaries = []
    call_label = "grade:" + dest.name
    try:
        for number, (part, group) in enumerate(batches, 1):
            urls = [(x["id"], image_part(x["path"], False)["image_url"]["url"]) for x in group]
            body = {"model": model, "messages": judge_messages(part, urls), "max_tokens": 8000,
                    "reasoning": {"effort": "medium"}, "response_format": {"type": "json_object"}, "usage": {"include": True}}
            data, meta = client.call(body, scope=scope, label=f"{call_label}:batch{number}")
            result["calls"].append(meta["call_id"])
            write(dest / f"response-{number:02d}.json", data)
            choice = (data.get("choices") or [{}])[0]
            content = (choice.get("message") or {}).get("content")
            try:
                if choice.get("finish_reason") == "length":
                    raise ValueError("judgment_output_token_limit")
                judgment = parse_judgment(content)
                write(dest / f"judgment-{number:02d}.json", judgment)
                if number == 1:
                    write(dest / "judgment.json", judgment)
                summary = summarize_judgment(part, judgment)
            except (ValueError, TypeError) as error:
                summary = {"status": "invalid_judgment", "validation_errors": [str(error)[:500]], "human_accepted": None,
                           "project_rubric_pass": None, "consequential_error_candidate": None}
            summaries.append(summary)
            write(dest / f"summary-{number:02d}.json", summary)
            result["batches"].append({"batch": number, "call_id": meta["call_id"], "packet_path": str(dest / f"packet-{number:02d}.json"),
                                      "judgment_path": str(dest / f"judgment-{number:02d}.json"), "summary": summary})
        result["status"] = "graded" if all(s["status"] != "invalid_judgment" for s in summaries) else "invalid_judgment"
    except BudgetStop as error:
        result.update(status="budget_limited", error=str(error))
    except Exception as error:
        result.update(status="infrastructure_failure", error=str(error)[:1500])
    result["summary"] = combine_summaries(summaries, len(batches))
    rows = [read(p) for p in (client.root / "calls").glob("*/reservation.json") if read(p).get("label", "").startswith(call_label + ":")]
    result["calls"] = [r["id"] for r in rows]
    result["known_cost_usd"] = sum(r.get("actual_cost_usd") or 0 for r in rows)
    result["unresolved_calls"] = sum(r.get("actual_cost_usd") is None for r in rows)
    result["unresolved_reserved_usd"] = sum(r["reserved_usd"] for r in rows if r.get("actual_cost_usd") is None)
    result.update(completed_at=now(), packet_path=str(dest / "packet.json"), judgment_path=str(dest / "judgment.json"))
    write(dest / "result.json", result)
    (dest / "in_progress.json").unlink()
    return result


def run_primary(client, model, task_prefix=None, solver_model=None, stage="primary", execute=False):
    tasks = {t["task_id"]: t for t in map(json.loads, INPUTS.read_text().splitlines())}
    rubrics = read(RUBRICS)
    results = []
    for path in sorted((OUT / "runs").glob("*/result.json")):
        run = read(path)
        if run.get("stage") != stage or (task_prefix and not run["task_id"].startswith(task_prefix)) or (solver_model and run.get("model") != solver_model):
            continue
        dest = OUT / "grades" / (path.parent.name + "__" + model.replace("/", "_"))
        if (dest / "result.json").exists():
            results.append(read(dest / "result.json")); continue
        try:
            packet, private, images, _ = prepare_run(path.parent, tasks[run["task_id"]], rubrics)
        except Exception as error:
            record = {"task_id": run["task_id"], "solver_run_id": path.parent.name, "solver_model": run.get("model"), "model": model,
                      "stage": stage, "status": "preparation_failure", "error": str(error)[:1500], "calls": [], "known_cost_usd": 0,
                      "human_acceptance": None, "summary": {"human_accepted": None, "project_rubric_pass": None, "consequential_error_candidate": None}}
            if execute:
                write(dest / "result.json", record)
            results.append(record)
            print(json.dumps({"task": run["task_id"][:8], "status": record["status"], "error": record["error"]}), flush=True)
            continue
        if packet is None:
            record = {"task_id": run["task_id"], "solver_run_id": path.parent.name, "solver_model": run.get("model"), "model": model,
                      "stage": stage, "status": "no_submission", "solver_status": run.get("status"), "calls": [], "known_cost_usd": 0,
                      "human_acceptance": None, "summary": {"human_accepted": None, "project_rubric_pass": None, "consequential_error_candidate": None}}
            if execute:
                write(dest / "result.json", record)
            results.append(record); continue
        write(dest / "identity.private.json", private)
        identity = {"task_id": run["task_id"], "solver_run_id": path.parent.name, "solver_model": run.get("model"), "stage": stage}
        scope = "judge_primary" if model == read(ROOT / "config/evaluation_v2_run.json")["primary_judge"] else "judge_secondary"
        record = grade_packet(client, packet, images, dest, model, identity=identity, scope=scope, execute=execute)
        results.append(record)
        print(json.dumps({"task": run["task_id"][:8], "judge": model, "status": record["status"], "cost": record.get("known_cost_usd")}), flush=True)
        if record["status"] in ("budget_limited", "infrastructure_failure"):
            break
    return results


def run_development(client, model, task_prefix=None, execute=False):
    # This file deliberately has no expected human labels; those are kept apart.
    path = ROOT / "data/evaluation_v2/development-calibration.json"
    bank = read(path)
    cases = bank["cases"]
    results = []
    for case in cases:
        case_id = case["case_id"]
        if task_prefix and not case_id.startswith(task_prefix):
            continue
        packet = build_packet(case["task"], case["sources"], case["artifacts"], case["criteria"], case.get("inspection"),
                              expected_source_ids=[s["id"] for s in case["sources"]], source_coverage_confirmed=True)
        dest = OUT / "development_calibration" / (case_id + "__" + model.replace("/", "_"))
        identity = {"case_id": case_id, "task_id": case["task"].get("task_id"), "stage": "development_calibration",
                    "source_bank_sha256": digest(path), "scope_limit": "Selected previously reviewed historical adapted cases; development calibration, not new validation or native visual acceptance"}
        record = grade_packet(client, packet, [], dest, model, identity=identity, scope="judge_development_calibration", execute=execute)
        results.append(record)
        print(json.dumps({"case": case_id, "judge": model, "status": record["status"], "cost": record.get("known_cost_usd")}), flush=True)
        if record["status"] in ("budget_limited", "infrastructure_failure"):
            break
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file")
    parser.add_argument("--task")
    parser.add_argument("--model")
    parser.add_argument("--solver-model")
    parser.add_argument("--stage", choices=["primary", "smoke", "supplemental", "development_calibration"], default="primary")
    parser.add_argument("--execute", action="store_true", help="Dispatch paid grading under the frozen global budget; otherwise prepare packets only")
    args = parser.parse_args()
    if args.execute and not args.key_file:
        parser.error("--execute requires --key-file")
    freeze_grader(args.execute)
    cfg = read(ROOT / "config/evaluation_v2_run.json")
    model = args.model or cfg["primary_judge"]
    client = Client(args.key_file) if args.execute else None
    if args.stage == "development_calibration":
        results = run_development(client, model, args.task, args.execute)
    else:
        results = run_primary(client, model, args.task, args.solver_model, args.stage, args.execute)
    print(json.dumps({"mode": "executed" if args.execute else "offline_preparation", "records": len(results), "statuses": [r["status"] for r in results]}, indent=2))


if __name__ == "__main__":
    main()
