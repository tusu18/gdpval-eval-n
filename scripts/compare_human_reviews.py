"""Compare real reviewer exports without inventing consensus or adjudication.

Counts are primary. Cluster intervals are descriptive, not population accuracy.
Input files and the original single-reviewer scorer remain unchanged.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import random
from score_human_submission_reviews import validated_rows

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {'contract_ambiguity','invalid_serialization','approval_bypass',
              'unsupported_continuity','unsupported_eligibility','missing_comparison',
              'page_overflow','no_issue','insufficient_evidence'}


def ratio(n, d):
    return {'numerator': n, 'denominator': d, 'value': n/d if d else None}


def interval(events):
    """Events are (family, success). Resample entire source-family blocks."""
    groups = defaultdict(list)
    for family, success in events: groups[family].append(int(success))
    if len(groups) < 2:
        return {'interval_95': None, 'reason': 'Fewer than two observed source families.'}
    if len({x for _, x in events}) < 2:
        return {'interval_95': None, 'reason': 'All outcomes identical; empirical bootstrap would be degenerate and is not a reliability bound.'}
    rng = random.Random(20261102); draws = []; families = sorted(groups)
    for _ in range(5000):
        sample = [v for f in rng.choices(families, k=len(families)) for v in groups[f]]
        draws.append(sum(sample)/len(sample))
    draws.sort()
    return {'interval_95': [draws[124], draws[4874]], 'method': 'descriptive source-family block bootstrap; 5000 resamples',
            'family_count': len(groups), 'population_inference_supported': False,
            'caveat': 'Purposive sample; at most five families. This interval is not a certification of grader reliability.'}


def reviewer_metrics(doc, mapping):
    rows = validated_rows(doc, mapping); eligible = [r for r in rows if mapping[r['review_id']]['calibration_queue']]
    metrics = {}
    for field, judge_field in [('consequential_error','critical_error'), ('content_acceptable','content_acceptable')]:
        pairs = []; exclusions = Counter()
        for row in eligible:
            record = mapping[row['review_id']]
            if row['evaluation_defect'] != 'no': exclusions['defect_or_uncertain_validity'] += 1; continue
            if row[field] == 'uncertain': exclusions['uncertain_human_label'] += 1; continue
            judge = (record.get('primary_judge') or {}).get(judge_field)
            if type(judge) is not bool: exclusions['missing_judge_label'] += 1; continue
            pairs.append((record['family_id'], row[field]=='yes', judge))
        m = Counter((h,j) for _,h,j in pairs)
        tp,fn,fp,tn = m[True,True],m[True,False],m[False,True],m[False,False]
        result = {'comparable': len(pairs), 'families': len({f for f,_,_ in pairs}),
                  'matrix': {'human_yes_judge_yes':tp,'human_yes_judge_no':fn,
                             'human_no_judge_yes':fp,'human_no_judge_no':tn},
                  'agreement': ratio(tp+tn,len(pairs)),
                  'agreement_uncertainty': interval([(f,h==j) for f,h,j in pairs]),
                  'exclusions': dict(exclusions)}
        if field=='consequential_error':
            result['error_sensitivity'] = ratio(tp,tp+fn)
            result['missed_error_fraction'] = ratio(fn,tp+fn)
            result['false_alarm_fraction'] = ratio(fp,fp+tn)
            result['sensitivity_uncertainty'] = interval([(f,j) for f,h,j in pairs if h])
        else:
            result['false_accepts_among_judge_accepts'] = ratio(fp,tp+fp)
            result['false_rejects_among_human_accepts'] = ratio(fn,tp+fn)
            result['false_accept_uncertainty'] = interval([(f,not h) for f,h,j in pairs if j])
        metrics[field] = result
    return {'reviewer_id':doc.get('reviewer_id'), 'qualification':doc.get('qualification'),
            'independent_of_author':doc.get('independent_of_author'),
            'human_completed':len(rows), 'calibration_completed':len(eligible),
            'calibration_planned':sum(x['calibration_queue'] for x in mapping.values()),
            'missing_review_minutes':sum(r.get('review_minutes') is None for r in rows),
            'recorded_review_minutes':sum(r.get('review_minutes') or 0 for r in rows),
            'metrics':metrics}


def compare(first, second, mapping):
    if not first.get('reviewer_id') or first.get('reviewer_id') == second.get('reviewer_id'):
        raise ValueError('Two distinct declared reviewer identifiers are required; distinct names alone do not prove independence.')
    a = {r['review_id']:r for r in validated_rows(first,mapping)}
    b = {r['review_id']:r for r in validated_rows(second,mapping)}
    shared = sorted(a.keys() & b.keys()); matrices = {}; disagreements = []
    for field in ['content_acceptable','consequential_error','evaluation_defect','category']:
        pairs = []; missing = []
        for rid in shared:
            if field=='category' and not mapping[rid]['failure_queue']: continue
            av,bv = a[rid].get(field),b[rid].get(field)
            if field=='category':
                if av and av not in CATEGORIES or bv and bv not in CATEGORIES:
                    raise ValueError('Unrecognized taxonomy label; version the taxonomy before scoring it.')
                if not av or not bv: missing.append(rid); continue
            # Preserve uncertain/defect labels in inter-rater agreement instead of
            # deleting precisely the cases on which humans disagree.
            pairs.append((mapping[rid]['family_id'],av,bv))
            if av!=bv: disagreements.append({'review_id':rid,'field':field,'reviewer_a':av,'reviewer_b':bv,
                                           'adjudicated_label':None})
        counts = Counter((x,y) for _,x,y in pairs); n=len(pairs)
        agreement = sum(x==y for _,x,y in pairs)
        ma=Counter(x for _,x,_ in pairs); mb=Counter(y for _,_,y in pairs)
        pe=sum(ma[k]*mb[k] for k in ma.keys()|mb.keys())/(n*n) if n else None
        kappa=(agreement/n-pe)/(1-pe) if n and pe<1 else None
        matrices[field] = {'paired_labels':n,'agreement':ratio(agreement,n),
                           'confusion_counts':[{'reviewer_a':x,'reviewer_b':y,'count':v} for (x,y),v in sorted(counts.items())],
                           'cohen_kappa':kappa, 'missing_category_ids':missing,
                           'agreement_uncertainty':interval([(f,x==y) for f,x,y in pairs]),
                           'caveat':'Agreement is descriptive, not evidence either reviewer is correct. Kappa is sensitive to prevalence and category mix.'}
    return {'schema':'turing-two-reviewer-comparison-v1','status':'observed_labels_only_no_adjudication',
            'reviewers':[reviewer_metrics(first,mapping),reviewer_metrics(second,mapping)],
            'shared_completed_attempts':len(shared), 'only_first_reviewed':sorted(a.keys()-b.keys()),
            'only_second_reviewed':sorted(b.keys()-a.keys()), 'inter_rater':matrices,
            'disagreements_requiring_adjudication':disagreements,
            'model_recommendation':None,
            'limits':'Do not average conflicting labels into gold truth. Qualifications and independence are self-declared. Selected public families and repeated variants do not establish population reliability.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('first',type=Path); parser.add_argument('second',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'output/submission_audit/two_reviewer_comparison.json')
    args=parser.parse_args()
    mapping={x['review_id']:x for x in json.loads((ROOT/'output/submission_audit/private_review_key.json').read_text())}
    result=compare(json.loads(args.first.read_text()),json.loads(args.second.read_text()),mapping)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f: json.dump(result,f,indent=2); f.write('\n')
    print(json.dumps({'output':str(args.output),'shared_completed_attempts':result['shared_completed_attempts']}))
