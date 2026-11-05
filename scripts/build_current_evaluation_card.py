"""Evidence record for this development study; documentation is not validation."""
from pathlib import Path
from run_completion_and_pairs import read,write,sha,utc
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/current_study_06'
def build():
 c=read(OUT/'summary.json');cfg=read(ROOT/c['paired_config']);maps={m['instance_id']:m for m in read(ROOT/'data/evidence_upgrade_01/grader/evidence_maps.json')}
 families=[]
 for f in sorted({j['family_id'] for j in cfg['jobs']}):
  task=read(ROOT/'data/evidence_upgrade_01/solver'/(f+'__baseline.json'));m=maps[f+'__baseline']
  families.append({'id':f,'occupation':task['occupation'],'source_task_id':task['source_task_id'],'split':'inspected_development','rights_status':m['rights_status'],'independent_review':m['independent_review'],'training_eligible':False})
 card={'schema':'project-evidence-card-v1','updated_at':utc(),'title':'Paired foreground-conflict professional-work diagnostic',
  'intended_use':'Develop and inspect a test of whether authoritative evidence survives into the final professional deliverable.',
  'main_caveat':'Human acceptance and consequential errors remain unmeasured; selected inspected families are not held-out evaluation.',
  'question':c['actual_pair_contrast'],'families':families,'protocol':{'path':c['paired_config'],'sha256':sha(ROOT/c['paired_config']),
     'model':c['fixed_model'],'attempts':10,'family_count':5,'repeat_per_condition':1,'randomization_seed':cfg['seed'],'seed_scope':cfg['seed_scope'],
     'analysis_unit':'task family','transport_retry_policy':cfg['transport'],'post_hoc_engineering_phases_excluded_from_primary_pairs':True},
  'task_equivalence':{'record':c['pair_equivalence_audit'],'canonical_facts_contract_workspace_clarifications_preserved':True,'baseline_also_contains_draft_records':True,'independent_domain_review':'pending'},
  'native_workflow':{'tools':['search_files','read_file','ask_requester','write_document','write_workbook','inspect_file','view_page','submit_files'],'formats':['DOCX','XLSX'],'inputs':'text/table extracts','clarification':'scripted recorded replies; not live people','visual_comprehension_certified':False},
  'outcomes':{k:c[k] for k in ('paired_finished_attempts','paired_submitted_attempts','pairs_with_both_submitted','human_reviewed_outputs','human_acceptance','paired_acceptance_difference','consequential_errors')},
  'grader':{'config':'config/grader_checks_05.json','response_record':'output/grader_checks_05/summary.json','constructed_labels':'Author-intended, not independently validated gold.','human_agreement':None,'quote_format_diagnostic':'output/grader_checks_05/quote_format_summary.json','secondary_quote_normalization_used_for_primary_scores':False},
  'cost':c['cost'],'auxiliary_request_recovery_probe':c.get('request_recovery_probe'),'data_leakage_controls':['Private evidence maps and labels outside solver tools.','No training performed.','All inspected family derivatives excluded from future training.','Public pretraining exposure is unknown.'],
  'unsupported_claims':['Model ranking','Population reliability','Expert acceptance','Held-out generalization','Training improvement','Lab endorsement','Commercial rights clearance'],
  'evidence':{'summary':'output/current_study_06/summary.json','verification':'output/current_study_06/verification.json','report':'output/pdf/turing-native-study-and-two-pitches.pdf','human_review_workspace':'reviews/calibration_ready_01/index.html'},
  'documentation_limit':'This card organizes evidence. It does not establish evaluation validity or superiority.'}
 write(OUT/'evaluation_card.json',card);return card
if __name__=='__main__':build()
