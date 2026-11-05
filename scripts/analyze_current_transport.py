"""Describe logged transport evidence without attributing failures to model quality."""
import json
from collections import Counter
from pathlib import Path
from run_completion_and_pairs import write,utc

ROOT=Path(__file__).resolve().parents[1]

def category(event):
    if event['status']=='received':return 'received'
    error=(event.get('error') or '').lower()
    if 'bad_record_mac' in error or 'bad record mac' in error:return 'tls_bad_record_mac'
    for code in ('401','402','403','429'):
        if 'openrouter http '+code in error:return 'http_'+code
    if any(x in error for x in ('epipe','econnreset','socket','upload connection closed')):return 'socket_or_upload_error'
    return 'other_transport_error'

def build():
    stages={}
    for stage in ('paired_native_08','native_completion_07','native_backoff_probe_09'):
        path=ROOT/'output'/stage/'transport_events.jsonl'
        events=[json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        received=[e for e in events if e['status']=='received']
        failed=[e for e in events if e['status']=='failed']
        stages[stage]={'logged_network_attempts':len(events),'status_counts':dict(Counter(category(e) for e in events)),
            'received_body_bytes_range':[min(e['body_bytes'] for e in received),max(e['body_bytes'] for e in received)] if received else None,
            'received_bodies_over_one_megabyte':sum(e['body_bytes']>1000000 for e in received),
            'failed_events':[{'log_line':i+1,'category':category(e),'body_bytes':e['body_bytes'],'will_retry':e['will_retry']} for i,e in enumerate(events) if e['status']=='failed'],
            'extra_unresolved_retry_charges':sum(e['extra_unresolved_charge_record'] for e in events)}
    result={'updated_at':utc(),'scope':'Read-only diagnostic of the frozen transport event logs; no additional API calls.',
        'stages':stages,'interpretation':'TLS failures occurred at different request sizes, while large requests also succeeded. These observations do not establish payload size as the cause. No certificate verification was disabled and no failed attempt was reclassified as business error.',
        'limitations':'Network attempts are dependent within task runs. Body sizes do not identify image contents. No randomized transport comparison or root-cause proof is claimed.'}
    write(ROOT/'output/current_study_06/transport_diagnostics.json',result)
    return result

if __name__=='__main__':build()
