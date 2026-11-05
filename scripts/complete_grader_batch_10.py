"""Wait for the existing single writer, then resume only unattempted jobs.

The original runner/config stay frozen. The API key is requested by getpass only
if more jobs need dispatch; it is never saved or put in command arguments.
"""
import argparse
from collections import Counter
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/judge_robustness_10'


def state():
    cfg = json.loads((ROOT/'config/judge_robustness_10.json').read_text())
    rows = {}
    for job in cfg['jobs']:
        path = OUT/'runs'/(job['id']+'.json')
        if path.exists():
            try:
                rows[job['id']] = json.loads(path.read_text())
            except json.JSONDecodeError:
                return cfg, rows, True
    return cfg, rows, False


def other_runners():
    result = subprocess.run(['/bin/ps', '-axo', 'pid,command'], text=True,
                            capture_output=True, check=True)
    pids = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        pid, command = int(parts[0]), parts[1]
        if pid == os.getpid() or ' -lc ' in command or ' - <<' in command:
            continue
        if 'scripts/run_judge_robustness_10.py' in command and '--execute' in command:
            pids.append(pid)
    return pids


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-stage-usd', type=float, default=40.0)
    args = parser.parse_args()
    if args.max_stage_usd <= 0:
        raise SystemExit('A positive internal stage guard is required.')
    lock = (OUT/'completion.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('Another completion coordinator already owns this batch.')
    last = None
    while True:
        writers = other_runners()
        cfg, rows, writing = state()
        counts = dict(Counter(r.get('status') for r in rows.values()))
        progress = (len(rows), tuple(sorted(counts.items())), bool(writers))
        if progress != last:
            print(json.dumps({'planned':len(cfg['jobs']), 'recorded':len(rows),
                              'statuses':counts, 'existing_writer_active':bool(writers)}), flush=True)
            last = progress
        if not writers and not writing:
            break
        time.sleep(5)
    running = [r['id'] for r in rows.values() if r.get('status')=='running']
    if running:
        raise SystemExit('No live writer, but interrupted request records need explicit preservation before resuming: '+', '.join(running))
    import run_judge_robustness_10 as runner
    if len(rows) == len(cfg['jobs']):
        runner.finish(cfg)
        print('All planned requests have terminal records; no further dispatch needed.', flush=True)
        return
    # main verifies every frozen hash before obtaining a key or sending data.
    # Existing received/error records are skipped, never deleted or overwritten.
    sys.argv = [str(ROOT/'scripts/run_judge_robustness_10.py'), '--execute',
                '--max-usd', str(args.max_stage_usd)]
    runner.main()
    cfg, rows, writing = state()
    print(json.dumps({'final_recorded':len(rows), 'planned':len(cfg['jobs']),
                      'statuses':dict(Counter(r.get('status') for r in rows.values())),
                      'all_terminal':not writing and len(rows)==len(cfg['jobs']) and
                                     all(r.get('status') in ('received','execution_error') for r in rows.values())}), flush=True)


if __name__ == '__main__':
    main()
