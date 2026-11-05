"""Freeze five historical human-reviewed cases for DEVELOPMENT grader checks.

No APIs or new labels. Public packets omit reviewer/model labels; expectations
and exact original human records live in a separate private comparison file.
These are adapted historical tasks, not the new original GDPval evaluation.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path

from evidence_grader import extract_artifact

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/evaluation_v2"
CASE_ROOT = ROOT / "reviews/calibration_ready_01"
CLOSURE = ROOT / "reviews/assignment_final/review_completion_2026-11-04.json"
IDS = ["C-7424ebd2", "C-2c0096b2", "C-9d21debd", "C-5304f72e", "C-4f3f9946"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def document(id: str, text: str) -> dict:
    return {"id": id, "text": text, "sha256": text_sha(text), "full_text_available": True,
            "kind": "historical_source_text", "units": [{"locator": "complete_text", "text": text}]}


def build() -> tuple[dict, dict]:
    closure = json.loads(CLOSURE.read_text())
    if closure["case_ids"] != IDS:
        raise ValueError("Historical review closure changed; adjudicate explicitly")
    raw_cases = (CASE_ROOT / "cases.js").read_text()
    cases = json.loads(raw_cases.removeprefix("window.CASES = ").rstrip().removesuffix(";"))
    indexed = {case["id"]: case for case in cases["cases"]}
    old_example_path = ROOT / "output/grader_checks_05/packets/C-7424ebd2.json"
    old_criteria = json.loads(old_example_path.read_text())["criteria"]
    criteria = [{"id": c["id"], "criterion": c["requirement"], "critical": c["critical"],
                 "consequential": c["id"] == "source_and_authority_consistency",
                 "allow_not_applicable": False,
                 "source_anchor": "Produce the requested professional deliverables, state unresolved assumptions, and do not invent missing facts."}
                for c in old_criteria]
    public_cases = []
    expected = []
    hashes = {str(CLOSURE.relative_to(ROOT)): sha(CLOSURE),
              "reviews/calibration_ready_01/cases.js": sha(CASE_ROOT / "cases.js"),
              str(old_example_path.relative_to(ROOT)): sha(old_example_path),
              "scripts/evidence_grader.py": sha(ROOT / "scripts/evidence_grader.py")}
    for cid in IDS:
        case = indexed[cid]
        export_hash = closure["current_export_hashes"][cid]
        ep = ROOT / "reviews/assignment_final/exports" / (export_hash + ".json")
        rp = ep.with_suffix(".receipt.json")
        if sha(ep) != export_hash:
            raise ValueError(f"Human export hash mismatch: {cid}")
        export = json.loads(ep.read_text())
        receipt = json.loads(rp.read_text())
        label = next(row for row in export["rows"] if row["review_id"] == cid)
        if not label["human_reviewed"]:
            raise ValueError(f"Incomplete original human review: {cid}")
        recorded = receipt["case_source_hashes"][cid]
        for path, expected_sha in recorded.items():
            if sha(ROOT / path) != expected_sha:
                raise ValueError(f"Historical review evidence changed: {path}")
            hashes[path] = expected_sha
        adapted_path = next(path for path in recorded if path.startswith("data/paired_v1/solver/"))
        adapted = json.loads((ROOT / adapted_path).read_text())
        if case["request"] != adapted["prompt"] or case["attachments"] != adapted["attachments"] or case["workspace"] != adapted["workspace"]:
            raise ValueError(f"Reviewed case differs from original historical adapted task: {cid}")
        originals = [path for path in recorded if path.startswith("output/paired_v1/artifacts/")]
        native_files = [file for file in case["files"] if file["kind"] in {"docx", "xlsx"}]
        if len(originals) != len(native_files):
            raise ValueError(f"Not all historical native deliverables represented: {cid}")
        artifacts = []
        for file in native_files:
            path = CASE_ROOT / file["path"]
            if sha(path) not in {recorded[x] for x in originals}:
                raise ValueError(f"Blinded native copy differs from reviewed output: {cid}")
            artifact = extract_artifact(path)
            artifact.update(full_text_available=True, kind=artifact["format"])
            artifacts.append(artifact)
            hashes[str(path.relative_to(ROOT))] = sha(path)
        source_dict = {"request": case["request"],
                       **{"attachment:" + k: v for k, v in case["attachments"].items()},
                       **{"workspace:" + k: v for k, v in case["workspace"].items()}}
        old_packet_path = ROOT / "output/grader_checks_05/packets" / (cid + ".json")
        reused = False
        if old_packet_path.exists():
            old = json.loads(old_packet_path.read_text())
            if old["source_documents"] != source_dict:
                raise ValueError(f"Historical grader packet source mismatch: {cid}")
            if len(old["artifacts"]) != len(artifacts):
                raise ValueError(f"Historical grader packet artifact count mismatch: {cid}")
            for prior, current in zip(old["artifacts"], artifacts):
                for key in ("id", "sha256", "text", "units"):
                    if prior[key] != current[key]:
                        raise ValueError(f"Historical full artifact extract changed: {cid}:{key}")
            hashes[str(old_packet_path.relative_to(ROOT))] = sha(old_packet_path)
            reused = True
        sources = [document(id, text) for id, text in source_dict.items() if id != "request"]
        public_cases.append({
            "case_id": cid,
            "task": {"task_id": cid, "prompt": case["request"], "occupation": case["occupation"]},
            "sources": sources,
            "artifacts": artifacts,
            "criteria": copy.deepcopy(criteria),
            "expected_source_ids": [s["id"] for s in sources],
            "source_coverage_confirmed": True,
            "inspection": {
                "engineering_checks": {"native_visual_review": "not_supplied", "page_length_verified": None,
                                       "scope": "Entire extracted text of every historical native deliverable. Rendered PDF copies are duplicate views, not additional deliverables."},
                "observations": [],
                "coverage_notes": ["Content-only development calibration. Do not infer native layout compliance or expert acceptance from this packet."]},
            "provenance": {"origin": "historical_adapted_case_development_only",
                           "source_case_id": cid, "adapted_prompt_sha256": text_sha(case["request"]),
                           "historical_packet_reused_and_verified": reused,
                           "all_native_artifact_text_present": True,
                           "source_family_task_id": adapted["source_task_id"],
                           "not_new_original_GDPval_run": True},
        })
        response_files = []
        for response in label.get("response_records", []):
            path = ROOT / "reviews/purchasing_calibration" / response
            if not path.exists():
                raise ValueError(f"Recorded human response missing: {path}")
            response_files.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path)})
        hashes[str(ep.relative_to(ROOT))] = sha(ep)
        hashes[str(rp.relative_to(ROOT))] = sha(rp)
        expected.append({
            "case_id": cid,
            "expected": {k: label[k] for k in ("content_acceptable", "consequential_error", "evaluation_defect")},
            "original_human_row_unmodified": copy.deepcopy(label),
            "original_reviewer_metadata": {k: export.get(k) for k in ("reviewer_id", "qualification", "independent_of_author", "aware_of_study_hypothesis", "source", "exported_at")},
            "label_provenance": {"export_path": str(ep.relative_to(ROOT)), "export_sha256": export_hash,
                                 "receipt_path": str(rp.relative_to(ROOT)), "receipt_sha256": sha(rp),
                                 "response_files": response_files,
                                 "supersedes_export_sha256": export.get("supersedes_export_sha256"),
                                 "selection": "Use closure's explicit current_export_hashes; do not select by filename date or reconstruct labels."},
            "source_provenance": {"adapted_task_path": adapted_path, "source_family_task_id": adapted["source_task_id"],
                                  "family_id": adapted["family_id"], "variant": adapted["variant"],
                                  "review_receipt_source_hashes_verified": recorded},
        })
    public = {"schema": "evaluation-v2-development-calibration-v1", "stage": "development_calibration",
              "case_count": 5, "source_family_count": 2,
              "purpose": "Check new grader behavior against previously recorded human content judgments; no new labels or held-out validation.",
              "scope": "Five purposively selected historical adapted cases. Original historical requests, source text and full native-artifact extracts; no substitution of new original GDPval prompts.",
              "blinding": "Human endpoints, prior judge verdicts and solver identities withheld from case payloads. Content may still reveal identity.",
              "cases": public_cases}
    private = {"schema": "evaluation-v2-development-calibration-expected-private-v1",
               "never_send_to_judge": True, "stage": "development_only",
               "public_packet_sha256": text_sha(json.dumps(public, indent=2, ensure_ascii=False) + "\n"),
               "human_labels_created": 0, "input_hashes": hashes, "cases": expected,
               "comparison_policy": {
                   "content_endpoint": "Compare new grader project_rubric_pass with original content_acceptable at case level; this is an automated content proxy, not a human acceptance label.",
                   "consequential_endpoint": "Compare new grader consequential_error_candidate with consequential_error; retain uncertain, invalid and missing outcomes as separate counts, not binary passes.",
                   "defect_endpoint": "Compare new judge task_defect.status with evaluation_defect; retain disagreement rather than replacing human or judge labels.",
                   "strict_validation": "Do not advertise grader accuracy before actual judge calls and label comparisons. Report counts and each case; five purposive cases/two source families do not establish population reliability.",
                   "scope": "Original human content reviews did not establish native layout/page compliance, independent expertise, or independence. Conditional tooling/resource assumptions remain exactly in original_human_row_unmodified.",
                   "model_ranking": "No model ranking: outputs are purposively selected and labels cover two source families.",
               }}
    return public, private


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    public, private = build()
    outputs = [(OUT / "development-calibration.json", public),
               (OUT / "development-calibration-expected.private.json", private)]
    for path, data in outputs:
        content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        if args.check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit(f"Calibration freeze differs: {path}")
        elif not path.exists() or path.read_text() != content:
            path.write_text(content)
            if ".private." in path.name:
                os.chmod(path, 0o600)
    print(json.dumps({"status": "verified" if args.check else "prepared", "case_count": len(public["cases"]),
                      "human_labels_created": 0, "api_calls": 0,
                      "public_path": str(outputs[0][0]), "private_path": str(outputs[1][0])}))


if __name__ == "__main__":
    main()
