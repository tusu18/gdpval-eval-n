"""Verify frozen inputs, submitted native bytes and judge packet copies."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/evaluation_v4'


def read(path):
    return json.loads(path.read_text())


def check(path, expected):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == expected, str(path)
    return {'path': str(path.relative_to(ROOT)), 'sha256': actual}


def main():
    frozen = [check(p, sha) for p, sha in read(OUT / 'freeze.json')['files'].items()]
    submissions = []
    for manifest in sorted((OUT / 'solver').glob('*/submission_manifest.json')):
        files = []
        for artifact in read(manifest):
            item = check(artifact['path'], artifact['sha256'])
            assert artifact['inspected'] is True
            expected_views = list(range(1, len(artifact['previews']) + 1))
            assert sorted(artifact['viewed_pages']) == expected_views
            for view in artifact['previews']:
                assert Path(view['path']).is_file()
            item['required_views_and_recorded_acknowledgements'] = len(expected_views)
            files.append(item)
        submissions.append({'task_id': manifest.parent.name, 'files': files})
    assert len(submissions) == 20
    packets = []
    for packet in sorted((OUT / 'judge-packets').glob('*/packet.json')):
        data = read(packet)
        entries = []
        for group in ('sources', 'artifacts', 'external_evidence'):
            for item in data[group]:
                checked = check(item['path'], item['sha256'])
                checked.update(group=group, id=item['id'])
                entries.append(checked)
        packets.append({'task_id': data['task_id'], 'files': entries})
    assert len(packets) == 20
    result = {'checked_at': datetime.now(timezone.utc).isoformat(),
              'frozen_files_verified': len(frozen), 'new_task_submissions': len(submissions),
              'new_native_files': sum(len(s['files']) for s in submissions),
              'judge_packets': len(packets),
              'judge_packet_files_verified': sum(len(p['files']) for p in packets),
              'all_hashes_match': True,
              'scope': 'File integrity and recorded display acknowledgements only; not judge accuracy or human acceptance.',
              'frozen_files': frozen, 'submissions': submissions, 'packets': packets}
    (OUT / 'final-integrity.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('frozen_files', 'submissions', 'packets')}))


if __name__ == '__main__':
    main()
