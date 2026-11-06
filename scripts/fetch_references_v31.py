"""Download the reference files the v3.1 slice needs into research/reference_files/, verifying each against its
content-addressed folder name (the folder is the first 32 hex characters of the file's SHA-256).

  python3 scripts/fetch_references_v31.py            # skips files already present and verified
Writes research/reference_manifest_v31.json. Standard library only; set HF_TOKEN if Hugging Face rate-limits you.
"""
import hashlib, json, os, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLICE = ROOT / 'data/gdpval_v31/solver/tasks.jsonl'


def main():
    tasks = [json.loads(l) for l in SLICE.read_text().split('\n') if l.strip()]
    rows, failed = [], []
    for t in tasks:
        for rel, url in zip(t['reference_files'], t['reference_urls']):
            dest = ROOT / 'research' / rel; want = rel.split('/')[1]
            if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest().startswith(want):
                rows.append({'task_id': t['task_id'], 'path': str(dest.relative_to(ROOT)), 'status': 'present'}); continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(url, headers={'User-Agent': 'gdpval-eval-research'} | ({'Authorization': 'Bearer ' + os.environ['HF_TOKEN']} if os.environ.get('HF_TOKEN') else {}))
            for attempt in range(4):
                try:
                    blob = urllib.request.urlopen(req, timeout=120).read(); break
                except Exception as e:
                    if attempt == 3: failed.append({'path': rel, 'error': str(e)[:200]}); blob = None
                    else: time.sleep(2 ** attempt)
            if blob is None: continue
            h = hashlib.sha256(blob).hexdigest()
            if not h.startswith(want): failed.append({'path': rel, 'error': f'sha256 {h[:12]} does not match folder {want[:12]}'}); continue
            dest.write_bytes(blob); rows.append({'task_id': t['task_id'], 'path': str(dest.relative_to(ROOT)), 'sha256': h, 'bytes': len(blob), 'status': 'downloaded'})
            print('ok', rel, len(blob), flush=True)
    (ROOT / 'research/reference_manifest_v31.json').write_text(json.dumps({'files': rows, 'failed': failed}, indent=1) + '\n')
    print(json.dumps({'present_or_downloaded': len(rows), 'failed': failed}, indent=1))
    if failed: raise SystemExit(1)


if __name__ == '__main__':
    main()
