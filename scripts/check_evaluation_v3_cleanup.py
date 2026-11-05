"""Independent source-PDF to submitted-workbook fidelity check, read-only."""
import json
import re
import hashlib
from pathlib import Path
from datetime import date
from pypdf import PdfReader
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parents[1]
TID='17111c03-aac7-45c2-857d-c06d8223d6ad'
PACKET=ROOT/'output/evaluation_v3/judge-packets'/TID

def main():
    source=PACKET/'sources/S1.pdf';output=PACKET/'artifacts/A2.xlsx'
    months={'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}
    expected=[]
    for page_number,page in enumerate(PdfReader(source).pages,1):
        for line in page.extract_text(extraction_mode='layout').splitlines():
            if 'Section' not in line:continue
            match=re.search(r'([A-Za-z]+)\s+(\d+)\s*[–-]\s*([A-Za-z]+)\s+(\d+),\s*(\d{4})\s+Section\s+(\d)',line)
            if not match:raise ValueError('Unparsed schedule row: '+line)
            m1,d1,m2,d2,year,section=match.groups();m1=months[m1.lower()[:3]];m2=months[m2.lower()[:3]];year=int(year)
            start=date(year-int(m1>m2),m1,int(d1));end=date(year,m2,int(d2))
            expected.append({'page':page_number,'source_line':line.strip(),'start':start.isoformat(),'end':end.isoformat(),'section':'Section '+section})
    wb=load_workbook(output,data_only=True);sheet=wb['Cleanup schedule'];actual=[]
    for row in sheet.iter_rows(min_row=2):
        if row[0].value is not None:
            actual.append({'row':row[0].row,'start':row[0].value.date().isoformat(),'end':row[1].value.date().isoformat(),'section':row[2].value})
    mismatches=[]
    for i,(want,got) in enumerate(zip(expected,actual)):
        for field in ('start','end','section'):
            if want[field]!=got[field]:mismatches.append({'index':i,'field':field,'expected':want[field],'observed':got[field]})
    if len(expected)!=len(actual):mismatches.append({'row_count_expected':len(expected),'row_count_observed':len(actual)})
    result={'task_id':TID,'kind':'independent_assistant_source_fidelity_check','source_rows':len(expected),'output_rows':len(actual),'fields_checked':3*min(len(expected),len(actual)),'mismatches':mismatches,'scope':'Start date, end date, section in source order. Does not certify memo usability or human acceptance.','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'comparisons':[{'expected':w,'observed':g} for w,g in zip(expected,actual)]}
    dest=ROOT/'output/evaluation_v3/independent-checks/cleanup.json';dest.parent.mkdir(exist_ok=True);dest.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('source_rows','output_rows','fields_checked','mismatches')}))

if __name__=='__main__':main()
