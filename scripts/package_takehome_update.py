"""Bundle the executed study with clearly separated, unrun v2 preparation."""
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
README='''# Turing FDE take-home: evidence first, next study second

START HERE: output/pdf/turing-submission-one-page.pdf
Presentation and next-study guide: output/pdf/turing-next-study-and-pitch.pdf

The submission's measured evidence is the completed GDPval paired v1 pilot:
60 runs, five source families, three occupations, two systems, two repeats;
$4.391054 total API charges. The original study is preserved in output/paired_v1.
There is no measured v2 model performance and no training experiment.

The five-page guide includes concrete failure examples, an OpenAI/Anthropic
15-minute pitch, the v2 repair, original data candidates and review/selection gates.

## What changed

- data/paired_v2 contains 24 candidate instances: five repaired GDPval-derived
  families and three original assistant-authored fictional families, each in
  baseline/recovery/conflict form. Report these two source strata separately.
- scripts/workflow_workspace.py supplies local search, file reads and scripted
  clarification. It never contacts people, reads grader files or runs a model.
- The EV quotation basis is separated from the production forecast by an
  explicit shared synthetic per-pack cost assumption. Expert realism review is
  still required. The v1 inputs and raw outputs were not changed.
- config/paired_v2/prompt_arms.json prepares a generic evidence/dependency repair
  versus baseline at matched v2 tools/budgets. It contains no task-specific answers.
- scripts/model_selection_gate.py refuses to recommend a configuration without
  expert adjudication, permissions, approved sampling/thresholds and review cost.
  It ranks only eligible configurations by total cost per accepted deliverable.

## Human review is pending

No independent human has validated the tasks or accepted the outputs.
No user/customer error threshold has been invented.

Task triplets: reviews/paired_v2/task_validation.template.json
Rights attestation: reviews/paired_v2/rights_attestation.template.json
Output grading: reviews/paired_v1_expert/output_reviews.template.json
Blinded packets: reviews/paired_v1_expert/blinded/
Coordinator-only identity map: reviews/paired_v1_expert/private_coordinator_key.json

Copy templates before filling them; generators recreate templates. Give only
the blinded packet directory and blank output review form to reviewers. Withhold
the coordinator key, model-judge reviews, model identity and scores until their
independent decisions are saved. Every critical label/disagreement requires
adjudication against actual source and rendered output. Record actual minutes.
Blinding removes explicit model labels; prose can still reveal task condition.

Original candidate episodes contain no copied external assets, but owner
attestation and domain review remain pending. GDPval reuse/redistribution rights
are unverified. This is a PRIVATE local evidence kit, not a cleared dataset release.
All v1/v2 episodes, their variants and template descendants are evaluation-only.
Public-source pretraining exposure is unknown. No contamination-free claim.

## Run offline checks

Use Python 3.12+:

python3 scripts/validate_paired_v2.py
python3 -m unittest discover -s tests -p test_paired_v2.py -v
python3 scripts/model_selection_gate.py

These calls are free and use saved local files. The selector currently returns
not_selectable because no human adjudications or customer thresholds exist.
Do not fill missing reviews with LLM judgments or treat test fixtures as data.

The prospective selection input is
reviews/paired_v2/adjudicated_selection_rows.json (not yet present), one row per
family/model/prompt arm for conflict trial 1, with independent human labels,
reviewer IDs, source validity, permission, all attempt cost and actual review
minutes. See scripts/model_selection_gate.py for the exact field names.
Repeated trials/conditions cannot count as independent families.

Preparation has no paid execution path. A later runner must be added only after
task validation, permissions and protocol freeze, and must check model prices
and enforce the campaign cap: $25 total minus $4.391054 already spent/reserved.
The maximum 192-run plan is a design matrix, not authorization to ignore the cap
or proof that 192 runs fit. Freeze a reviewed subset before execution if needed.
No SFT or RL is justified until verified failures survive prompt/tool repairs.

## Dependencies and evidence

The environment, oracle, selector and tests use Python's standard library.
PDF generation requires reportlab; PDF QA used pypdf/Poppler. Prior native
DOCX/XLSX rendering depends on the Codex bundled document/artifact libraries.
Original native GDPval source assets and dependency caches are omitted.
The v1 evidence is included from the previously verified private kit; provider
account identifiers in its rejected error logs were already redacted. API keys
are absent. PACKAGE_MANIFEST.json records exact archive-member hashes.
'''

def main():
    base=ROOT/'output/paired-pilot-evidence-kit.zip'
    with zipfile.ZipFile(base) as z:
        payloads={n:z.read(n) for n in z.namelist() if n not in ['README.md','PACKAGE_MANIFEST.json']}
    paths=set()
    for pattern in ['data/paired_v2/**/*.json','config/paired_v2/*.json','reviews/**/*.json','reviews/**/*.docx','reviews/**/*.xlsx','output/paired_v2/*.json','tests/test_paired_v2.py']:
        paths.update(p for p in ROOT.glob(pattern) if p.is_file())
    scripts=['build_paired_v2.py','workflow_workspace.py','validate_paired_v2.py','model_selection_gate.py','prepare_expert_review.py','build_takehome_update.py','package_takehome_update.py']
    paths.update(ROOT/'scripts'/n for n in scripts)
    paths.update(ROOT/'output/pdf'/n for n in ['turing-submission-one-page.pdf','turing-next-study-and-pitch.pdf'])
    for path in paths:payloads[str(path.relative_to(ROOT))]=path.read_bytes()
    payloads['README.md']=README.encode()
    for name,blob in payloads.items():
        if re.search(rb'sk-or-v1-[a-fA-F0-9]{20,}',blob):raise RuntimeError('Credential scan failed; no archive written.')
        if name.startswith('reviews/paired_v1_expert/blinded/') and name.endswith('packet.json'):
            if any(s in blob for s in [b'anthropic/claude-sonnet',b'openai/gpt-6.1']):raise RuntimeError('Explicit model identifier found in a blinded packet.')
    manifest={'purpose':'Private take-home evidence and unrun next-study preparation','base_v1_kit_sha256':hashlib.sha256(base.read_bytes()).hexdigest(),'sha256':{n:hashlib.sha256(b).hexdigest() for n,b in sorted(payloads.items())}}
    payloads['PACKAGE_MANIFEST.json']=json.dumps(manifest,indent=2).encode()
    out=ROOT/'output/turing-takehome-and-next-study.zip'
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,blob in sorted(payloads.items()):z.writestr(name,blob)
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        for name,digest in manifest['sha256'].items():assert hashlib.sha256(z.read(name)).hexdigest()==digest
    print(json.dumps({'archive':str(out),'files':len(payloads),'bytes':out.stat().st_size,'credentials_found':False}))

if __name__=='__main__':main()
