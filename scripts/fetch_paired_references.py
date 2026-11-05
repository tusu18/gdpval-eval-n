"""Fetch pinned, public GDPval inputs only. Never download gold deliverables."""
import json, hashlib, urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
rows = [json.loads(x) for x in (ROOT/'data/gdpval/solver/tasks.jsonl').read_text().splitlines()]
def fetch(pair):
    rel, url = pair
    path = ROOT/'research'/rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with urllib.request.urlopen(url, timeout=90) as r:
            path.write_bytes(r.read())
    return {'path': str(path.relative_to(ROOT)), 'url': url, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes':path.stat().st_size}
if __name__ == '__main__':
    pairs = [(p,u) for r in rows for p,u in zip(r['reference_files'],r['reference_urls'])]
    with ThreadPoolExecutor(max_workers=4) as pool:
        outputs=list(pool.map(fetch,pairs))
    (ROOT/'research/reference_manifest.json').write_text(json.dumps(outputs,indent=2))
    print(json.dumps({'downloaded':len(outputs),'bytes':sum(x['bytes'] for x in outputs)}))
