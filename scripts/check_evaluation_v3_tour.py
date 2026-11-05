"""Read-only independent arithmetic using source line items, not solver formulas."""
import json
import hashlib
from pathlib import Path
from decimal import Decimal
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parents[1]
TID='7b08cd4d-df60-41ae-9102-8aaa49306ba2'
PACKET=ROOT/'output/evaluation_v3/judge-packets'/TID

def D(x):return Decimal(str(x))

def main():
    source=PACKET/'sources/S1.xlsx';output=PACKET/'artifacts/A1.xlsx'
    sw=load_workbook(source,data_only=True);ow=load_workbook(output,data_only=True)
    tm=sw['Inc & Costs Tracked by Tour Mgr'];pc=sw['Costs Tracked by Productn Co']
    rates={'UK':D('.20'),'France':D('.15'),'Spain':D('.24'),'Germany':D('.15825')}
    rows=[]
    def check(sheet,cell,expected,inputs):
        got=ow[sheet][cell].value
        difference=abs(D(got)-expected) if isinstance(got,(float,int)) else None
        rows.append({'sheet':sheet,'cell':cell,'expected':str(expected),'observed':got,'within_one_cent':difference is not None and difference<=D('.01'),'source_inputs':inputs})
    gross=tax=Decimal(0)
    for sr in range(9,16):
        outrow=sr-5;g=D(tm[f'E{sr}'].value);rate=rates[tm[f'D{sr}'].value];t=g*rate
        gross+=g;tax+=t
        for col,want in [('D',g),('E',rate),('F',t),('G',g-t)]:
            check('Revenue',f'{col}{outrow}',want,f'Tour Manager E{sr}, country D{sr}; prompt country rate')
    for col,want in [('D',gross),('F',tax),('G',gross-tax)]:check('Revenue',f'{col}11',want,'Seven source tour stops, prompt tax rates')
    tm_cats=[sum(D(tm[f'E{r}'].value) for r in (29,30)),gross*D('.11')+sum(D(tm[f'E{r}'].value) for r in (44,47)),sum(D(tm[f'E{r}'].value) for r in range(34,40)),sum(D(tm[f'E{r}'].value) for r in (45,46))]
    pc_cats=[D(pc['C8'].value),sum(D(pc[f'C{r}'].value) for r in (20,22)),sum(D(pc[f'C{r}'].value) for r in range(11,17)),D(pc['C21'].value)]
    for i,(t,p) in enumerate(zip(tm_cats,pc_cats),17):
        for c,want in [('B',t),('C',p),('D',t+p)]:check('P&L',f'{c}{i}',want,'Independent source detail category sums; agency commission = gross x 11%')
    totals={5:[gross,D(0),gross],6:[tax,D(0),tax],7:[gross-tax,D(0),gross-tax],21:[sum(tm_cats),sum(pc_cats),sum(tm_cats)+sum(pc_cats)],22:[gross-tax-sum(tm_cats),-sum(pc_cats),gross-tax-sum(tm_cats)-sum(pc_cats)]}
    for r,values in totals.items():
        for c,want in zip('BCD',values):check('P&L',f'{c}{r}',want,'Recomputed source detail revenue less source costs, preserving source separation')
    result={'task_id':TID,'kind':'independent_assistant_arithmetic_check','numeric_comparisons':len(rows),'mismatches':[x for x in rows if not x['within_one_cent']],'tolerance':'USD .01; rates also checked separately for exact equality','rate_exact_matches':all(D(ow['Revenue'][f'E{r-5}'].value)==rates[tm[f'D{r}'].value] for r in range(9,16)),'net_income_full_precision':str(totals[22][2]),'scope':'Checks current numeric outputs against primitive source values and prompt rates. No human acceptance or live update behavior claim.','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'comparisons':rows}
    dest=ROOT/'output/evaluation_v3/independent-checks/tour.json';dest.parent.mkdir(exist_ok=True);dest.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('numeric_comparisons','mismatches','rate_exact_matches','net_income_full_precision')}))

if __name__=='__main__':main()
