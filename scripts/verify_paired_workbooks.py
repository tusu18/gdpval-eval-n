"""Check exported cached worksheet values independently of model audit answers."""
import json,math,re
from pathlib import Path
import openpyxl
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'output/paired_v1'
TRUTH={'A-1001':[2.5,'ups',5.95,7.95,2],'B-5005':[250,'freight',150,225,75],'C-2001':[50,'fedex',75,79.99,4.99]}
def normal(x):return re.sub(r'[^a-z0-9]','',str(x).lower())
def check(p):
 w=openpyxl.load_workbook(p,data_only=True);found={};errors=[]
 for s in w:
  sheet_rows=list(s.values)
  # A supporting pick-ticket sheet can repeat IDs in a different column layout.
  # Only the actual manifest header establishes the nine-column interpretation.
  if not any(len(row)>=9 and normal(row[3])=='shippingmethod' and 'saving' in normal(row[8]) for row in sheet_rows):continue
  for row in sheet_rows:
   if not row or row[0] not in TRUTH:continue
   if len(row)<9:errors.append('Incomplete nine-column manifest row');continue
   expected=TRUTH[row[0]];values=[row[2],normal(row[3]),row[6],row[7],row[8]]
   ok=all(a==e if isinstance(e,str) else isinstance(a,(int,float)) and math.isfinite(a) and abs(a-e)<0.011 for a,e in zip(values,expected))
   found[row[0]]={'sheet':s.title,'values':values,'expected':expected,'correct':ok}
   if row[4] not in [None,'','Not provided','Not supplied','TBD','Pending','Not available']:errors.append('Review tracking field: '+str(row[4]))
 return {'run_id':p.parent.name,'file':p.name,'rows':found,'errors':errors,'pass':len(found)==3 and all(x['correct'] for x in found.values()) and not errors}
if __name__=='__main__':
 rows=[check(p) for p in (BASE/'artifacts').rglob('*.xlsx')]
 (BASE/'artifact_qa/workbook_checks.json').write_text(json.dumps(rows,indent=2))
 print(json.dumps({'checked':len(rows),'passed':sum(r['pass'] for r in rows),'failures':[r for r in rows if not r['pass']]}))
