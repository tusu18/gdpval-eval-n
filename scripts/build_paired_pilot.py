"""Construct a local paired pilot from pinned GDPval prompts and reference extracts.

No teacher samples, gold deliverables, or paid model calls are used here.
Synthetic workflow records are explicitly identified in provenance, not in the solver cue.
"""
import json, hashlib, random, datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/paired_v1'
def dump(p,x):
    p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(x,indent=2,ensure_ascii=False))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    rows={r['task_id']:r for r in map(json.loads,(ROOT/'data/gdpval/solver/tasks.jsonl').read_text().splitlines())}
    refs=json.loads((ROOT/'research/reference_text.json').read_text())
    # All selections and mutations are frozen before the first solver request.
    specs=[
      dict(id='ev_localization',source='93b336f3-61f3-4287-86d2-87445e1e0f90',where='prompt',
           old='110K units per year for 5 years',missing='the volume and duration recorded in the commercial planning workspace',stale='150K units per year for 5 years',
           record='Annual volume: 110000 packs. Program duration: 5 years.',draft='Annual volume: 150000 packs. Program duration: 5 years.',
           keys=['annual_volume','program_years','unit_savings_inr','annual_savings_inr','five_year_savings_inr'],
           truth={'annual_volume':110000,'program_years':5,'unit_savings_inr':103910,'annual_savings_inr':11430100000,'five_year_savings_inr':57150500000},
           consequence='Overstates recurring savings and the five-year business case.',format='docx',count=1,
           rubric='Compute unchanged child parts as (10000-1300-200)*83 = 705500 INR; local pack cost 726090 INR; unit saving 103910 INR. Annual volume 110000 for 5 years. Ownership is 49:51 EvTronics:EV Batteries. Do not describe assembly-only localization as full cell localization or eliminate imported-cell forex risk. Historical policy statements are scenario assumptions, not current legal advice.'),
      dict(id='supplier_exit',source='15ddd28d-8445-4baa-ac7f-f41372e1344e',where='prompt',
           old='within just three weeks',missing='on the date specified in the supplier correspondence workspace',stale='within twelve weeks',
           record='LPI supply cessation notice period: 21 calendar days from today. No extension has been agreed.',draft='LPI supply cessation notice period: 84 calendar days from today. No extension has been agreed.',
           keys=['notice_days','monthly_sets','electronics_min_months','electronics_max_months'],
           truth={'notice_days':21,'monthly_sets':800,'electronics_min_months':4,'electronics_max_months':5},
           consequence='Delays continuity action beyond the supplier cutoff and risks stopping production.',format='docx',count=1,
           rubric='Plan for a 21-day supply cutoff, 800 sets/month, 4-5 month electronics redevelopment, 3-4 months plastics in parallel, 25-day tooling transfer. Distinguish proposals from agreements. Do not promise an unverified local supplier can qualify inside three weeks. Include sincere resolution, quantified bridge stock or supply, BATNA, conditional ZOPA, tooling ownership and a viable transition timeline.'),
      dict(id='sourcing_approvals',source='1b1ade2d-f9f6-4a04-baa5-aa15012b53be',where='prompt',
           old='approvals from the Finance controllers, Program managers, and Purchase teams',missing='approvals from the roles listed in the sourcing governance workspace',stale='approval from the Purchase team alone',
           record='Price change request approvals: Finance controllers, Program managers, and Purchase teams. All three are required.',draft='Price change request approval: Purchase team alone.',
           keys=['price_change_approvers'],truth={'price_change_approvers':['finance','program','purchase']},
           consequence='Allows commercial commitments without the required financial and program approvals.',format='docx',count=1,
           rubric='Include Finance, Program Management and Purchase approvals for price changes. Retain ER/Quality/Purchase TRSO signoff and nomination approvals. Include modular quotation cost drivers, version control, digital approval history and a practical path for late changes. Do not remove mandatory gates in the name of agility.'),
      dict(id='change_control',source='fd6129bd-f095-429b-873c-dcc3137be2c3',where='Change Control SOP Working Session Internal Input Summary.docx',
           old='Budget overage > $5,000',missing='Budget overage threshold: consult the change governance workspace',stale='Budget overage > $50,000',
           record='Formal change control is triggered when a budget overage is strictly greater than USD 5000.',draft='Formal change control is triggered when a budget overage is strictly greater than USD 50000.',
           keys=['budget_trigger_usd','budget_trigger_operator','review_required_for_6000_overage'],
           truth={'budget_trigger_usd':5000,'budget_trigger_operator':'>','review_required_for_6000_overage':True},
           consequence='A USD 6000 overage bypasses formal review under the obsolete threshold.',format='docx',count=2,
           rubric='SOP triggers include budget overage strictly >5000 USD and timeline shift >2 business days, plus scope and filing impacts. Low-risk fast track still needs PM+QA and logging. Preserve conditional Finance/Regulatory reviews, PM Lead signoff, archived written approvals and version control. Supply SOP and request form with all fields. No specific change case is supplied: leave factual entries unknown or clearly label illustrative entries; do not invent approved business events.'),
      dict(id='shipment_manifest',source='76418a2c-a3c0-4894-b89d-2493369135d9',where='Shipping parameters.xlsx',
           old='flat rate $150',missing='flat rate: consult the TMS rate workspace',stale='flat rate $110',
           record='Freight flat rate per qualifying shipment: USD 150. Industry average: USD 225. This rate is independent of weight within this category.',draft='Freight flat rate per qualifying shipment: USD 110. Industry average: USD 225.',
           keys=['freight_cost_usd','freight_savings_usd','total_shipping_cost_usd','total_savings_usd'],
           truth={'freight_cost_usd':150,'freight_savings_usd':75,'total_shipping_cost_usd':230.95,'total_savings_usd':81.99},
           consequence='Understates freight cost and overstates the saving promised to customers by USD 40.',format='xlsx',count=1,
           rubric='A-1001 Bergman: 2.5 lb UPS, cost5.95, benchmark7.95, savings2.00. B-5005 Grandger:250 lb Freight, cost150, benchmark225, savings75. C-2001 Stretman:50 lb Fed Ex, cost75, benchmark79.99, savings4.99. Totals230.95,312.94,81.99. Preserve all nine manifest columns. Do not invent tracking numbers. Rate-band boundary gaps exist in the source but none of these three shipments is at a boundary.'),
    ]
    instances=[]; grader=[]
    for s in specs:
        r=rows[s['source']]
        basefiles={Path(f).name:refs['research/'+f] for f in r['reference_files']}
        for variant in ['baseline','recovery','conflict']:
            prompt=r['prompt']; files=dict(basefiles)
            replacement={'baseline':s['old'],'recovery':s['missing'],'conflict':s['stale']}[variant]
            if s['where']=='prompt':
                assert prompt.count(s['old'])==1; prompt=prompt.replace(s['old'],replacement)
            else:
                assert files[s['where']].count(s['old'])==1
                files[s['where']]=files[s['where']].replace(s['old'],replacement)
            # The timestamp trap is intentional: a more recent proposal is not an approved record.
            operational={
              'registry.txt':'Operations document registry\nrecord-17.txt: revision 2; approved 2025-06-20; status in force; approved by process owner.\nrecord-22.txt: revision 3; created 2025-06-23; status draft; not approved.\nThe registry, not recency alone, determines which record is operative.',
              'record-17.txt':s['record'],
              'record-22.txt':s['draft'],
            }
            if variant=='conflict':
                files['working-notes.txt']='Working notes copied on 2025-06-23 from a revision-3 proposal. '+s['draft']
            common='\n\nWORKSPACE ACCESS\nThe attached documents below are text/table extracts of the source files. An operations workspace is available through list_workspace and read_record. It can contain approved records and unapproved drafts. If sources disagree, apply the operative approval status. Produce the requested professional deliverables, state unresolved assumptions, and do not invent missing facts. Do not send communications externally.'
            if s['id']=='ev_localization': common+=' Treat the described government policies as fixed historical scenario assumptions; current-law verification is outside this exercise.'
            if s['id']=='change_control': common+=' No specific change request event has been provided; provide the complete usable form with factual fields unfilled or clearly marked for completion.'
            entry={'instance_id':s['id']+'__'+variant,'family_id':s['id'],'source_task_id':s['source'],'occupation':r['occupation'],'variant':variant,
              'prompt':prompt+common,'attachments':files,'workspace':operational,
              'fact_keys':s['keys'],'deliverable_format':s['format'],'deliverable_count':s['count']}
            dump(OUT/'solver'/f"{entry['instance_id']}.json",entry);instances.append(entry['instance_id'])
        grader.append({**s,'expert_review':'pending','design_review':'assistant preflight only','split':'public_diagnostic_eval_only',
                       'baseline_note':'Source-derived baseline; shared tools, text extraction and harness instructions differ from official GDPval.'})
    dump(OUT/'grader'/'rubrics.json',grader)
    selection=[]
    for r in rows.values():
        sid=r['task_id']; match=next((s for s in specs if s['source']==sid),None)
        note='Not selected for this mechanism pilot; not a finding of invalidity.'
        if sid.startswith('11dcc'):note='Quarantined: all three received item IDs are absent from location register; special item P11-P09457-01 has no received quantity in supplied log.'
        if sid.startswith('ce864'):note='Quarantined: timesheets include Ellen Zhu, absent from 23-person registry; March 31 coverage/capacity convention also needs clarification.'
        if sid.startswith('5349') or sid.startswith('02aa'):note='Deferred: depends on external live/historical source retrieval outside the controlled workspace.'
        if sid.startswith('a4a'):note='Deferred: linked standard excerpt is not a full licensed standard; requires source and domain validation.'
        selection.append({'source_task_id':sid,'selected':bool(match),'reason':'Readable, bounded critical-fact intervention; no observed blocking source defect.' if match else note})
    dump(OUT/'selection_audit.json',selection)
    protocol={
      'version':'paired-v1','frozen_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'frozen_before_solver_calls',
      'source_revision':'11e7900cdcac61bc4daf59e65feb238acda98fbf','families':5,'occupations':3,'instances':15,'trials_per_system':2,
      'models':['openai/gpt-6.1-sol','anthropic/claude-sonnet-5.5'],
      'model_choice':'Two current tool-capable systems from different vendors, with identical listed standard text-token prices. Selection precedes outcomes; no best-model or equal-compute claim.',
      'reasoning_effort':'medium','max_completion_tokens_per_call':6500,'max_calls_per_run':5,'max_input_bytes_per_call':55000,
      'budget_cap_usd':25,'solver_budget_cap_usd':18,'price_cap_per_million':{'prompt':2,'completion':10},
      'tools':['list_workspace','read_record'],'tool_access':'exact in-memory allowlist only; no shell, network or grader access',
      'primary_metric':'Fraction of runs with every preregistered critical decision field correct (diagnostic, not full deliverable acceptance).',
      'secondary_metrics':['explicit wrong critical-decision rate','missing critical-decision rate','recovery completion conditional on reading the operative record','authority resolution with registry access','provisional blinded model-judge acceptance','API cost per critical-check pass','wall latency','evaluation defects'],
      'estimator':'Within-family variant-minus-baseline difference averaged over two trials and five families; enumerate discordant pairs. Family bootstrap 10000 draws, descriptive only at n=5.',
      'exclusions':'Infrastructure failures reported separately; no valid wrong answer retries. Preflight source defects excluded before scores. Any discovered evaluation defect remains in audit with affected-run counts; never recode it as a model failure.',
      'human_review_minutes':None,'human_expert_agreement':None,
      'contamination':'All source families and their variants evaluation-only. No SFT/RL here. Sources are public and author inspected source/rubric context; unknown provider pretraining exposure. Solver API sees only selected allowlisted inputs, never gold/rubrics/other runs. Local timestamps and hashes are audit aids, not third-party preregistration.',
      'generation':'Deterministic Python transformations authored by the assistant. No teacher model generates business facts; operative values are inherited from sources. Synthetic draft values and approval metadata are manually specified in build_paired_pilot.py. Seed 20261030 randomizes run order only, not semantic fact generation.',
      'permissions':'Pinned public research/evaluation inputs used locally. No explicit license file or license metadata found in repository. Commercial adaptation/redistribution rights unverified; do not distribute copied source/reference/gold assets as a licensed dataset.',
      'limitations':['Five purposively selected families, occupation mix 3 purchasing / 1 project management / 1 shipping','Same author designs mutations and deterministic truth checks; independent domain validation pending','Text/table extraction removes visual/file-navigation difficulty','Structured renderer supplies layout; this is not unrestricted desktop artifact creation','Public diagnostic, not contamination-free or representative professional reliability estimate']}
    protocol['input_hashes']={str(p.relative_to(ROOT)):sha(p) for p in sorted(OUT.rglob('*.json'))}
    dump(ROOT/'config/paired_protocol.v1.json',protocol)
    order=[{'instance_id':i,'model':m,'trial':t} for i in instances for m in protocol['models'] for t in [1,2]]
    random.Random(20261030).shuffle(order);dump(OUT/'run_order.json',order)
    print(json.dumps({'families':5,'instances':len(instances),'planned_runs':len(order),'protocol_sha256':sha(ROOT/'config/paired_protocol.v1.json')}))
if __name__=='__main__':main()
