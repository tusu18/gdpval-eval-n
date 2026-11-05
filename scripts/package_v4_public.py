"""Allowlisted public code/report bundle; never includes original source documents."""
import hashlib,json,re,zipfile,shutil
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit,unquote
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'sites/v4-submission/dist'
selected=['evaluation_v4_workspace.py','evaluation_v4_native_xlsx.py','validate_evaluation_v4_assessments.py','freeze_evaluation_v4.py','build_evaluation_v4_report.py','analyze_evaluation_v4.py','prepare_evaluation_v4_selection.py','prepare_evaluation_v4_execution.py','build_v4_delivery.py']
files={}
for n in selected:
 s=(ROOT/'scripts'/n).read_text().replace(str(ROOT),'/path/to/project').replace('/Users/tusu18','/path/to/user')
 files['implementation/'+n]=s.encode()
for name in ['index.html','evidence.html','pitches.html','style.css','evidence-snapshot.json']:files['report/'+name]=(D/name).read_bytes()
for n in list(files):
 if n.endswith('.html'):
  files[n]=files[n].replace(b'href="submission-code.zip" download>Report + code ZIP',b'href="../README.txt">Bundle contents').replace(b'href="submission-code.zip"',b'href="../README.txt"')
files['README.txt']=b'''V4 public submission: sanitized report and selected implementation\n\nOpen report/index.html. Run python3 reproduce_summary.py to verify aggregate counts, cost arithmetic and the reported tax difference from the sanitized snapshot. This does not rerun inference or independently verify raw evidence.\n\nimplementation/ contains selected actual harness, analysis, validation and report-generation sources for inspection. They require omitted project modules, original inputs and bundled native-document libraries to execute; this is not a standalone inference environment. Sources use placeholder personal paths where necessary. Exact hosting access metadata and credentials are excluded.\n\nRaw prompts/reference files, native submissions, full traces, private review records, account IDs and runtime secrets are intentionally excluded from this public bundle. The full local evidence archive remains separate. The public task IDs and aggregate findings enable matching a reviewed result to that archive. No external raw-evidence link is implied.\n\nAll empirical findings are descriptive and scoped. Four assisted non-specialist reviews do not establish expert acceptance or judge accuracy. V5 is separate future validation work.\n'''
files['reproduce_summary.py']=b'''import json\nfrom pathlib import Path\nd=json.loads((Path(__file__).parent/'report/evidence-snapshot.json').read_text())\nc=d['counts'];co=d['cohorts']\nassert sum(x['selected_tasks'] for x in co.values())==c['selected_tasks']==40\nassert sum(x['submitted_tasks'] for x in co.values())==c['submitted_tasks']==40\nassert sum(x['tasks_with_contract_valid_assessment'] for x in co.values())==33\nassert sum(x['human_reviewed_tasks'] for x in co.values())==4\nassert sum(d['v4_provisional_outcomes'].values())==20\nassert sum(d['review_minutes'])==28\nt=d['evidence'][0];assert t['regular_tax_corrected']-t['regular_tax_saved']==t['difference']==2046\ncost=d['cost'];assert abs(cost['committed_usd']-cost['known_provider_cost_usd']-cost['unresolved_charge_reserve_usd'])<1e-7\nprint('8 aggregate consistency checks passed; not a raw-data or model rerun.')\n'''
secret=re.compile(rb'(?:sk-or-v1-[a-zA-Z0-9]{20,}|art_v2_[a-zA-Z0-9_]{15,}|/Users/tusu18|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}|\b\d{3}-\d{2}-\d{4}\b)',re.I)
for n,b in files.items():
 if secret.search(b):raise RuntimeError('Public screening hit: '+n)
manifest={'scope':'allowlisted sanitized report and selected code','files':{n:hashlib.sha256(b).hexdigest() for n,b in files.items()}}
files['MANIFEST.json']=(json.dumps(manifest,indent=2)+'\n').encode()
with zipfile.ZipFile(D/'submission-code.zip','w',zipfile.ZIP_DEFLATED) as z:
 for n,b in sorted(files.items()):z.writestr(n,b)
with zipfile.ZipFile(D/'submission-code.zip') as z:assert z.testzip() is None
class Links(HTMLParser):
 def __init__(self):super().__init__();self.links=[]
 def handle_starttag(self,t,a):self.links += [v for k,v in a if k in ['href','src'] and v]
count=0
for p in D.glob('*.html'):
 parser=Links();parser.feed(p.read_text())
 for link in parser.links:
  u=urlsplit(link)
  if u.scheme or not u.path:continue
  assert (p.parent/unquote(u.path)).is_file(),link
  count+=1
# Local raw archive receives the exact same concise front end, without publishing the raw archive.
delivery=ROOT/'output/evaluation_v4/delivery';delivery.mkdir(exist_ok=True)
for p in D.iterdir():
 if p.is_file():shutil.copy2(p,delivery/p.name)
result={'local_links_checked':count,'public_zip_entries':len(files),'public_zip_sha256':hashlib.sha256((D/'submission-code.zip').read_bytes()).hexdigest(),'public_zip_bytes':(D/'submission-code.zip').stat().st_size,'credential_personal_path_email_ssn_pattern_screen':'passed','raw_sources_uploaded':False}
(ROOT/'output/evaluation_v4/delivery-verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
