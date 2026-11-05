"""Local CLI adapter over the frozen v2 native workspace. No API calls.

Each fresh in-app solver sees only its original task and native references.
The shared filesystem is instruction-isolated, not an OS security boundary.
Image acknowledgments are explicit local display receipts, not API receipts.
"""
import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from evaluation_v2_workspace import Workspace as BaseWorkspace, TOOLS, SYSTEM, sha, write
from evaluation_v2_compat_workspace import xml_signature
import zipfile
import xml.etree.ElementTree as ET
import re

ROOT = Path(__file__).resolve().parents[1]

class Workspace(BaseWorkspace):
    """Normalize namespace serialization for native import, without source edits."""
    def _import_copy(self, source, folder):
        source, folder = Path(source), Path(folder)
        if source.suffix not in ('.xlsx', '.docx', '.pptx'):
            return source
        replacements = {}
        with zipfile.ZipFile(source) as archive:
            for member in ('[Content_Types].xml', '_rels/.rels'):
                payload = archive.read(member)
                root = ET.fromstring(payload)
                match = re.search(rb'<([A-Za-z0-9_]+):(Types|Relationships)\b', payload)
                if match:
                    prefix = match.group(1)
                    normalized = payload.replace(b'<'+prefix+b':', b'<').replace(b'</'+prefix+b':', b'</').replace(b'xmlns:'+prefix+b'=', b'xmlns=')
                    if xml_signature(root) != xml_signature(ET.fromstring(normalized)):
                        raise ValueError('Namespace rewrite changed XML content')
                    replacements[member] = normalized
        if not replacements:
            return source
        folder.mkdir(parents=True, exist_ok=True)
        target = folder/('import-compatible'+source.suffix)
        original_sha = sha(source)
        with zipfile.ZipFile(source) as before, zipfile.ZipFile(target, 'w') as after:
            after.comment = before.comment
            for info in before.infolist():
                after.writestr(info, replacements.get(info.filename, before.read(info.filename)))
        with zipfile.ZipFile(source) as before, zipfile.ZipFile(target) as after:
            changed = [n for n in before.namelist() if before.read(n) != after.read(n)]
            if set(changed) != set(replacements):
                raise ValueError('Unexpected content change')
        if sha(source) != original_sha:
            raise ValueError('Original source changed')
        manifest = {'adapter_version': 'v3-opc-namespace-only', 'original_path': str(source),
          'original_sha256': original_sha, 'derived_path': str(target), 'derived_sha256': sha(target),
          'changed_members': changed, 'xml_expanded_names_attributes_child_order_and_text_preserved': True,
          'all_other_member_bytes_identical': True}
        write(folder/'import-compatibility.json', manifest)
        return target

    def _engine(self, folder, kind, content, path, template=None, coverage=None):
        if template:
            template = self._import_copy(template, Path(folder)/'compatibility')
        return super()._engine(folder, kind, content, path, template, coverage)

    def _render_office(self, path, folder):
        compatible = self._import_copy(path, Path(folder)/'compatibility')
        return super()._render_office(compatible, folder)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--task', required=True)
    p.add_argument('--area', choices=['preflight', 'solver'], default='solver')
    p.add_argument('--request', type=Path)
    p.add_argument('--ack', type=Path, help='JSON array of queued image records, after displaying them')
    p.add_argument('--describe', action='store_true')
    args = p.parse_args()
    tasks = [json.loads(x) for x in (ROOT/'data/evaluation_v3/tasks.jsonl').read_text().split('\n') if x.strip()]
    matches = [x for x in tasks if x['task_id'].startswith(args.task)]
    if len(matches) != 1:
        raise ValueError('Task prefix must uniquely match a selected task')
    task = matches[0]
    folder = ROOT/'output/evaluation_v3'/args.area/task['task_id']
    workspace = Workspace(task, folder)
    if args.describe:
        print(json.dumps({'task_id': task['task_id'], 'prompt': task['prompt'], 'tools': TOOLS,
          'base_system': SYSTEM,
          'local_adapter_difference': 'In-app solver may use code only to prepare JSON tool arguments and calculate. Source reads and native writes use this CLI. No external browsing/actions. Original prompt unchanged. No fixed API turn/token cap. Local image display is separately acknowledged.',
          'today': '2026-11-04', 'timezone': 'America/New_York'}, ensure_ascii=False))
        return
    if args.ack:
        items = json.loads(args.ack.read_text())
        if not isinstance(items, list) or any(i not in workspace.image_queue for i in items):
            raise ValueError('Acknowledgment must match queued image records')
        receipts = [{**i, 'image_sha256': sha(i['path'])} for i in items]
        workspace.acknowledge_images(items)
        for item in items:
            workspace.image_queue.remove(item)
        workspace.events.append({'tool': 'local_image_display_receipt', 'items': receipts,
          'time': datetime.now(timezone.utc).isoformat(), 'attestation': 'solver reports display through view_image; not independent gaze verification'})
        workspace._persist()
        print(json.dumps({'acknowledged': len(items)}))
        return
    if not args.request:
        raise ValueError('Supply --describe, --request or --ack')
    request = json.loads(args.request.read_text())
    reply = workspace.call(request['tool'], request.get('arguments', {}))
    print(json.dumps({'reply': reply, 'queued_images': workspace.image_queue}, ensure_ascii=False))

if __name__ == '__main__':
    main()
