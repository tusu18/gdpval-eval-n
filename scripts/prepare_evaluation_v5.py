"""Prepare offline text-only constraint interventions from six existing documents."""
import copy, hashlib, html, json, re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/evaluation_v5'; DATA=ROOT/'data/evaluation_v5'; REVIEW=ROOT/'reviews/evaluation_v5'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,d):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n')
SPECS=[
 ('1b1ade2d','sonnet','Lamp_Sourcing_Nomination_Workflow_Draft.docx',90,'Purchasing: provisional price authority',
 'Provisional authorisation: Purchase may issue a capped, time-limited Letter of Authority only after Finance Controller, Program Manager and Purchase approve the provisional price. Cap and expiry are set by Finance; the authority lapses automatically.',
 'Provisional authorisation: Finance Controller, Program Manager and Purchase must approve the provisional price before Purchase issues a capped, time-limited Letter of Authority. Finance sets its cap and expiry; the authority expires automatically.',
 'Provisional authorisation: Purchase may issue a capped, time-limited Letter of Authority after Program Manager and Purchase approve the provisional price; Finance Controller approval may follow issuance. Cap and expiry are set by Finance; the authority lapses automatically.'),
 ('1b1ade2d','opus','Revised_Sourcing_Nomination_Workflow_Lamp_Assemblies_v0.1.docx',146,'Purchasing: proceed-at-risk approval',
 'FP6 Proceed-at-risk. For Class B or C changes on the critical path, Finance Controller, PM and Purchase must approve a provisional price with capped financial exposure before tooling starts. The final price must be agreed and trued-up within 30 days (proposed).',
 'FP6 Proceed-at-risk. Before tooling starts on critical-path Class B or C changes, approval of a provisional price with capped financial exposure is required from Finance Controller, PM and Purchase. Final-price agreement and true-up are due within 30 days (proposed).',
 'FP6 Proceed-at-risk. For Class B or C changes on the critical path, PM and Purchase may approve a provisional price with capped financial exposure so tooling starts; Finance Controller approval may follow. The final price must be agreed and trued-up within 30 days (proposed).'),
 ('fd6129bd','sonnet','Change_Control_SOP.docx',116,'Change control: Finance gate',
 'If Budget Impact = Yes, Finance reviews the CR and its written approval is required before final approval.',
 'Finance must review and give written approval before final approval of any CR marked Budget Impact = Yes.',
 'If Budget Impact = Yes, Finance reviews the CR, but its written approval may be obtained after final approval.'),
 ('fd6129bd','opus','SOP_Change_Control_Project_Impacting_Changes_v1.0.docx',278,'Change control: fast-track QA gate',
 'PM and QA both record written approval before the fast-track change is approved. The PM then updates the tracker and archives the form.',
 'Approval of the fast-track change requires written approval from both QA and PM first. Afterwards, the PM updates the tracker and archives the form.',
 'PM records written approval and approves the fast-track change; QA approval may follow. The PM then updates the tracker and archives the form.'),
 ('58ac1cc5','sonnet','QA_Escalation_Email_DRAFT.docx',28,'Material release: test-result condition',
 'Option A - deviation: seek QA approval of a documented deviation and in-house endotoxin testing. Under this proposed route, release requires a test result below 1 EU/ml and QA approval; a report-only vendor COA alone is insufficient.',
 'Option A - deviation: request in-house endotoxin testing and QA approval of a documented deviation. This proposed route permits release only with QA approval and a test result below 1 EU/ml, not on a report-only vendor COA alone.',
 'Option A - deviation: seek QA approval of a documented deviation and in-house endotoxin testing. Under this proposed route, release requires a test result below 5 EU/ml and QA approval; a report-only vendor COA alone is insufficient.'),
 ('58ac1cc5','opus','QA_Escalation_Email_QY-GEL_Antifoam.docx',36,'Material release: QA disposition gate',
 'Lot 00004515 is on QA hold (quarantine). It will not be issued or kitted for the run until QA approves its disposition.',
 'Lot 00004515 remains quarantined on QA hold. QA must approve its disposition before it is issued or kitted for the run.',
 'Lot 00004515 is on QA hold (quarantine). It may be issued or kitted for the run before QA approves its disposition.')]

