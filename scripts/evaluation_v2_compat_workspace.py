"""Versioned, shipping-only OPC import compatibility adapter.

Preserve original reference bytes. In a private workspace copy, normalize only
the XML namespace serialization of [Content_Types].xml before Artifact Tool
imports an original XLSX. All other ZIP member bytes and the XML tree match.
"""
import hashlib
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import evaluation_v2_workspace as original
from run_evaluation_v2 import ROOT, OUT, digest, freeze, now, read, write

TASK = '76418a2c-a3c0-4894-b89d-2493369135d9'
BASE_WORKSPACE = original.Workspace
ENGINE = ROOT / 'scripts/evaluation_v2_compat_engine.mjs'
NAMESPACE = 'http://schemas.openxmlformats.org/package/2006/content-types'


def xml_signature(root):
    return root.tag, list(root.attrib.items()), root.text, root.tail, [xml_signature(child) for child in root]


def normalize_import_copy(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or source.is_relative_to(destination):
        raise ValueError('Original source cannot be overwritten')
    original_sha = digest(source)
    with zipfile.ZipFile(source) as before:
        if len(before.namelist()) != len(set(before.namelist())):
            raise ValueError('Duplicate ZIP members require separate review')
        payload = before.read('[Content_Types].xml')
        root = ET.fromstring(payload)
        if root.tag != '{' + NAMESPACE + '}Types':
            raise ValueError('Unexpected OPC content-types namespace/root')
        ET.register_namespace('', NAMESPACE)
        normalized = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        if xml_signature(root) != xml_signature(ET.fromstring(normalized)):
            raise ValueError('Normalization changed XML expanded names, attributes, child order or text')
        with zipfile.ZipFile(destination, 'w') as after:
            after.comment = before.comment
            for info in before.infolist():
                after.writestr(info, normalized if info.filename == '[Content_Types].xml' else before.read(info.filename))
    with zipfile.ZipFile(source) as before, zipfile.ZipFile(destination) as after:
        if before.namelist() != after.namelist():
            raise ValueError('ZIP entry sequence changed')
        changed = [name for name in before.namelist() if before.read(name) != after.read(name)]
        if set(changed) - {'[Content_Types].xml'}:
            raise ValueError('A source ZIP member outside content-types changed')
        member_hashes = {name: hashlib.sha256(before.read(name)).hexdigest() for name in before.namelist() if name != '[Content_Types].xml'}
    if digest(source) != original_sha:
        raise ValueError('Original source changed during normalization')
    return {'adapter_version': 'shipping-opc-import-v2_1', 'original_path': str(source), 'original_sha256': original_sha,
            'derived_path': str(destination), 'derived_sha256': digest(destination), 'changed_members': changed,
            'xml_expanded_names_attributes_child_order_and_text_preserved': True,
            'all_other_member_bytes_identical': True, 'unchanged_member_sha256': member_hashes,
            'purpose': 'Private native-engine import compatibility copy, not a replacement source or business-content edit.'}


class CompatibilityWorkspace(BASE_WORKSPACE):
    def _engine(self, folder, kind, content, path, template=None, coverage=None):
        if self.task['task_id'] != TASK or kind not in ('xlsx', 'inspect_xlsx') or not template:
            return super()._engine(folder, kind, content, path, template, coverage)
        folder = Path(folder)
        derived = folder / 'source-import-compatibility.xlsx'
        manifest = normalize_import_copy(template, derived)
        write(folder / 'source-import-compatibility.json', manifest)
        job = {'kind': kind, 'content': content, 'output': str(path), 'result': str(folder / 'engine-result.json'),
               'template': str(derived)}
        if coverage:
            job['coverage'] = coverage
        write(folder / 'engine-input.json', job)
        self._run([original.NODE, ENGINE, folder / 'engine-input.json'], folder)
        result = read(folder / 'engine-result.json')
        result['import_compatibility'] = manifest
        return result


def install_compatibility_adapter():
    # solve imports Workspace at runtime; all prompts, tools and arguments are
    # still the original frozen values. The conditional is one original task.
    original.Workspace = CompatibilityWorkspace


def freeze_compatibility():
    freeze()
    config = ROOT / 'config/evaluation_v2_shipping_compatibility.json'
    paths = [Path(__file__).resolve(), ENGINE, config, ROOT / 'scripts/repair_evaluation_v2_shipping.py',
             ROOT / 'scripts/dispatch_evaluation_v2_remaining.py', ROOT / 'config/evaluation_v2_budget_amendment.json', OUT / 'freeze.json']
    record = {'files': {str(path.relative_to(ROOT)): digest(path) for path in paths}, 'task_id': TASK,
              'original_reference_bytes_changed': False, 'solver_prompt_or_tools_changed': False}
    target = OUT / 'compatibility' / 'shipping-v2_1-freeze.json'
    if target.exists():
        old = read(target)
        if old['files'] != record['files']:
            raise ValueError('Compatibility amendment changed after freeze')
    else:
        write(target, {'created_at': now(), **record})
    return target
