"""Prepare an unrun change-control contract repair without editing frozen studies.

This is a candidate task specification, not independent domain validation or a
native-file agent implementation. No API client is imported or called.
"""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'data/contract_repair_01'
DELIVERABLES = [
    {'role': 'sop', 'format': 'docx', 'description': 'Change Control SOP'},
    {'role': 'request_form', 'format': 'docx', 'description': 'Usable Change Request Form template; factual event fields blank'},
    {'role': 'tracker', 'format': 'xlsx', 'description': 'Change Log Tracker template with the source-required columns; no invented events'},
]


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def contract_text(deliverables):
    rows = ['DELIVERABLE CONTRACT FOR THIS ADAPTED TASK',
            f'Submit exactly {len(deliverables)} separate files:']
    rows += [f'{i}. {d["description"]} ({d["format"].upper()}).'
             for i, d in enumerate(deliverables, 1)]
    rows += ['The tracker is an explicit required deliverable, consistent with reference Section 3B.',
             'Do not invent a completed change event, approval, signature or tracker history.',
             'File names may vary; roles, file types and required business content must be clear.']
    return '\n'.join(rows)


def validate(task, rubric):
    """Fail on contract drift before any future model dispatch."""
    ds = task.get('deliverables')
    if ds != DELIVERABLES:
        raise ValueError('Missing or changed required deliverable role/type specification')
    if task.get('deliverable_count') != len(ds) or rubric.get('count') != len(ds):
        raise ValueError('Task/grader file-count disagreement')
    if task.get('deliverable_format') != 'mixed' or rubric.get('format') != 'mixed':
        raise ValueError('Task/grader must explicitly allow mixed DOCX/XLSX files')
    if rubric.get('deliverables') != ds:
        raise ValueError('Task/grader role/type disagreement')
    if contract_text(ds) not in task['prompt']:
        raise ValueError('The solver-visible prompt is missing the complete contract')
    if 'Please submit both the SOP and the Change Request Form' in task['prompt']:
        raise ValueError('Old two-deliverable instruction remains')
    return True


def repair(task, rubric):
    candidate = copy.deepcopy(task)
    candidate['parent_v2_1_sha256'] = sha(json.dumps(task, indent=2).encode() + b'\n')
    candidate['version'] = 'contract-repair-01-unrun-candidate'
    candidate['prompt'] = candidate['prompt'].replace(
        'Please submit both the SOP and the Change Request Form as soon as possible.',
        'Submit the SOP, Change Request Form template and Change Log Tracker specified below.')
    candidate['prompt'] += '\n' + contract_text(DELIVERABLES) + '\n'
    candidate['deliverables'] = copy.deepcopy(DELIVERABLES)
    candidate['deliverable_format'] = 'mixed'
    candidate['deliverable_count'] = 3
    candidate['candidate_status'] = 'not_run_pending_independent_domain_review'
    grading = copy.deepcopy(rubric)
    grading.update(version=candidate['version'], format='mixed', count=3,
                   deliverables=copy.deepcopy(DELIVERABLES), expert_review='pending')
    grading['rubric'] += (' Also supply a separate Excel Change Log Tracker template with '
                         'Change ID, Project, Date Submitted, Requestor, Summary, Risk Level, '
                         'Status, Outcome, Last Updated By and Date Closed. Do not invent '
                         'approved events. Judge role and content, not a fixed filename. '
                         'A formatting/file pass does not establish business acceptance.')
    validate(candidate, grading)
    return candidate, grading


def write_new(path, obj):
    blob = (json.dumps(obj, indent=2) + '\n').encode()
    if path.exists() and path.read_bytes() != blob:
        raise RuntimeError('Refusing to overwrite different candidate: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return sha(blob)


def main():
    originals = json.loads((ROOT / 'data/paired_v2/grader/rubrics.json').read_text())
    rubric = next(r for r in originals if r['id'] == 'change_control')
    files = []; shared_rubric = None
    for variant in ['baseline', 'recovery', 'conflict']:
        source = ROOT / 'data/paired_v2_1/solver' / f'change_control__{variant}.json'
        blob = source.read_bytes()
        task, updated_rubric = repair(json.loads(blob), rubric)
        task['parent_v2_1_sha256'] = sha(blob)
        dest = DEST / 'solver' / source.name
        files.append({'path': str(dest.relative_to(ROOT)), 'sha256': write_new(dest, task),
                      'parent_path': str(source.relative_to(ROOT)), 'parent_sha256': sha(blob)})
        if shared_rubric is not None:
            assert updated_rubric == shared_rubric
        shared_rubric = updated_rubric
    write_new(DEST / 'grader/rubric.json', shared_rubric)
    manifest = {
        'status': 'unrun_candidate_not_independently_validated',
        'scope': 'One development-only change-control family, all three information variants.',
        'repair': 'One explicit SOP DOCX + blank form DOCX + empty tracker XLSX contract in prompt, metadata and rubric.',
        'authorship': 'Assistant-authored adaptation, not a newly recovered original GDPval instruction.',
        'unchanged': ['reference content', 'workspace evidence and authority', 'audit facts', 'clarifications'],
        'cautions': ['Adds an explicit third-file obligation relative to the old runner; old/new scores are not a causal model comparison.',
                     'Not a purchasing family; this repairs audit integrity, not occupation coverage.',
                     'Independent review must still confirm the scope choice, realism and solvability.',
                     'A future native-file runner must support mixed formats and pass validate(); old runners are not upgraded here.',
                     'Commercial source permissions remain unverified.'],
        'model_runs': 0, 'independent_reviews': 0, 'training_eligible': False,
        'files': files,
        'rubric_sha256': sha((DEST / 'grader/rubric.json').read_bytes()),
    }
    write_new(DEST / 'manifest.json', manifest)
    write_new(DEST / 'review_form.template.json', {
        'purpose': 'Independent review of the adapted task, not model-output grading.',
        'reviewer_id': None, 'role_and_experience': None, 'independent_of_author': None,
        'reviewed_candidate_hashes': [], 'three_file_scope_plausible': None,
        'blank_form_and_tracker_appropriate': None, 'same_objective_across_variants': None,
        'authority_and_chronology_consistent': None, 'solvable_with_planned_tools': None,
        'approve': None, 'evidence_and_corrections': None, 'review_minutes': None,
    })
    print(json.dumps({'candidate_instances': len(files), 'model_runs': 0,
                      'independent_reviews': 0, 'destination': str(DEST)}))


if __name__ == '__main__':
    main()