def prepare():
 cases=[]
 for number,(pre,model,artifact,paragraph,title,correct,para,broken) in enumerate(SPECS,1):
  cid=f'V5-{number:02d}'; paths=sorted((ROOT/'output/study_v3/judge_packets').glob(f'{pre}__original__{model}*sel*.json')); source=paths[-1]
  packet=json.loads(source.read_text()); art=next(a for a in packet['artifacts'] if a['id']==artifact)
  native=ROOT/'output/study_v3/claudecode'/f'{pre}__original__{model}__r1/outputs'/artifact
  assert sha(native)==art['sha256'], 'Native file changed since extraction'
  loc=f'word/document.xml:paragraph:{paragraph}'; assert sum(u['locator']==loc for u in art['units'])==1
  base=copy.deepcopy(art); repairs=[]
  if number==1:
   u=next(u for u in base['units'] if u['locator']=='word/document.xml:paragraph:75')
   repairs.append({'locator':u['locator'],'before':u['text'],'after':'Purchase + Finance controller + Program Manager (delegated). Quality and ER acknowledge.'});u['text']=repairs[-1]['after']
  sources=packet['source_documents']; save(DATA/cid/'sources.json',sources)
  save(DATA/cid/'original-extract.json',art)
  expected_scope=[u['locator'] for u in base['units'] if re.search(r'Finance|approv|release|disposition|quarant|endotoxin|fast.track',u['text'],re.I)]
  expected_scope=sorted(set(expected_scope+[loc]))
  variants=[]
  for label,text in [('A',correct),('B',para),('C',broken)]:
   a=copy.deepcopy(base);u=next(u for u in a['units'] if u['locator']==loc);u['text']=text
   a['text']='\n'.join(u['locator']+'\t'+u['text'] for u in a['units'])
   a['original_native_sha256']=a.pop('sha256');a['derivative_kind']='controlled_text_extract_not_modified_native_file'
   a['sha256']=hashlib.sha256(a['text'].encode()).hexdigest()
   req={'id':'TARGET','text':title+'; check operative instructions, including contradictions with other sections. Assess only this constraint, not whole-task acceptance.','source_ids':list(sources),'critical':True,'operative_sections':[{'artifact_id':artifact,'locator':l} for l in expected_scope]}
   payload={'schema':'v5-constraint-packet-1','source_documents':sources,'requirements':[req],'artifacts':[a], 'scope':'Complete selected-document text; not the complete task package. Native layout and other task requirements are outside this target endpoint.'}
   dest=DATA/cid/f'{label}.json';save(dest,payload);variants.append({'label':label,'path':str(dest.relative_to(ROOT)),'sha256':sha(dest)})
  case={'case_id':cid,'family_id':pre,'title':title,'source_packet':str(source.relative_to(ROOT)),'source_packet_sha256':sha(source),'native_original':str(native.relative_to(ROOT)),'native_sha256':sha(native),'target_locator':loc,'original_target':next(u['text'] for u in art['units'] if u['locator']==loc),'common_control_repairs':repairs,'variants':variants,'scope_proposal':expected_scope,'human_validation':'pending','expected_labels_private':{'A':'pass','B':'pass','C':'fail'},'author_expectation_is_not_gold':True}
  save(DATA/cid/'provenance.json',case)
  content=[f'<h1>{cid}: {html.escape(title)}</h1><p>Informed review of controlled text derivatives. Expected labels are not human truth. This page contains the full provided source extracts and the complete selected document in all three versions. Other task deliverables and native layout are outside scope.</p>',f'<p>Target location: {loc}. The proposed coverage list has {len(expected_scope)} locations and requires human confirmation.</p>','<h2>Sources</h2>']
  for key,value in sources.items():content.append(f'<details open><summary>{html.escape(key)}</summary><pre>{html.escape(value)}</pre></details>')
  for label in ['A','B','C']:
   payload=json.loads((DATA/cid/f'{label}.json').read_text());a=payload['artifacts'][0]
   content.append(f'<h2>Complete document — version {label}</h2>')
   for u in a['units']:content.append(f'<p class="{"target" if u["locator"]==loc else ""}"><small>{html.escape(u["locator"])}</small><br>{html.escape(u["text"])}</p>')
  content.append('<h2>Common repairs and scope</h2><pre>'+html.escape(json.dumps({'common_repairs':repairs,'scope_proposal':expected_scope},indent=2))+'</pre>')
  page=REVIEW/cid/'review.html';page.parent.mkdir(parents=True,exist_ok=True)
  page.write_text('<!doctype html><meta charset="utf-8"><title>'+cid+'</title><style>body{max-width:980px;margin:40px auto;font:17px/1.6 system-ui;padding:20px}pre{white-space:pre-wrap}small{color:#666}.target{border-left:4px solid #6655bb;padding:12px;background:#f5f3ff}summary{font-weight:600}</style>'+''.join(content))
  case['review_path']=str(page.relative_to(ROOT));cases.append(case)
 save(DATA/'manifest.json',{'schema':'evaluation-v5-preparation-1','cases':cases,'case_count':6,'families':3,'documents':18,'judge_calls':0,'status':'prepared_pending_human_review','sampling':'Purposive development diagnostic; two outputs per family. No independent or representative population claim.'})
 config={'schema':'evaluation-v5-protocol-1','execution_enabled':False,'planned_judge_requests':36,'repeats':0,'judges_requested':['google/gemini-4-argon','openai/gpt-6.1-sol'],'access_and_price_check':'pending before execution','source':'data/evaluation_v5/manifest.json','target':'Preservation of operative business constraints in full selected-document text','metrics':['S stability','R verdict change','correct pass-to-fail direction','false acceptance among human-fail variants','false rejection among human-pass controls','usable judgment coverage'],'denominator_rule':'Report all scheduled counts and invalid/uncertain outcomes; S/R eligible-pair denominators separate. Unknown is not pass or fail. Cluster by the three source families; descriptive pilot, no population precision claim.','required_human_fields':['source_adequate','control_target_pass','paraphrase_preserves_meaning','broken_changes_constraint','coverage_complete'],'human_review_method':'One question at a time; informed author-direction review, not blind independent validation. Store exact replies and hashes; revisions append history.','human_labels_are_authoritative':True,'no_training_or_solver_ranking_claim':True}
 save(ROOT/'config/evaluation_v5.json',config)
 response_path=REVIEW/'responses.json'
 if not response_path.exists():save(response_path,{'schema':'v5-human-responses-1','responses':[]})
 index=REVIEW/'index.html';index.write_text('<!doctype html><meta charset="utf-8"><h1>V5 — six constraint checks, human validation pending</h1><p>No judge calls have been made. These are text derivatives, not newly generated native submissions.</p>'+''.join(f'<p><a href="{c["case_id"]}/review.html">{c["case_id"]} — {html.escape(c["title"])}</a></p>' for c in cases))
 print(json.dumps({'cases':6,'families':3,'variants':18,'judge_calls':0}))
if __name__=='__main__':prepare()
