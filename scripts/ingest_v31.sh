#!/bin/bash
# Unpack a v3.1 results pack (from `bash night.sh pack`) into this repo and rebuild every derived file.
#   bash scripts/ingest_v31.sh path/to/v31_results.zip [--fonts DIR]
# Rebuilds: output/human_reviews_all.json, output/results.json, docs/results.json, docs/index.html,
# docs/pitch.html head, docs/methods.html, docs/og.png; then runs the tests.
set -euo pipefail
cd "$(dirname "$0")/.."
ZIP="${1:?usage: bash scripts/ingest_v31.sh v31_results.zip [--fonts DIR]}"; shift || true
FONTS=""; [ "${1:-}" = "--fonts" ] && FONTS="--fonts ${2:?}"
python3 - "$ZIP" <<'EOF'
import sys, zipfile, pathlib
z = zipfile.ZipFile(sys.argv[1]); bad = [n for n in z.namelist() if n.startswith('/') or '..' in pathlib.PurePosixPath(n).parts]
if bad: sys.exit('refusing unsafe paths: %s' % bad[:3])
keys = [n for n in z.namelist() if any(s in n.lower() for s in ('.env', 'apikey', 'api_key', 'openrouter_key'))]
if keys: sys.exit('pack contains key-like files: %s' % keys[:3])
z.extractall('.'); print('unpacked', len(z.namelist()), 'entries')
EOF
grep -rlE 'sk-or-v1-[A-Za-z0-9]{20,}' output data 2>/dev/null && { echo 'an OpenRouter key appears in the unpacked files; remove it before committing'; exit 3; } || true
python3 scripts/consolidate_human_reviews.py > /dev/null
python3 scripts/build_results.py > /dev/null
python3 scripts/build_methods.py
python3 scripts/build_site.py --artifact "${ARTIFACT_COPY:-/dev/null}"
python3 scripts/build_og.py $FONTS || echo 'og.png not rebuilt (needs playwright); the previous one stays'
python3 -m pytest tests -q
