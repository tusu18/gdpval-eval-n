"""Keep initial and post-hoc recovery outcomes and costs distinguishable."""
import json
from pathlib import Path
from summarize_native_study import summarize
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/native_workflow_01'

def main():
 first=summarize();second=summarize(ROOT/'output/native_transport_02',ROOT/'config/native_transport_02.json')
 costs={'initial_api_usd':first['cost']['reported_new_usd'],'recovery_api_usd':second['cost']['reported_new_usd'],
        'historical_api_usd':first['cost']['reported_prior_usd'],
        'reported_new_usd':first['cost']['reported_new_usd']+second['cost']['reported_new_usd'],
        'reported_cumulative_usd':first['cost']['reported_prior_usd']+first['cost']['reported_new_usd']+second['cost']['reported_new_usd'],
        'unresolved_charge_records':first['cost']['unresolved_records']+second['cost']['unresolved_records'],
        'human_labor_usd':None,'cost_per_accepted_deliverable':None}
 rows=[]
 for a,b in zip(first['by_model'],second['by_model']):
  assert a['model']==b['model']
  rows.append({'model':a['model'],'initial_submitted':a['submitted'],'initial_attempted':a['started'],
               'recovery_selected':b['planned'],'recovery_attempted':b['started'],'recovery_submitted':b['submitted'],
               'reported_api_cost_usd':a['reported_api_cost_usd']+b['reported_api_cost_usd'],
               'unresolved_charge_records':a['unresolved_cost_records']+b['unresolved_cost_records'],
               'human_accepted':None,'consequential_errors':None})
 result={'schema':'native-two-stage-diagnostic-v1','initial':{k:first[k] for k in ('planned_attempts','finished_attempts','submitted_attempts','complete')},
         'recovery':{k:second[k] for k in ('planned_attempts','started_attempts','finished_attempts','submitted_attempts','complete','execution_finished')},
         'total_finished_attempts':first['finished_attempts']+second['finished_attempts'],
         'total_submitted_attempts':first['submitted_attempts']+second['submitted_attempts'],
         'cost':costs,'by_model':rows,
         'interpretation':'Original 20 attempts are preserved. The recovery phase restarts only infrastructure-failed slots, once each, sequentially with a different HTTP client. These post-hoc selected results are not a clean five-model benchmark or a causal transport comparison. Costs include both phases; no human acceptance is inferred.'}
 result['recovery']['unattempted_count']=second['planned_attempts']-second['started_attempts']
 result['recovery']['account_or_rate_stop']=second['execution_finished'] and result['recovery']['unattempted_count']>0
 (OUT/'combined_study.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'finished_attempts':result['total_finished_attempts'],'submitted':result['total_submitted_attempts'],'cost':costs}))
 return result

if __name__=='__main__':main()
