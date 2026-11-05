"""Freeze the 15 original GDPval tasks without changing prompts or references.

This is offline preparation only: no solver, grader, API calls, or gold loading.
Historical outputs are development evidence and are never copied into this slice.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/gdpval/solver/tasks.jsonl"
AUDIT = ROOT / "docs/evaluation_v2/task-audit.json"
OUT = ROOT / "data/evaluation_v2"
EXTERNAL_MANIFEST = OUT / "external_sources/manifest.json"
REVISION = "11e7900cdcac61bc4daf59e65feb238acda98fbf"
OCCUPATIONS = {
    "Buyers and Purchasing Agents",
    "Project Management Specialists",
    "Shipping, Receiving, and Inventory Clerks",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prompt_digest(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


class _SourceHTMLText(HTMLParser):
    """Extract source text, retaining table-cell separators and empty cells."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style", "noscript", "svg", "head"}:
            self.skip_depth += 1
        elif not self.skip_depth:
            if tag in {"p", "div", "section", "article", "h1", "h2", "h3", "h4", "li", "br", "tr"}:
                self.parts.append("\n")
            elif tag in {"td", "th"}:
                self.parts.append("\t")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg", "head"} and self.skip_depth:
            self.skip_depth -= 1
        elif not self.skip_depth and tag in {"p", "div", "section", "article", "h1", "h2", "h3", "h4", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            # HTML indentation is not a cell boundary; explicit tabs above are.
            self.parts.append(re.sub(r"\s+", " ", data))

    def text(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip() + "\n"


def prepare_external_source_index(*, write: bool = True) -> dict:
    """Write source-only TXT views for supported engine inputs; never invent data."""
    manifest = json.loads(EXTERNAL_MANIFEST.read_text())
    successful = []
    rejected = []
    for entry in manifest["sources"]:
        if not entry.get("usable_source") or not entry.get("path"):
            rejected.append({"task_id": entry.get("task_id"), "url": entry["url"],
                             "reason": entry.get("content_validation_error") or entry.get("error") or "No usable cached source"})
            continue
        original = ROOT / entry["path"]
        if digest(original) != entry["sha256"]:
            raise ValueError(f"External source changed after retrieval: {entry['path']}")
        raw = original.read_bytes()
        if b"Access Denied" in raw[:1000]:
            raise ValueError(f"Access-denied response wrongly marked usable: {original}")
        if original.suffix.lower() == ".pdf":
            if not raw.startswith(b"%PDF-"):
                raise ValueError(f"Cached PDF is not a PDF: {original}")
            supported = original
            transformation = "Original downloaded PDF bytes"
        elif original.suffix.lower() in {".html", ".htm"}:
            parser = _SourceHTMLText()
            parser.feed(raw.decode("utf-8", errors="replace"))
            supported = original.with_suffix(".source.txt")
            content = parser.text()
            if not supported.exists() or supported.read_text() != content:
                if not write:
                    raise ValueError(f"External text extraction missing or changed: {supported}")
                supported.write_text(content)
            transformation = "HTML body text; script/style/head removed, table rows and tab-separated cells retained. No filtering, calculations or recommendations."
        elif original.suffix.lower() == ".txt":
            supported = original
            transformation = "Original downloaded text bytes"
        else:
            rejected.append({"task_id": entry.get("task_id"), "url": entry["url"], "reason": "Unsupported source format"})
            continue
        successful.append({
            "task_id": entry["task_id"], "path": str(supported),
            "local_path": str(supported.relative_to(ROOT)), "name": supported.name,
            "sha256": digest(supported), "bytes": supported.stat().st_size,
            "url": entry["url"], "retrieved_at_utc": entry["retrieved_at_utc"],
            "origin": "retrieved_public_primary_source", "external_source": True,
            "raw_source_path": entry["path"], "raw_source_sha256": entry["sha256"],
            "transformation": transformation,
            **({"water_system_id": entry["system_id"], "source_query": entry["water_system_search"]} if entry.get("system_id") else {}),
        })
    return {
        "external_manifest_path": str(EXTERNAL_MANIFEST.relative_to(ROOT)),
        "external_manifest_sha256": digest(EXTERNAL_MANIFEST),
        "references": successful,
        "grader_only_coverage_gaps": {
            "rejected_retrievals": rejected,
            "limitations": manifest.get("limitations", []),
            "carrier_history": manifest.get("rate_source_coverage"),
            "task_notes": {
                "02aa1805-c658-4069-8a6a-02dec146063a": "All eight named system factsheets retrieved. Sources reflect retrieval date, not necessarily the original dataset date.",
                "a4a9195c-5ebe-4b8d-a0c2-4a6b7a49da8b": "Linked PDF provides cover and contents only. Full-standard requirements remain unavailable.",
                "5349dd7b-bf0a-4544-9a17-75b7013767e6": "Cache does not cover the complete 2020–2025 increase series. Current/2025/2026 sources have different effective dates. Original prompt's projection year remains unchanged.",
                "3c19c6d1-672c-467a-8437-6fe21afb8eae": "Linked background grant describes 3–5-month projects while original task specifies six months; no task text was repaired.",
            },
        },
    }


def attach_external_sources(task: dict, source_index: dict) -> dict:
    """Pure adapter: return a copy with cached references; mutate no input or files.

    The index is passed explicitly so identical inputs produce identical outputs.
    Coverage/answer-review annotations are deliberately not copied into solver data.
    """
    result = copy.deepcopy(task)
    extras = [copy.deepcopy(r) for r in source_index["references"] if r["task_id"] == task["task_id"]]
    for reference in extras:
        reference.pop("task_id")
    result["original_references"] = copy.deepcopy(task["references"])
    result["external_references"] = extras
    result["references"] = copy.deepcopy(task["references"]) + extras
    result["external_input_manifest"] = {
        "path": source_index["external_manifest_path"],
        "sha256": source_index["external_manifest_sha256"],
        "reference_count": len(extras),
        "original_reference_count": len(task["references"]),
    }
    result["provenance"]["external_references_added"] = bool(extras)
    result["provenance"]["external_source_policy"] = "Cached public retrievals supplement tool-accessible sources. Original prompt, reference_files and reference_urls remain unchanged."
    assert result["prompt"] == task["prompt"]
    assert result["reference_files"] == task["reference_files"]
    assert result["reference_urls"] == task["reference_urls"]
    return result


def contract(task: dict) -> dict:
    """Mechanical file requirements only, not answer content or scoring truth."""
    sid = task["source_task_id"]
    short = sid[:8]
    required = {
        "05389f78": ["docx"], "15ddd28d": [], "1b1ade2d": ["docx"],
        "24d1e93f": ["xlsx"], "93b336f3": ["docx"], "02aa1805": ["xlsx"],
        "3c19c6d1": ["pptx"], "58ac1cc5": ["pdf", "docx"],
        "ce864f41": ["xlsx"], "fd6129bd": [], "11dcc268": ["xlsx"],
        "5349dd7b": ["xlsx"], "552b7dd0": ["pptx"],
        "76418a2c": ["xlsx"], "a4a9195c": ["docx"],
    }[short]
    c = {
        "task_id": sid,
        "name": task["name"],
        "outputs": task["deliverable_contract"],
        "required_formats": required,
        "min_files": 2 if short in {"05389f78", "58ac1cc5"} else 1,
        "max_files": None,
        "format_options": [],
        "page_constraints": [],
        "slide_constraints": [],
        "sheet_constraints": [],
        "template_references": [],
        "supplemental_drafts": [],
        "external_dependency": task["external_dependency"],
        "embedded_prompt_urls": task["embedded_prompt_urls"],
        "dependency_gaps": [],
        "source_quality_flags": [],
        "audit_notes": task["audit_notes"],
        "interpretation": "File-contract audit only. Do not add these annotations, prior review findings, or grading criteria to the original task prompt.",
    }
    if short == "05389f78":
        c["page_constraints"] = [
            {"role": "CEO email", "format": "docx", "min": 1, "max": 1},
            {"role": "CPO report", "format": "docx", "min": 2, "max": 3},
        ]
        c["format_options"] = [
            {"role": "CEO email", "formats": ["docx"]},
            {"role": "CPO report", "formats": ["docx"]},
        ]
    if short in {"15ddd28d", "1b1ade2d", "93b336f3"}:
        formats = ["docx", "pdf"] if short == "15ddd28d" else ["docx"]
        c["format_options"] = [{"role": "main document", "formats": formats}]
        c["page_constraints"] = [{"role": "main document", "formats": formats, "min": 2, "max": 3}]
    if short == "24d1e93f":
        c["sheet_constraints"] = [{"role": "NPV workbook", "minimum": 4, "description": "Dedicated sheet for each of three vendors and final summary sheet; assumptions must be listed."}]
    if short == "02aa1805":
        c["sheet_constraints"] = [{"role": "well workbook", "count": 2, "description": "All wells with criteria filters; qualifying wells only."}]
        c["supplemental_drafts"] = ["Manager recommendation email; do not send"]
        c["dependency_gaps"] = ["No well records are attached; Illinois EPA external factsheets must be accessible and logged. Offline preparation has not verified current availability."]
    if short == "3c19c6d1":
        c["slide_constraints"] = [{"role": "monthly report", "count": 9}]
        c["dependency_gaps"] = ["Grant website is linked as background and has not been fetched in this offline preparation; four supplied files contain the requested report inputs."]
    if short == "58ac1cc5":
        c["template_references"] = [r["local_path"] for r in task["references"] if r["local_path"].endswith("/Change Control Form.pdf")]
        c["supplemental_drafts"] = ["QA escalation email; do not send", "MS Teams summary; do not post"]
    if short == "ce864f41":
        c["sheet_constraints"] = [{"role": "workload workbook", "required_names": ["Stakeholder Registry"]}]
        c["supplemental_drafts"] = ["Brief responses to the three requested questions"]
        c["source_quality_flags"] = ["Registry/timekeeping employee mismatch", "Monthly capacity and March 31 coverage ambiguity"]
    if short == "fd6129bd":
        c["source_quality_flags"] = ["Top-level SOP and completed form versus reference section 3B Excel tracker requirement", "No concrete change event supplied for the completed form"]
        c["mechanical_contract_adjudication_required"] = True
        c["interpretation"] += " Do not impose the historical exact-two-DOCX rule. Reference permits a Word or Excel form and also requests an Excel tracker. One file minimum is only a submission-presence check, not proof that all deliverables are present."
    if short == "11dcc268":
        c["template_references"] = [r["local_path"] for r in task["references"] if r["local_path"].endswith("/Blank Location Report.xlsx")]
        c["source_quality_flags"] = ["Received item IDs are missing from assigned-location registry", "Special prompt item has no received quantity in supplied log"]
    if short == "5349dd7b":
        c["dependency_gaps"] = ["Historical 2020–2025 rate increases and published carrier business flat rates require external retrieval; availability and effective dates unverified offline."]
        c["source_quality_flags"] = ["Prompt projects 2026 but execution date is November 2026; preserve original prompt and record retrieved rate effective dates rather than silently changing the year."]
    if short == "76418a2c":
        c["template_references"] = [r["local_path"] for r in task["references"] if r["local_path"].endswith("/Blank Daily Shipment Manifest.xlsx")]
    if short == "a4a9195c":
        c["page_constraints"] = [{"role": "ESD SOP", "format": "docx", "min": None, "max": 5}]
        c["dependency_gaps"] = ["Linked IPC-A-610G PDF is not attached locally. Prior selection audit identified a TOC/excerpt, not a full standard; availability and scope require verification."]
        c["source_quality_flags"] = ["Prompt's PC-A-610G name differs from linked IPC-A-610G filename; retain original text."]
    return c


def build(frozen_at: str) -> tuple[list[dict], dict]:
    audit = json.loads(AUDIT.read_text())
    rows = [json.loads(line) for line in SOURCE.read_text().splitlines() if line.strip()]
    if digest(SOURCE) != audit["source"]["solver_file_sha256"]:
        raise ValueError("Original solver JSONL changed after the audited source check")
    if audit["source"]["revision"] != REVISION:
        raise ValueError("Unexpected pinned source revision")
    counts = Counter(r["occupation"] for r in rows)
    if set(counts) != OCCUPATIONS or set(counts.values()) != {5} or len(rows) != 15:
        raise ValueError(f"Expected all five original tasks in each of three occupations: {counts}")
    audited = {x["source_task_id"]: x for x in audit["tasks"]}
    if set(audited) != {r["task_id"] for r in rows}:
        raise ValueError("Audit and solver task identities differ")
    result = []
    contracts = {}
    for row in sorted(rows, key=lambda x: (x["occupation"], x["task_id"])):
        sid = row["task_id"]
        a = audited[sid]
        phash = prompt_digest(row["prompt"])
        if phash != a["original_prompt_source"]["utf8_sha256"] or not a["original_prompt_source"]["exact_match_to_pinned_parquet"]:
            raise ValueError(f"Original prompt audit mismatch: {sid}")
        refs = []
        for original, url in zip(row["reference_files"], row["reference_urls"], strict=True):
            relative = Path("research") / original
            actual = ROOT / relative
            check = next(x for x in a["references"] if x["original_relative_path"] == original)
            h = digest(actual)
            if h != check["sha256"] or not check["matches_download_manifest"]:
                raise ValueError(f"Original reference hash mismatch: {relative}")
            refs.append({"path": str(actual), "local_path": str(relative), "name": actual.name,
                         "original_path": original, "url": url, "sha256": h, "bytes": actual.stat().st_size})
        c = contract(a)
        contracts[sid] = c
        # Original solver fields stay intact; all annotations are separate fields.
        result.append({**row, "original_prompt": row["prompt"], "prompt_sha256": phash,
                       "instance_id": sid, "family_id": sid, "source_task_id": sid,
                       "source_revision": REVISION, "references": refs, "contract": c,
                       "provenance": {"origin": "original_public_GDPval_task", "prompt_modified": False,
                                      "reference_files_modified": False, "constructed": False,
                                      "source_solver_path": str(SOURCE.relative_to(ROOT)),
                                      "source_solver_sha256": digest(SOURCE),
                                      "historical_family_id": a["historical_family_id"],
                                      "historical_outputs_use": "development_only; excluded from new evaluation results",
                                      "held_out_claim": False, "training_eligible": False}})
    preflight = {
        "original_prompts_verified": len(result),
        "native_references_verified": sum(len(x["references"]) for x in result),
        "required_native_formats": ["docx", "xlsx", "pptx", "pdf"],
        "external_sources_verified_in_this_preparation": False,
        "source_or_contract_issue_task_ids": [sid for sid, c in contracts.items() if c["source_quality_flags"]],
        "external_dependency_task_ids": [sid for sid, c in contracts.items() if c["dependency_gaps"]],
        "input_reader_requirements": [
            "Expose original native files, not only old truncated text extracts.",
            "BridgeMind spend workbook has six sheets and columns through AC.",
            "Incident workbook dimension reaches row 957; risk register reaches row 997. Read all populated rows; do not mistake formatting for records.",
            "Read and preserve supplied PDF/XLSX templates; PDF form output and PPTX output require native rendering/readback support.",
        ],
        "limitations": [
            "This offline audit is not expert solvability validation or an acceptance label.",
            "All 15 tasks remain in the roster even if sources or tools are unavailable; report explicit status and reason.",
            "Do not repair original task facts silently. Any later repaired task belongs in a separately named derivative study.",
        ],
    }
    metadata = {
        "version": "evaluation-v2-original15", "status": "frozen_original_slice_no_model_runs",
        "frozen_at_utc": frozen_at, "dataset": "openai/gdpval", "source_revision": REVISION,
        "selection_rule": "All five original tasks in each of the three existing occupations; no constructed replacements or outcome-based selection.",
        "ordering": "occupation then source_task_id", "task_count": 15, "occupation_counts": dict(sorted(counts.items())),
        "selected_task_ids": [x["task_id"] for x in result],
        "source_hashes": {str(SOURCE.relative_to(ROOT)): digest(SOURCE), str(AUDIT.relative_to(ROOT)): digest(AUDIT),
                          "research/reference_manifest.json": digest(ROOT / "research/reference_manifest.json"),
                          "research/train-00000-of-00001.parquet": digest(ROOT / "research/train-00000-of-00001.parquet")},
        "instruction_separation": "Use exact task.prompt as the user task. Tool descriptions belong in a separately logged system message. Contracts, audit flags, historical traces, human labels and gold are not solver instructions.",
        "historical_trace_policy": "Reuse code and traces for development only. Never pool old adapted/constructed results with original-task runs. These public, inspected tasks are not an untouched held-out test.",
        "offline_preflight": preflight, "tasks": contracts,
    }
    return result, metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify existing prepared files without writing")
    args = parser.parse_args()
    target = OUT / "task-contracts.json"
    if target.exists():
        frozen_at = json.loads(target.read_text())["frozen_at_utc"]
    else:
        frozen_at = datetime.now(timezone.utc).isoformat()
    tasks, metadata = build(frozen_at)
    jsonl = "".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in tasks)
    contract_json = json.dumps(metadata, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    source_index = prepare_external_source_index(write=not args.check)
    effective = [attach_external_sources(task, source_index) for task in tasks]
    effective_jsonl = "".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in effective)
    effective_manifest_path = OUT / "effective-inputs-manifest.json"
    effective_at = (json.loads(effective_manifest_path.read_text())["frozen_at_utc"]
                    if effective_manifest_path.exists() else datetime.now(timezone.utc).isoformat())
    effective_metadata = {
        "version": "evaluation-v2-original15-with-cached-external-sources",
        "frozen_at_utc": effective_at,
        "original_tasks_path": "data/evaluation_v2/tasks.jsonl",
        "original_tasks_sha256": hashlib.sha256(jsonl.encode()).hexdigest(),
        "effective_inputs_path": "data/evaluation_v2/effective-inputs.jsonl",
        "effective_inputs_sha256": hashlib.sha256(effective_jsonl.encode()).hexdigest(),
        "preparation_script_sha256": digest(Path(__file__)),
        "external_manifest_path": source_index["external_manifest_path"],
        "external_manifest_sha256": source_index["external_manifest_sha256"],
        "task_count": len(tasks),
        "original_reference_count": sum(len(x["references"]) for x in tasks),
        "external_reference_count": len(source_index["references"]),
        "solver_policy": "Read exact prompt and combined references only. Do not expose this manifest's grader-only coverage notes, historical review findings or gold.",
        "tasks": [{"task_id": x["task_id"], "prompt_sha256": x["prompt_sha256"],
                   "original_reference_count": len(x["original_references"]),
                   "external_reference_count": len(x["external_references"]),
                   "input_files": [{"path": r["local_path"], "sha256": r["sha256"],
                                    "external_source": r.get("external_source", False),
                                    **({"retrieved_at_utc": r["retrieved_at_utc"], "raw_source_sha256": r["raw_source_sha256"]}
                                       if r.get("external_source") else {})}
                                   for r in x["references"]]}
                  for x in effective],
        "grader_only_coverage_gaps": source_index["grader_only_coverage_gaps"],
    }
    effective_manifest_json = json.dumps(effective_metadata, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.check:
        if not (OUT / "tasks.jsonl").exists() or (OUT / "tasks.jsonl").read_text() != jsonl or not target.exists() or target.read_text() != contract_json:
            raise SystemExit("Prepared slice differs from audited original sources or contracts")
        if not (OUT / "effective-inputs.jsonl").exists() or (OUT / "effective-inputs.jsonl").read_text() != effective_jsonl or not effective_manifest_path.exists() or effective_manifest_path.read_text() != effective_manifest_json:
            raise SystemExit("Effective inputs differ from frozen external sources")
    else:
        OUT.mkdir(parents=True, exist_ok=True)
        for path, content in [(OUT / "tasks.jsonl", jsonl), (target, contract_json),
                              (OUT / "effective-inputs.jsonl", effective_jsonl),
                              (effective_manifest_path, effective_manifest_json)]:
            if not path.exists() or path.read_text() != content:
                path.write_text(content)
    print(json.dumps({"status": "verified" if args.check else "prepared", "task_count": len(tasks),
                      "reference_count": metadata["offline_preflight"]["native_references_verified"],
                      "external_reference_count": len(source_index["references"]),
                      "task_path": str(OUT / "tasks.jsonl"), "contract_path": str(target),
                      "effective_inputs_path": str(OUT / "effective-inputs.jsonl")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
