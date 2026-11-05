"""Package the final local study without credentials, caches or interim reports."""
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/paired-pilot-evidence-kit.zip'
README = """# Paired GDPval workflow pilot — final evidence kit

Start with output/pdf/paired-pilot-research-and-sales.pdf (eight pages), or
output/pdf/paired-pilot-one-page.pdf (one page). The final machine-readable
results are output/paired_v1/summary.json and evaluation_card.json.

60 solver runs, five source families, three conditions, two systems, two trials.
Reported API spend: $4.391054 including all review attempts. No training or
independent expert grading was performed. The API experiment is finished.

The study does not show superiority over GDPval or AfterQuery. Structured fact
checks saturated among parseable outputs; output validity, artifact constraints
and substantive model reviews are separate measures. Four EV conflict runs are
retained but excluded from the clean paired estimate because the intervention
coupled the volume forecast with quotation cost basis.

## Inspect the evidence

- config/paired_protocol.v1.json: original frozen protocol and input hashes.
- data/paired_v1/: solver inputs, separate grader truths, selection and order.
- output/paired_v1/runs/: original first-attempt solver responses and traces.
- output/paired_v1/artifacts/: 47 DOCX and 12 XLSX model deliverables.
- output/paired_v1/artifact_qa/: page-count and exported-value check records.
- output/paired_v1/judgments_v3/: 53 primary and 12 secondary model reviews.
- output/paired_v1/judgments* and rejected_review_attempts/: invalidated or
  rejected attempts, retained to audit review defects and costs.
- output/paired_v1/defect_adjudications.json: post-execution defect decisions.
- output/paired_v1/ledger.json and judge_ledger.json: all reported charges.
- PACKAGE_MANIFEST.json: SHA-256 of the exact packaged bytes.

## Local reproducibility

Use Python 3.12+ for the standard-library runner, scorer and tests.
`python3 scripts/finalize_paired_results.py` recomputes final scores/card from
saved local runs and reviews without paid API calls. It requires keeping the
supplied directory layout. Do not use score_paired_pilot.py alone as the final
summary: it produces the decision-only intermediate summary.

Report generation requires reportlab. Exported workbook verification requires
openpyxl. The artifact renderer uses docx and @oai/artifact-tool from the Codex
bundled Node runtime; DOCX rendering uses the bundled document renderer and
LibreOffice. These dependencies and rendered page images are not bundled.
All native outputs and final page/value check records are included.

The source builder is included to inspect deterministic transformations; do not
rebuild v1 in place because that rewrites frozen timestamps and protocol hashes.
Original native GDPval reference assets and the full public dataset are omitted.
Their pinned source links and hashes are in research/reference_manifest.json.
The source builder requires the original selected source records and extracts
in the full local project. Saved solver payloads suffice to audit this study.

## Provenance and sharing

The source is the public GDPval release at revision
11e7900cdcac61bc4daf59e65feb238acda98fbf. Synthetic changes were specified in code;
no teacher API generated the task facts. Seed 20261030 shuffles run order only.
All five source families and their variants are evaluation-only. Public-source
pretraining exposure is unknown; this is not a contamination-free holdout.

This is a PRIVATE research evidence kit containing source-derived task text and
outputs. Commercial adaptation and redistribution rights remain unverified.
It is not a licensed dataset release. API keys, account budget records, local
caches, dependencies and stale intermediate reports are excluded. Account IDs
inside rejected provider error messages are redacted only in this archive;
original private logs remain in the project. PACKAGE_MANIFEST.json records
those redactions and exact packaged hashes. No solver answer is edited.
"""

def main():
    selected = set()
    def add(pattern):
        selected.update(p for p in ROOT.glob(pattern) if p.is_file() and not p.is_symlink())
    for pattern in [
        'scripts/*.py', 'scripts/*.mjs', 'tests/*.py',
        'config/paired_protocol.v1.json', 'data/paired_v1/**/*.json',
        'research/reference_manifest.json', 'research/openrouter/models.json',
        'output/paired_v1/*.json', 'output/paired_v1/runs/*.json',
        'output/paired_v1/judgments*/*.json',
        'output/paired_v1/rejected_review_attempts/*.json',
        'output/paired_v1/artifacts/**/*.docx',
        'output/paired_v1/artifacts/**/*.xlsx',
        'output/paired_v1/artifact_qa/page_checks.json',
        'output/paired_v1/artifact_qa/workbook_checks.json',
        'output/pdf/paired-pilot-research-and-sales.pdf',
        'output/pdf/paired-pilot-one-page.pdf',
    ]:
        add(pattern)
    excluded = {'findings.json', 'account_budget_start.json', 'artifact_manifest.json',
                'build_one_pager.py', 'build_report.py'}
    payloads = {'README.md': README.encode()}
    redacted = []
    key_pattern = re.compile(rb'sk-or-v1-[a-fA-F0-9]{20,}')
    for path in sorted(selected):
        if path.name in excluded:
            continue
        name = str(path.relative_to(ROOT))
        data = path.read_bytes()
        if key_pattern.search(data):
            raise RuntimeError('Credential scan failed; archive not written.')
        if 'rejected_review_attempts/' in name:
            clean, count = re.subn(rb'user_[A-Za-z0-9]{10,}', b'[REDACTED_ACCOUNT]', data)
            if count:
                redacted.append({'path': name, 'account_id_occurrences_removed': count})
                data = clean
        payloads[name] = data
    manifest = {
        'scope': 'Private local evidence copy, not a licensed public dataset release',
        'account_id_redactions': redacted,
        'sha256': {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()},
    }
    payloads['PACKAGE_MANIFEST.json'] = json.dumps(manifest, indent=2).encode()
    with zipfile.ZipFile(OUT, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in payloads.items():
            archive.writestr(name, data)
    with zipfile.ZipFile(OUT) as archive:
        assert archive.testzip() is None
        for name, digest in manifest['sha256'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    print(json.dumps({'archive': str(OUT), 'files': len(payloads),
                      'bytes': OUT.stat().st_size, 'redacted_error_files': len(redacted)}))

if __name__ == '__main__':
    main()
