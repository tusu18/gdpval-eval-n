"""Prepare unlabeled human review of four proposed edits, without model calls.

These are design proposals anchored to existing native outputs. No edited native
files, gold labels, correctness directions or judge results are manufactured.
"""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
import shutil

from run_evaluation_v2 import ROOT, OUT, read, write, digest, now

BASE = OUT / "construct_direction_review"


def main():
    cases = {}
    for case_id, neutral in [("P-docx", "workflow"), ("P-xlsx", "cost-workbook")]:
        folder = OUT / "judge_checks/cases" / case_id
        packet = read(folder / "packet.json")
        private = read(folder / "identity.private.json")
        artifact = packet["artifacts"][0]
        native = Path(private["artifacts"][artifact["id"]]["path"])
        native_copy = BASE / "native" / (neutral + native.suffix)
        native_copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(native, native_copy)
        if digest(native_copy) != artifact["sha256"]:
            raise ValueError("Native copy hash mismatch")
        evidence = {"task_id": packet["task_id"], "original_request": packet["source_documents"][0]["text"],
                    "sources": packet["source_documents"], "artifact": artifact, "native_file": str(native_copy.relative_to(BASE)),
                    "model_identity": "omitted", "human_label": None, "judge_label": None}
        evidence_file = BASE / "evidence" / (neutral + ".json")
        write(evidence_file, evidence)
        cases[case_id] = {"packet": packet, "artifact": artifact, "native_file": str(native_copy.relative_to(BASE)), "evidence_file": str(evidence_file.relative_to(BASE))}
    proposal_specs = [
        ("P-docx", "word/document.xml:p28", "Every price change requires Finance controller, Program Manager and Purchase approval.", "Every price change requires Program Manager and Purchase approval.",
         "The price change request further needs approvals from the Finance controllers, Program managers, and Purchase teams."),
        ("P-docx", "word/document.xml:p23", "3 | Post-nomination changes and platform blueprint", "3 | POST-NOMINATION CHANGES AND PLATFORM BLUEPRINT",
         "Create a 2–3-page Word document outlining this revised sourcing and nomination workflow."),
        ("P-xlsx", "Inputs!B5", "0.1", "0.12", "Use a discount rate of 10% for years 2, 3, and 4."),
        ("P-xlsx", "Inputs!A1", "MODEL I | SOURCING INPUTS", "Model I | Sourcing Inputs", "Clearly list all assumptions made.")
    ]
    proposals = []
    for i, (case_id, locator, before, after, rule) in enumerate(proposal_specs):
        case = cases[case_id]
        unit = next(u for u in case["artifact"]["units"] if u["locator"] == locator)
        if before not in unit["text"] or rule not in case["packet"]["source_documents"][0]["text"]:
            raise ValueError("Proposal is not an exact existing source/output anchor")
        pair_id = "D-" + hashlib.sha256((case_id + locator).encode()).hexdigest()[:8]
        proposals.append({"pair_id": pair_id, "task_id": case["packet"]["task_id"], "native_file": case["native_file"], "evidence_file": case["evidence_file"],
                          "original_native_sha256": case["artifact"]["sha256"], "locator": locator, "source_rule_quote": rule,
                          "original_context_verbatim": unit["text"], "before_verbatim": before, "proposed_after_verbatim": after,
                          "status": "proposed_edit_not_applied_to_native_file", "human_direction": None, "human_isolated_change": None,
                          "human_reason": None, "judge_verdict": None, "expected_gold": None,
                          "review_questions": ["Considering the full task and original artifact, would this one proposed edit improve compliance, worsen it, preserve it, or leave the direction unclear?",
                                               "Does it isolate one intended change? Identify any other requirement, formula, layout or workflow effect that would change.",
                                               "Which source and artifact locations support your answer? Record uncertainty rather than inventing a gold label."],
                          "execution_note": "Only after direction review: construct a separate native copy, render/recalculate all dependent outputs, verify the complete change set, and obtain stimulus approval before judge testing."})
    proposals.sort(key=lambda p: hashlib.sha256(("construct-direction-order-v1|" + p["pair_id"]).encode()).hexdigest())
    record = {"schema": "evaluation-v2-unlabeled-construct-direction-proposals-v1", "created_at": now(), "proposals": proposals,
              "purpose": "Human direction and isolation review before using minimal-error or presentation controls to validate a judge",
              "limits": "Four edit proposals from two existing outputs; no edited native stimuli, human gold labels or judge tests exist. Original artifacts may contain other defects.",
              "source_script_sha256": digest(__file__), "api_calls": 0}
    write(BASE / "review-proposals.json", record)
    labels = BASE / "human-responses.json"
    if not labels.exists():
        write(labels, {"schema": "evaluation-v2-construct-direction-human-responses-v1", "instructions": "Do not infer labels from proposal order. Complete native review before endorsing a later test stimulus.",
                       "reviews": [{"pair_id": p["pair_id"], "direction": None, "isolated_change": None, "evidence": None, "uncertainty": None, "minutes": None} for p in proposals]})
    esc = html.escape
    blocks = []
    for p in proposals:
        blocks.append(f'<article><h2>{esc(p["pair_id"])}</h2><p><a href="{esc(p["native_file"])}">Open original native file</a> · <a href="{esc(p["evidence_file"])}">Full task and extracted evidence</a></p><p><b>Location:</b> {esc(p["locator"])}</p><blockquote>{esc(p["source_rule_quote"])}</blockquote><table><tr><th>Current text/value</th><th>Proposed replacement</th></tr><tr><td><pre>{esc(p["before_verbatim"])}</pre></td><td><pre>{esc(p["proposed_after_verbatim"])}</pre></td></tr></table><p><b>Original context:</b> {esc(p["original_context_verbatim"])}</p><ol>' + ''.join('<li>'+esc(q)+'</li>' for q in p['review_questions']) + '</ol><p class="note">Proposed edit only. No modified file has been created, recalculated, rendered or judged.</p></article>')
    page = '<!doctype html><meta charset="utf-8"><title>Review proposed evaluation controls</title><style>body{max-width:1000px;margin:40px auto;padding:0 20px;font:16px/1.55 system-ui;color:#182230}article{border-top:1px solid #ccd4df;padding:24px 0}table{width:100%;border-collapse:collapse}th,td{border:1px solid #ccd4df;padding:12px;text-align:left;vertical-align:top;width:50%}pre{white-space:pre-wrap;font:inherit}blockquote{border-left:3px solid #72829a;padding-left:16px}.note{color:#536375}</style><h1>Review proposed evaluation controls</h1><p>Review each proposed edit against the original task and native output. Decide its direction and whether it isolates one change. No human or model verdict is prefilled. These proposals are not finished test artifacts.</p>' + ''.join(blocks) + '<p>Record your answers in human-responses.json. Preserve uncertainty and reasons; no result is treated as gold automatically.</p>'
    (BASE / "index.html").write_text(page)
    print(json.dumps({"proposals": len(proposals), "human_labels": 0, "edited_native_files": 0, "page": str(BASE / "index.html")}))


if __name__ == "__main__":
    main()
