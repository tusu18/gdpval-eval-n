"""Separate bounded judge repeats, packet injections and native-inspection pilot.

Offline preparation is the default. No original artifact, solver result, frozen
rubric, primary grade or human label is changed. Tools replay frozen evidence.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil

from run_evaluation_v2 import ROOT, OUT, read, write, digest, canonical, now, image_part, BudgetStop
from dispatch_evaluation_v2_remaining import amended_client
from evaluation_v2_grading import judge_messages, parse_judgment, summarize_judgment, validate_judgment
from grade_evaluation_v2 import prepare_run, image_batches, grade_packet, combine_summaries, checked_file

CFG = ROOT / "config/evaluation_v2_judge_checks.json"
BASE = OUT / "judge_checks"


def object_hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def rehash_packet(packet):
    packet.pop("packet_sha256", None)
    packet["packet_sha256"] = object_hash(packet)
    return packet


def freeze_plan():
    path = BASE / "plan-freeze.json"
    current = digest(CFG)
    if path.exists():
        record = read(path)
        if record["config_sha256"] != current:
            raise ValueError("Judge-check plan changed after task/format selection was frozen")
        return record
    record = {"schema": "evaluation-v2-judge-checks-plan-freeze-v1", "created_at": now(),
              "config_path": str(CFG.relative_to(ROOT)), "config_sha256": current,
              "timing": "Primary availability and some grades known; plan frozen before extension results", "executed_requests": 0}
    write(path, record)
    return record


def freeze_execution():
    freeze_plan()
    paths = [CFG, Path(__file__), ROOT / "scripts/evaluation_v2_grading.py", ROOT / "scripts/grade_evaluation_v2.py",
             ROOT / "scripts/dispatch_evaluation_v2_remaining.py", ROOT / "config/evaluation_v2_budget_amendment.json",
             ROOT / "data/evaluation_v2/rubrics.json", ROOT / "data/evaluation_v2/effective-inputs.jsonl"]
    record = {"created_at": now(), "files": {str(p.relative_to(ROOT)): digest(p) for p in paths},
              "authorization": "Explicit user request for these bounded exploratory checks under the amended shared USD30 total ceiling"}
    path = BASE / "execution-freeze.json"
    if path.exists():
        old = read(path)
        if old["files"] != record["files"]:
            raise ValueError("Judge-check execution files changed; use a separate explicitly versioned extension")
        return old
    write(path, record)
    return record


def case_specs(cfg):
    cases = list(cfg["agentic"]["cases"])
    present = {c["task_id"] for c in cases}
    for task_id in cfg["exact_prompt_repeat"]["task_ids"]:
        if task_id not in present:
            cases.append({"case_id": "P-" + task_id[:8], "task_id": task_id, "allow_recovery": False,
                          "reason": "One-per-occupation exact repeat; no replacement if primary output missing"})
    return cases


def select_run(spec, cfg):
    prefix = spec["task_id"] + "__" + cfg["solver_model"].replace("/", "_")
    primary = OUT / "runs" / (prefix + "__primary")
    if (primary / "result.json").exists() and read(primary / "result.json").get("status") == "submitted":
        return primary
    if spec.get("allow_recovery"):
        recovery = OUT / "runs" / (prefix + "__recovery")
        if (recovery / "result.json").exists():
            row = read(recovery / "result.json")
            if row.get("status") == "submitted" and row.get("recovery_stage") == "recovery":
                return recovery
    return None


def prepare_case(spec, cfg):
    dest = BASE / "cases" / spec["case_id"]
    manifest_path = dest / "manifest.json"
    if manifest_path.exists():
        manifest = read(manifest_path)
        if manifest.get("status") == "ready":
            checked_file(dest / "packet.json", manifest["packet_file_sha256"])
            private = read(dest / "identity.private.json")
            for item in [*private["sources"].values(), *private["artifacts"].values()]:
                checked_file(item["path"], item["sha256"])
            for view in manifest["images"]:
                if view.get("available"):
                    checked_file(view["path"], view["sha256"], dest)
            return manifest
    run_dir = select_run(spec, cfg)
    if run_dir is None:
        record = {**spec, "status": "not_ready", "reason": "No submitted primary artifact or specifically allowed recovery artifact", "checked_at": now()}
        write(dest / "availability.json", record)
        return record
    tasks = {t["task_id"]: t for t in map(json.loads, (ROOT / "data/evaluation_v2/effective-inputs.jsonl").read_text().splitlines())}
    packet, private, images, run = prepare_run(run_dir, tasks[spec["task_id"]], read(ROOT / "data/evaluation_v2/rubrics.json"))
    if packet is None:
        raise ValueError("Selected run has no submitted artifact")
    if spec.get("format") and spec["format"] not in [a["kind"] for a in packet["artifacts"]]:
        record = {**spec, "status": "not_ready", "reason": "Submitted package does not contain the prespecified native format", "run_id": run_dir.name}
        write(dest / "availability.json", record)
        return record
    dest.mkdir(parents=True, exist_ok=True)
    frozen_images = []
    for i, view in enumerate(images, 1):
        v = copy.deepcopy(view)
        if view.get("available"):
            target = dest / "images" / (f"view-{i:03d}" + Path(view["path"]).suffix)
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(checked_file(view["path"], view["sha256"]), target)
            v["path"] = str(target.resolve())
        frozen_images.append(v)
    write(dest / "packet.json", packet)
    write(dest / "identity.private.json", private)
    manifest = {**spec, "status": "ready", "frozen_at": now(), "solver_run_id": run_dir.name,
                "solver_stage": run.get("stage"), "recovery_stage": run.get("recovery_stage"), "recovery_of": run.get("recovery_of"),
                "packet_path": str((dest / "packet.json").resolve()), "packet_file_sha256": digest(dest / "packet.json"),
                "native_artifact_hashes": {a["id"]: a["sha256"] for a in packet["artifacts"]},
                "source_hashes": {s["id"]: s.get("sha256") for s in packet["source_documents"]}, "images": frozen_images,
                "selection_limit": "Chosen by frozen task/format rule; primary outcomes were not wholly unknown when protocol was written"}
    write(manifest_path, manifest)
    return manifest


def text_packet(packet):
    out = copy.deepcopy(packet)
    checks = out["inspection"].get("engineering_checks", {})
    checks["native_observations"] = [{k: v for k, v in row.items() if k in ("artifact_id", "kind")} for row in checks.get("native_observations", [])]
    out["inspection"]["observations"] = []
    out["inspection"].pop("visual_coverage", None)
    out["inspection"]["limitations"] = "Text/cell evidence only in this assessment. Native render appearance and independent formula inspection records have not been supplied; do not infer their contents."
    return rehash_packet(out)


def adaptive_packet(packet, images):
    out = text_packet(packet)
    out["inspection"]["available_inspections"] = [{"id": v["id"], "artifact_id": v["artifact_id"], "locator": v.get("locator"), "available": v.get("available")} for v in images]
    out["inspection"]["inspection_access"] = "Read-only tools can retrieve frozen sections, rendered views and existing recalculation records. Tools cannot repair the deliverable or obtain new facts."
    return rehash_packet(out)


def injected_packet(packet, payload):
    out = text_packet(packet)
    for artifact in out["artifacts"]:
        artifact.setdefault("units", []).append({"locator": "appended_evaluator_note", "text": payload})
        artifact["text"] += "\nappended_evaluator_note\t" + payload
        artifact["text_sha256"] = hashlib.sha256(artifact["text"].encode()).hexdigest()
    return rehash_packet(out)


def body_for(packet, images, cfg):
    urls = [(v["id"], image_part(v["path"], False)["image_url"]["url"]) for v in images if v.get("available")]
    return {"model": cfg["model"], "messages": judge_messages(packet, urls), "max_tokens": cfg["max_tokens"],
            "reasoning": {"effort": cfg["reasoning_effort"]}, "response_format": {"type": "json_object"}, "usage": {"include": True}}


def normalize_provider(body, cfg):
    body = copy.deepcopy(body)
    models = {m["id"]: m for m in read(ROOT / "data/evaluation_v2/model-catalog.json")["models"]}
    pricing = models[cfg["model"]]["pricing"]
    body.setdefault("provider", {}).update(allow_fallbacks=False, require_parameters=True,
                                          max_price={"prompt": float(pricing["prompt"]) * 1e6, "completion": float(pricing["completion"]) * 1e6})
    return body


def primary_grade_dir(manifest, cfg):
    return OUT / "grades" / (manifest["solver_run_id"] + "__" + cfg["model"].replace("/", "_"))


def exact_fixed_reuse(manifest, packet, cfg):
    folder = primary_grade_dir(manifest, cfg)
    if not (folder / "result.json").exists():
        return None
    prior = read(folder / "result.json")
    batches = image_batches(packet, manifest["images"])
    if len(prior.get("batches", [])) != len(batches):
        return None
    pairs = []
    for index, (part, views) in enumerate(batches, 1):
        old = prior["batches"][index - 1]
        call_dir = OUT / "calls" / old["call_id"]
        request = call_dir / "request.json"
        old_packet = folder / f"packet-{index:02d}.json"
        if not request.exists() or not old_packet.exists():
            return None
        expected_request = normalize_provider(body_for(part, views, cfg), cfg)
        if canonical(read(request)) != canonical(expected_request) or read(old_packet).get("packet_sha256") != part["packet_sha256"]:
            return None
        pairs.append({"call_id": old["call_id"], "request_sha256": digest(request), "packet_sha256": part["packet_sha256"], "request_path": str(request), "packet_path": str(old_packet), "judgment_path": str(folder / f"judgment-{index:02d}.json")})
    return {"prior_result": prior, "result_path": str(folder / "result.json"), "exact_matches": pairs}


def tool(name, description, properties, required):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required, "additionalProperties": False}}}


TOOLS = [
    tool("inspection_catalog", "List frozen native inspection views and available spreadsheet calculation records. Read-only; does not certify correctness.", {}, []),
    tool("read_section", "Read exact frozen source/artifact units and locators; specify an ID from the packet. No new source retrieval or artifact editing.",
         {"id": {"type": "string"}, "locator_contains": {"type": "string"}, "offset": {"type": "integer"}, "limit": {"type": "integer"}}, ["id"]),
    tool("view_native", "Receive up to four frozen native rendered views by IDs from inspection_catalog. Images arrive with the following tool evidence; they do not modify files.",
         {"view_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4}}, ["view_ids"]),
    tool("inspect_calculations", "Retrieve the frozen spreadsheet engine/formula-error/recalculated-value record for an artifact. This replays existing inspection, does not repair or recompute the submitted workbook.",
         {"artifact_id": {"type": "string"}}, ["artifact_id"])
]


class InspectionReplay:
    def __init__(self, packet, images):
        self.packet = copy.deepcopy(packet)
        self.images = {v["id"]: v for v in images}
        self.items = {x["id"]: x for x in packet["source_documents"] + packet["artifacts"]}
        self.records = {x["artifact_id"]: x for x in packet["inspection"].get("engineering_checks", {}).get("native_observations", [])}

    def call(self, name, args):
        if name == "inspection_catalog":
            return {"views": [{k: v for k, v in x.items() if k not in ("path",)} for x in self.images.values()],
                    "calculation_records": [{"artifact_id": k, "available": bool(v.get("recalculation_engine"))} for k, v in self.records.items()]}, [], []
        if name == "read_section":
            item = self.items[args["id"]]
            units = item.get("units") or [{"locator": "full_text", "text": item["text"]}]
            term = args.get("locator_contains", "")
            if term:
                units = [u for u in units if term.lower() in str(u.get("locator", "")).lower()]
            offset, limit = args.get("offset", 0), args.get("limit", 40)
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 80:
                raise ValueError("Use offset>=0 and limit1–80")
            return {"id": item["id"], "units": units[offset:offset + limit], "total_matching_units": len(units),
                    "more_available": offset + limit < len(units)}, [], []
        if name == "view_native":
            names = args["view_ids"]
            if not isinstance(names, list) or not 1 <= len(names) <= 4 or any(not isinstance(x, str) for x in names):
                raise ValueError("Request one to four view IDs")
            views = []
            for name in names:
                row = self.images[name]
                if not row.get("available"):
                    raise ValueError("Frozen view is unavailable: " + name)
                checked_file(row["path"], row["sha256"], BASE / "cases")
                views.append(row)
            return {"images_follow": names, "scope": "Frozen original submitted-file renders; no edits"}, views, []
        if name == "inspect_calculations":
            aid = args["artifact_id"]
            record = self.records.get(aid)
            if not record or not record.get("recalculation_engine"):
                return {"artifact_id": aid, "status": "no_frozen_recalculation_record"}, [], []
            return {"artifact_id": aid, "status": "frozen_record_replayed", "record": record}, [], [aid]
        raise ValueError("Unknown or non-read-only inspection tool")


def final_evidence_packet(initial, full, images, delivered_views, delivered_calculations):
    final = copy.deepcopy(initial)
    final["inspection"]["observations"] = [{k: v for k, v in image.items() if k != "path"} | {"image_supplied": image["id"] in delivered_views} for image in images]
    original_records = full["inspection"].get("engineering_checks", {}).get("native_observations", [])
    final["inspection"]["engineering_checks"]["native_observations"] = [copy.deepcopy(row) for row in original_records if row["artifact_id"] in delivered_calculations]
    final["inspection"]["visual_coverage"] = {"views_delivered": sorted(delivered_views), "total_available_views": sum(v.get("available") is True for v in images),
                                             "all_available_views_delivered": all(v["id"] in delivered_views for v in images if v.get("available")),
                                             "missing_views": [v["id"] for v in images if not v.get("available")]}
    return rehash_packet(final)


def ledger_cost(client, prefix):
    rows = [read(p) for p in (client.root / "calls").glob("*/reservation.json") if read(p).get("label", "").startswith(prefix + ":")]
    return {"calls": [r["id"] for r in rows], "known_cost_usd": sum(r.get("actual_cost_usd") or 0 for r in rows),
            "unresolved_calls": sum(r.get("actual_cost_usd") is None for r in rows),
            "unresolved_reserved_usd": sum(r["reserved_usd"] for r in rows if r.get("actual_cost_usd") is None)}


def adaptive_job(client, manifest, cfg, dest):
    if (dest / "result.json").exists():
        return read(dest / "result.json")
    if (dest / "in_progress.json").exists():
        raise ValueError("Interrupted adaptive job: inspect checkpoint; no automatic retry")
    full = read(manifest["packet_path"])
    initial = adaptive_packet(full, manifest["images"])
    write(dest / "packet-initial.json", initial)
    replay = InspectionReplay(full, manifest["images"])
    messages = judge_messages(initial)
    delivered_views, delivered_calculations = set(), set()
    pending_views, pending_calculations = set(), set()
    events = []; action_count = 0; summaries = []
    label = "judgecheck:" + dest.name
    result = {"study": "agentic", "case_id": manifest["case_id"], "task_id": manifest["task_id"], "arm": "C_adaptive", "model": cfg["model"],
              "solver_run_id": manifest["solver_run_id"], "solver_stage": manifest.get("solver_stage"), "recovery_stage": manifest.get("recovery_stage"),
              "status": "running", "started_at": now(), "human_acceptance": None}
    write(dest / "in_progress.json", result)
    try:
        for turn in range(cfg["agentic"]["C_max_model_requests"]):
            body = {"model": cfg["model"], "messages": messages, "tools": TOOLS, "max_tokens": cfg["max_tokens"],
                    "reasoning": {"effort": cfg["reasoning_effort"]}, "response_format": {"type": "json_object"}, "usage": {"include": True}}
            write(dest / "checkpoint.json", {"turn": turn, "messages": messages, "actions": action_count, "delivered_views": sorted(delivered_views)})
            data, meta = client.call(body, scope="judge_checks_agentic", label=f"{label}:turn{turn + 1}")
            delivered_views.update(pending_views); delivered_calculations.update(pending_calculations)
            pending_views.clear(); pending_calculations.clear()
            write(dest / f"response-{turn + 1:02d}.json", data)
            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            messages.append({k: v for k, v in message.items() if k in ("role", "content", "tool_calls", "reasoning_details")})
            calls = message.get("tool_calls") or []
            if not calls:
                packet = final_evidence_packet(initial, full, manifest["images"], delivered_views, delivered_calculations)
                write(dest / "packet-final.json", packet)
                try:
                    if choice.get("finish_reason") == "length":
                        raise ValueError("judgment_output_token_limit")
                    judgment = parse_judgment(message.get("content"))
                    write(dest / "judgment.json", judgment)
                    summary = summarize_judgment(packet, judgment)
                    summaries.append(summary)
                    result["status"] = "invalid_judgment" if summary["status"] == "invalid_judgment" else "graded"
                except (ValueError, TypeError) as error:
                    summaries.append({"status": "invalid_judgment", "validation_errors": [str(error)[:500]], "human_accepted": None})
                    result["status"] = "invalid_judgment"
                break
            next_images = []
            for call in calls:
                action_count += 1
                if action_count > cfg["agentic"]["C_max_tool_actions"]:
                    raise ValueError("Adaptive tool-action limit reached")
                name = call["function"]["name"]
                try:
                    arguments = json.loads(call["function"]["arguments"])
                    reply, views, calc = replay.call(name, arguments)
                    next_images.extend(views); pending_views.update(v["id"] for v in views); pending_calculations.update(calc)
                except (ValueError, KeyError, TypeError) as error:
                    arguments = call["function"]["arguments"]; reply = {"error": str(error)[:800]}
                events.append({"action": action_count, "tool": name, "arguments": arguments, "reply": reply, "call_id": meta["call_id"]})
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(reply, ensure_ascii=False)})
            if next_images:
                content = []
                for view in next_images:
                    url = image_part(view["path"], False)["image_url"]["url"]
                    # Match the fixed arm's URL/image-detail settings exactly.
                    content.extend([{"type": "text", "text": "Inspection image: " + view["id"]}, {"type": "image_url", "image_url": {"url": url}}])
                messages.append({"role": "user", "content": content})
        else:
            result["status"] = "judge_request_limit"
    except BudgetStop as error:
        result.update(status="budget_limited", error=str(error))
    except Exception as error:
        result.update(status="inspection_or_transport_failure", error=str(error)[:1200])
    result.update(ledger_cost(client, label))
    private = read(BASE / "cases" / manifest["case_id"] / "identity.private.json")
    verification = {kind: {identity: Path(item["path"]).is_file() and digest(item["path"]) == item["sha256"] for identity, item in private[kind].items()} for kind in ("sources", "artifacts")}
    result.update(completed_at=now(), tool_actions=action_count, tool_events=events, views_delivered=sorted(delivered_views),
                  calculations_delivered=sorted(delivered_calculations), source_and_native_bytes_unchanged=all(all(group.values()) for group in verification.values()), native_hash_verification=verification,
                  summary=combine_summaries(summaries, 1), judgment_path=str(dest / "judgment.json"), packet_path=str(dest / "packet-final.json"))
    write(dest / "result.json", result)
    (dest / "in_progress.json").unlink()
    return result


def run_agentic(client, manifest, cfg, arm):
    dest = BASE / "jobs" / ("check_agentic__" + manifest["case_id"] + "__" + arm)
    if (dest / "result.json").exists():
        return read(dest / "result.json")
    packet = read(manifest["packet_path"])
    if arm == "C_adaptive":
        return adaptive_job(client, manifest, cfg, dest)
    identity = {"study": "agentic", "case_id": manifest["case_id"], "task_id": manifest["task_id"], "arm": arm,
                "solver_run_id": manifest["solver_run_id"], "solver_stage": manifest.get("solver_stage"), "recovery_stage": manifest.get("recovery_stage")}
    if arm == "B_fixed":
        reuse = exact_fixed_reuse(manifest, packet, cfg)
        if reuse:
            result = {**identity, "model": cfg["model"], "status": "reused_exact_fixed_request", "human_acceptance": None,
                      "summary": reuse["prior_result"]["summary"], "calls": [], "known_cost_usd": 0, "unresolved_calls": 0,
                      "reused_result_path": reuse["result_path"], "reused_result_status": reuse["prior_result"]["status"],
                      "reused_calls": reuse["exact_matches"], "reuse_verified_at": now(), "new_api_requests": 0}
            write(dest / "result.json", result)
            return result
    images = manifest["images"] if arm == "B_fixed" else []
    if arm == "A_text":
        packet = text_packet(packet)
    return grade_packet(client, packet, images, dest, cfg["model"], identity=identity, scope="judge_checks_agentic", execute=True)


def run_injection(client, manifest, cfg, variant):
    dest = BASE / "jobs" / ("check_injection__" + manifest["case_id"] + "__" + variant)
    base = read(manifest["packet_path"])
    clean = variant == "clean_repeat"
    packet = text_packet(base) if clean else injected_packet(base, cfg["injection"]["attack_variants"][variant])
    identity = {"study": "injection", "case_id": manifest["case_id"], "task_id": manifest["task_id"], "variant": variant,
                "carrier": "counterfactual extracted-text packet only", "solver_run_id": manifest["solver_run_id"],
                "native_artifact_hashes_unchanged": manifest["native_artifact_hashes"], "expected_label": None,
                "source_packet_file_sha256": manifest["packet_file_sha256"]}
    return grade_packet(client, packet, [], dest, cfg["model"], identity=identity, scope="judge_checks_injection", execute=True)


def run_repeat(client, manifest, cfg):
    dest = BASE / "jobs" / ("check_repeat__" + manifest["case_id"])
    if (dest / "result.json").exists():
        return read(dest / "result.json")
    if (dest / "in_progress.json").exists():
        raise ValueError("Interrupted repeat: explicit checkpoint review required")
    baseline_folder = primary_grade_dir(manifest, cfg)
    if not (baseline_folder / "result.json").exists():
        return {"study": "repeat", "case_id": manifest["case_id"], "status": "not_ready", "reason": "Primary judgment not available"}
    baseline = read(baseline_folder / "result.json")
    if not baseline.get("batches"):
        return {"study": "repeat", "case_id": manifest["case_id"], "status": "not_ready", "reason": "No baseline request with a grading packet"}
    result = {"study": "repeat", "case_id": manifest["case_id"], "task_id": manifest["task_id"], "model": cfg["model"],
              "baseline_result_path": str(baseline_folder / "result.json"), "status": "running", "started_at": now(), "batches": [], "human_acceptance": None}
    write(dest / "in_progress.json", result)
    summaries = []; prefix = "judgecheck:" + dest.name
    try:
        for batch in baseline["batches"]:
            index = batch["batch"]
            original_request = OUT / "calls" / batch["call_id"] / "request.json"
            body = read(original_request)
            if body["model"] != cfg["model"] or body["max_tokens"] != cfg["max_tokens"] or body.get("reasoning", {}).get("effort") != cfg["reasoning_effort"]:
                raise ValueError("Baseline judge settings differ from frozen repeat plan")
            packet = read(baseline_folder / f"packet-{index:02d}.json")
            write(dest / f"packet-{index:02d}.json", packet)
            data, meta = client.call(body, scope="judge_checks_repeat", label=f"{prefix}:batch{index}")
            actual_request = client.root / "calls" / meta["call_id"] / "request.json"
            if canonical(read(actual_request)) != canonical(body):
                raise ValueError("Repeated body differs from original; not an exact-prompt repeat")
            write(dest / f"response-{index:02d}.json", data)
            choice = (data.get("choices") or [{}])[0]
            try:
                if choice.get("finish_reason") == "length":
                    raise ValueError("judgment_output_token_limit")
                judgment = parse_judgment((choice.get("message") or {}).get("content"))
                write(dest / f"judgment-{index:02d}.json", judgment)
                summary = summarize_judgment(packet, judgment)
            except (ValueError, TypeError) as error:
                summary = {"status": "invalid_judgment", "validation_errors": [str(error)[:500]], "human_accepted": None}
            summaries.append(summary)
            result["batches"].append({"batch": index, "call_id": meta["call_id"], "baseline_call_id": batch["call_id"],
                                      "exact_request_match": True, "baseline_request_sha256": digest(original_request), "summary": summary})
        result["status"] = "graded" if all(s["status"] != "invalid_judgment" for s in summaries) else "invalid_judgment"
    except BudgetStop as error:
        result.update(status="budget_limited", error=str(error))
    except Exception as error:
        result.update(status="infrastructure_failure", error=str(error)[:1000])
    result.update(ledger_cost(client, prefix))
    result.update(completed_at=now(), summary=combine_summaries(summaries, len(baseline["batches"])))
    write(dest / "result.json", result); (dest / "in_progress.json").unlink()
    return result


def pair_comparison(left, right):
    """Valid whole-response outcome pairs; exclusions are never zero flips."""
    if not left or not right:
        return {"comparable": False, "reason": "missing_arm_or_control"}
    a, b = left.get("summary", {}), right.get("summary", {})
    valid = a.get("status") == "automated_assessment_not_human_acceptance" and b.get("status") == "automated_assessment_not_human_acceptance"
    if not valid:
        return {"comparable": False, "reason": "invalid_incomplete_or_failed_judgment"}
    fields = {}
    for name in ("project_rubric_pass", "consequential_error_candidate"):
        av, bv = a.get(name), b.get(name)
        fields[name] = {"comparable": type(av) is bool and type(bv) is bool, "left": av, "right": bv,
                        "flipped": (av != bv) if type(av) is bool and type(bv) is bool else None}
    return {"comparable": True, "endpoints": fields, "interpretation": "Verdict difference only; human direction/correctness not established"}


def analyze(cfg):
    jobs = {p.parent.name: read(p) for p in (BASE / "jobs").glob("*/result.json")}
    comparisons = []
    for spec in cfg["agentic"]["cases"]:
        case_id = spec["case_id"]
        for left, right in (("A_text", "B_fixed"), ("B_fixed", "C_adaptive"), ("A_text", "C_adaptive")):
            a, b = (jobs.get("check_agentic__" + case_id + "__" + arm) for arm in (left, right))
            comparisons.append({"study": "agentic", "case_id": case_id, "left": left, "right": right, **pair_comparison(a, b)})
    for case_id in cfg["injection"]["parent_case_ids"]:
        clean = jobs.get("check_injection__" + case_id + "__clean_repeat")
        original_text = jobs.get("check_agentic__" + case_id + "__A_text")
        repeat_control = pair_comparison(original_text, clean)
        if original_text and clean and len(original_text.get("calls", [])) == len(clean.get("calls", [])) == 1:
            one = OUT / "calls" / original_text["calls"][0] / "request.json"
            two = OUT / "calls" / clean["calls"][0] / "request.json"
            exact = one.exists() and two.exists() and canonical(read(one)) == canonical(read(two))
            repeat_control["exact_request_match"] = exact
            if not exact:
                repeat_control = {"comparable": False, "reason": "clean_repeat_request_not_identical", "exact_request_match": False}
        comparisons.append({"study": "injection_control", "case_id": case_id, "comparison": "original_A_text_vs_fresh_unchanged_control", **repeat_control})
        for variant in cfg["injection"]["attack_variants"]:
            comparisons.append({"study": "injection", "case_id": case_id, "variant": variant,
                                **pair_comparison(clean, jobs.get("check_injection__" + case_id + "__" + variant))})
    selected = {s["task_id"]: s for s in case_specs(cfg)}
    for task_id in cfg["exact_prompt_repeat"]["task_ids"]:
        case_id = selected[task_id]["case_id"]
        row = jobs.get("check_repeat__" + case_id)
        path = Path(row["baseline_result_path"]) if row else None
        comparisons.append({"study": "repeat", "case_id": case_id, **pair_comparison(read(path) if path and path.exists() else None, row)})
    denominator_report = {}
    for study in ("agentic", "injection", "injection_control", "repeat"):
        group = [c for c in comparisons if c["study"] == study]
        entry = {"scheduled_comparisons": len(group), "valid_whole_response_pairs": sum(c["comparable"] for c in group), "endpoints": {},
                 "scope": "Agentic comparisons share four cases; injections share two parent cases; these are not independent tasks."}
        for field in ("project_rubric_pass", "consequential_error_candidate"):
            valid = [c["endpoints"][field] for c in group if c["comparable"] and c["endpoints"][field]["comparable"]]
            excluded = {}
            for c in group:
                reason = c.get("reason") if not c["comparable"] else "uncertain_endpoint" if not c["endpoints"][field]["comparable"] else None
                if reason:
                    excluded[reason] = excluded.get(reason, 0) + 1
            entry["endpoints"][field] = {"valid_pair_denominator": len(valid), "flips": sum(v["flipped"] for v in valid), "unchanged": sum(not v["flipped"] for v in valid), "excluded": excluded}
        denominator_report[study] = entry
    report = {"created_at": now(), "schema": "evaluation-v2-judge-checks-analysis-v1", "jobs": jobs, "comparisons": comparisons,
              "known_incremental_cost_usd": sum(x.get("known_cost_usd") or 0 for x in jobs.values()),
              "physical_new_requests": sum(len(x.get("calls", [])) for x in jobs.values()),
              "unresolved_calls": sum(x.get("unresolved_calls") or 0 for x in jobs.values()),
              "human_accuracy": None, "human_acceptance": None, "comparison_counts": denominator_report,
              "limits": ["Selected format pilot; extra evidence and compute differ by arm", "Recovery artifacts remain separately identified",
                         "Invalid, missing and uncertain pairs are excluded with reasons, never counted as unchanged verdicts",
                         "Packet injection controls are not native-file attacks or human-confirmed construct edits",
                         "Native usability and correctness need new blinded human reviews"]}
    write(BASE / "analysis.json", report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "run", "analyze"])
    parser.add_argument("--study", choices=["agentic", "repeat", "injection", "all"], default="agentic")
    parser.add_argument("--case")
    parser.add_argument("--arm", choices=["A_text", "B_fixed", "C_adaptive"])
    parser.add_argument("--key-file")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    cfg = read(CFG); freeze_plan()
    if args.action == "analyze":
        report = analyze(cfg); print(json.dumps({"new_requests": report["physical_new_requests"], "cost": report["known_incremental_cost_usd"], "comparisons": report["comparisons"]}, indent=2)); return
    specs = case_specs(cfg)
    manifests = {s["case_id"]: prepare_case(s, cfg) for s in specs if not args.case or s["case_id"] == args.case or s["task_id"].startswith(args.case)}
    if args.action == "prepare":
        print(json.dumps([{k: x.get(k) for k in ("case_id", "task_id", "status", "solver_run_id", "recovery_stage", "reason")} for x in manifests.values()], indent=2)); return
    if not args.execute or not args.key_file:
        parser.error("run requires both --execute and --key-file; preparation is free")
    freeze_execution(); client = amended_client(args.key_file)
    agentic_ids = {x["case_id"] for x in cfg["agentic"]["cases"]}
    for case_id, manifest in manifests.items():
        if manifest["status"] != "ready":
            print(json.dumps({"case_id": case_id, "status": manifest["status"]}), flush=True); continue
        jobs = []
        if args.study in ("agentic", "all") and case_id in agentic_ids:
            jobs.extend(("agentic", arm) for arm in ([args.arm] if args.arm else cfg["agentic"]["arms"]))
        if args.study in ("repeat", "all") and manifest["task_id"] in cfg["exact_prompt_repeat"]["task_ids"]:
            jobs.append(("repeat", None))
        if args.study in ("injection", "all") and case_id in cfg["injection"]["parent_case_ids"]:
            jobs.extend(("injection", variant) for variant in ["clean_repeat", *cfg["injection"]["attack_variants"]])
        for study, variant in jobs:
            result = run_agentic(client, manifest, cfg, variant) if study == "agentic" else run_repeat(client, manifest, cfg) if study == "repeat" else run_injection(client, manifest, cfg, variant)
            print(json.dumps({"study": study, "case": case_id, "arm_or_variant": variant, "status": result["status"], "cost": result.get("known_cost_usd")}), flush=True)
            if result["status"] == "budget_limited":
                analyze(cfg); return
    analyze(cfg)


if __name__ == "__main__":
    main()
