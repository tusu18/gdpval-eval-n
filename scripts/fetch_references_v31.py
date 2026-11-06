"""Download the reference files the v3.1 slice needs into research/reference_files/.

Integrity: every URL is pinned to the dataset commit (resolve/11e7900…), so the bytes are fixed by the dataset
revision. Each file is also checked for a complete download (Content-Length) and a valid container (Office files
are zip, PDFs start with %PDF), and its SHA-256 is recorded in research/reference_manifest_v31.json, which is
what the study pins. The folder name matches the file's SHA-256 prefix for some GDPval files but not all
(it is not a content hash for most of the v3.1 files), so it is recorded as a check, not required.

  python3 scripts/fetch_references_v31.py            # skips files already present and valid
Standard library only; set HF_TOKEN if Hugging Face rate-limits you.
"""
import hashlib, json, os, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLICE = ROOT / 'data/gdpval_v31/solver/tasks.jsonl'
REVISION = '11e7900cdcac61bc4daf59e65feb238acda98fbf'
MAGIC = {'.xlsx': b'PK', '.docx': b'PK', '.pptx': b'PK', '.pdf': b'%PDF'}


def problem(name, blob):
    want = MAGIC.get(Path(name).suffix.lower())
    if not blob: return 'empty file'
    if want and not blob.startswith(want): return f'not a valid {Path(name).suffix} file (starts {blob[:12]!r})'
    return None


def folder_check(blob, folder):
    if hashlib.sha256(blob).hexdigest().startswith(folder): return 'folder=sha256'
    if hashlib.md5(blob).hexdigest().startswith(folder): return 'folder=md5'
    return 'folder is not a content hash'


def main():
    tasks = [json.loads(l) for l in SLICE.read_text().split('\n') if l.strip()]
    rows, failed = [], []
    for t in tasks:
        for rel, url in zip(t['reference_files'], t['reference_urls']):
            dest = ROOT / 'research' / rel; folder = rel.split('/')[1]
            if f'/resolve/{REVISION}/' not in url:
                failed.append({'path': rel, 'error': 'URL is not pinned to dataset revision ' + REVISION[:7]}); continue
            if dest.exists() and not problem(dest.name, dest.read_bytes()):
                blob = dest.read_bytes()
                rows.append({'task_id': t['task_id'], 'path': str(dest.relative_to(ROOT)), 'sha256': hashlib.sha256(blob).hexdigest(),
                             'bytes': len(blob), 'folder_check': folder_check(blob, folder), 'status': 'present'}); continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(url, headers={'User-Agent': 'gdpval-eval-research'} | ({'Authorization': 'Bearer ' + os.environ['HF_TOKEN']} if os.environ.get('HF_TOKEN') else {}))
            blob, err = None, None
            for attempt in range(4):
                try:
                    with urllib.request.urlopen(req, timeout=120) as r:
                        blob = r.read(); size = r.headers.get('Content-Length')
                    if size and int(size) != len(blob): raise IOError(f'truncated: {len(blob)} of {size} bytes')
                    err = problem(rel, blob)
                    if err: raise IOError(err)
                    break
                except Exception as e:
                    blob, err = None, str(e)[:200]
                    if attempt < 3: time.sleep(2 ** attempt)
            if blob is None:
                failed.append({'path': rel, 'error': err}); continue
            dest.write_bytes(blob)
            rows.append({'task_id': t['task_id'], 'path': str(dest.relative_to(ROOT)), 'sha256': hashlib.sha256(blob).hexdigest(),
                         'bytes': len(blob), 'folder_check': folder_check(blob, folder), 'status': 'downloaded'})
            print('ok', rel, len(blob), flush=True)
    (ROOT / 'research/reference_manifest_v31.json').write_text(json.dumps({'revision': REVISION, 'files': rows, 'failed': failed}, indent=1) + '\n')
    print(json.dumps({'present_or_downloaded': len(rows), 'failed': failed}, indent=1))
    if failed: raise SystemExit(1)


if __name__ == '__main__':
    main()
