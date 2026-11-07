#!/usr/bin/env python3
"""How much of each random-sample output the blind review packet showed.

human_review_kit._write_packet cuts each output file's extracted text at 80,000 characters and each source at 60,000,
with no marker. This records, per sampled output, the extracted length of every delivered file and whether any was cut.
Writes output/study_v3/packet_truncation_v31.json (read by results_v31.py).

    python3 scripts/packet_truncation_v31.py
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / 'output/study_v3'
OUTPUT_CAP, SOURCE_CAP = 80000, 60000
sys.path.insert(0, str(ROOT / 'scripts'))


def main():
    from evidence_grader import extract_artifact
    sel = json.loads((V3 / 'calibration_set_v31.json').read_text())['selected']
    rows = []
    for run in sel:
        r = json.loads((V3 / 'solver_runs' / f'{run}.json').read_text())
        files = []
        for o in r['outputs']:
            f = V3 / 'claudecode' / run / 'outputs' / o['name']
            try:
                n = len(extract_artifact(f).get('text', ''))
            except Exception:
                n = None
            files.append({'name': o['name'], 'chars': n, 'cut': bool(n and n > OUTPUT_CAP)})
        rows.append({'run_id': run, 'files': files, 'any_cut': any(x['cut'] for x in files),
                     'shown_share_of_largest': round(min(1.0, OUTPUT_CAP / max(x['chars'] or 1 for x in files)), 4)})
    out = {'output_cap_chars': OUTPUT_CAP, 'source_cap_chars': SOURCE_CAP, 'marker': False, 'rows': rows}
    (V3 / 'packet_truncation_v31.json').write_text(json.dumps(out, indent=1) + '\n')
    print(sum(r['any_cut'] for r in rows), 'of', len(rows), 'sampled outputs cut')


if __name__ == '__main__':
    main()
