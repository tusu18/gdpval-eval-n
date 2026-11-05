"""Score actual reviewer exports; keep historical and native cohorts separate.

The file is read-only input. No gold labels, model rankings or imputed review
times are created. The historical calibration has a judge; new runs do not.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
from score_human_submission_reviews import validated_rows
from compare_human_reviews import reviewer_metrics, ratio, interval

ROOT = Path(__file__).resolve().parents[1]

def score(doc, mapping):
    rows = validated_rows(doc, mapping)
    cohorts = {}
    groups = {
        'historical_calibration': lambda x: x.get('calibration_queue') is True,
        'historical_diagnostic_extra': lambda x: not x.get('calibration_queue') and not x.get('new_native_queue'),
        'native_development': lambda x: x.get('new_native_queue') is True and x.get('native_stage','initial')=='initial' and x.get('native_output_status')=='submitted',
        'native_recovery': lambda x: x.get('native_stage')=='recovery' and x.get('native_output_status')=='submitted',
        'native_completion': lambda x: x.get('native_stage')=='completion' and x.get('native_output_status')=='submitted',
        'native_upload_repair': lambda x: x.get('native_stage')=='upload_repair' and x.get('native_output_status')=='submitted',
        'native_backoff_probe': lambda x: x.get('native_stage')=='backoff_probe' and x.get('native_output_status')=='submitted',
        'paired_development': lambda x: x.get('native_stage')=='paired' and x.get('native_output_status')=='submitted',
        'native_drafts_initial_diagnostic': lambda x: x.get('native_stage','initial')=='initial' and x.get('native_output_status')=='unsubmitted_draft',
        'native_drafts_recovery_diagnostic': lambda x: x.get('native_stage')=='recovery' and x.get('native_output_status')=='unsubmitted_draft',
        'native_drafts_completion_diagnostic': lambda x: x.get('native_stage')=='completion' and x.get('native_output_status')=='unsubmitted_draft',
        'native_drafts_upload_repair_diagnostic': lambda x: x.get('native_stage')=='upload_repair' and x.get('native_output_status')=='unsubmitted_draft',
        'native_drafts_backoff_probe_diagnostic': lambda x: x.get('native_stage')=='backoff_probe' and x.get('native_output_status')=='unsubmitted_draft',
        'paired_drafts_diagnostic': lambda x: x.get('native_stage')=='paired' and x.get('native_output_status')=='unsubmitted_draft',
        'native_no_output': lambda x: x.get('new_native_queue') is True and x.get('native_output_status')=='none',
    }
    for name, predicate in groups.items():
        selected = [r for r in rows if predicate(mapping[r['review_id']])]
        eligible = [r for r in selected if r['evaluation_defect'] == 'no']
        outcomes = {}
        for field in ('content_acceptable', 'consequential_error'):
            yes = sum(r[field] == 'yes' for r in eligible)
            known = [r for r in eligible if r[field] != 'uncertain']
            outcomes[field] = {
                'counts_valid_cases': dict(Counter(r[field] for r in eligible)),
                'yes_among_resolved_valid_cases': ratio(yes, len(known)),
                'descriptive_uncertainty': interval([(mapping[r['review_id']]['family_id'], r[field] == 'yes') for r in known]),
            }
        cohorts[name] = {
            'planned': sum(predicate(x) for x in mapping.values()),
            'completed': len(selected),
            'evaluation_validity_counts': dict(Counter(r['evaluation_defect'] for r in selected)),
            'outcomes': outcomes,
            'recorded_minutes': sum(r.get('review_minutes') or 0 for r in selected),
            'missing_minutes': sum(r.get('review_minutes') is None for r in selected),
            'human_category_counts': dict(Counter(r.get('category') or 'unassigned' for r in selected)),
        }
    return {
        'schema': 'focused-human-review-summary-v1',
        'reviewer_id': doc.get('reviewer_id'),
        'qualification': doc.get('qualification'),
        'independent_of_author': doc.get('independent_of_author'),
        'human_completed': len(rows), 'cohorts': cohorts,
        'historical_judge_calibration': reviewer_metrics(doc, mapping),
        'native_judge_agreement': None,
        'native_judge_status': 'No automatic business judge was run on the native comparison. Do not reuse historical grades.',
        'model_recommendation': None, 'total_cost_per_accepted_deliverable': None,
        'limits': 'Selected development families; counts are not population estimates. Unknowns are not failures or successes. Invalid or uncertain tasks remain visible but are excluded from business-outcome denominators. Human labels are not called expert labels without verified relevant qualifications. Review and correction labor, defect adjudication and a sufficiently broad fresh test are still needed before choosing a model.',
    }

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('review_file', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    mapping = {x['review_id']: x for x in json.loads((ROOT/'output/native_workflow_01/calibration_private_key.json').read_text())}
    result = score(json.loads(args.review_file.read_text()), mapping)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as f:
        json.dump(result, f, indent=2); f.write('\n')
    print(json.dumps({'output': str(args.output), 'human_completed': result['human_completed']}))
