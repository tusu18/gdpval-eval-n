"""Narrow OOXML adapter for native pivots/print controls absent from bundled docs.

Usage: python evaluation_v4_native_xlsx.py workbook.xlsx spec.json
Edits the builder-owned workbook in place, never source attachments. Artifact-tool
authors the base workbook; this adapter preserves all unrelated ZIP member bytes.
Pivot scope: one or more categorical row fields, one or more numeric value fields with
sum/count/average/min/max, worksheet range source, no column/report-filter axes.
Creates real pivot definition/cache/records/relationships AND cached display cells.
Do not describe this helper as full Excel or arbitrary pivot support.
"""
import argparse
from collections import OrderedDict
import json
from pathlib import Path
import posixpath
import zipfile
from lxml import etree as E
import openpyxl
from openpyxl.utils.cell import range_boundaries, coordinate_from_string, column_index_from_string, get_column_letter

M='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P='http://schemas.openxmlformats.org/package/2006/relationships'
C='http://schemas.openxmlformats.org/package/2006/content-types'
def node(tag,attrs=None,parent=None,ns=M):
    el=E.Element('{'+ns+'}'+tag,{k:str(v) for k,v in (attrs or {}).items()})
    if parent is not None:parent.append(el)
    return el
def xml(el):return E.tostring(el,xml_declaration=True,encoding='UTF-8',standalone=True)
def target(part,value):return value.lstrip('/') if value.startswith('/') else posixpath.normpath(posixpath.join(posixpath.dirname(part),value))
def relpart(part):return posixpath.join(posixpath.dirname(part),'_rels',posixpath.basename(part)+'.rels')
def unique_id(root):
    taken={e.get('Id') for e in root};i=1
    while f'rIdV4_{i}' in taken:i+=1
    return f'rIdV4_{i}'
def child(root,tag,attrs=None):
    el=root.find('{'+M+'}'+tag)
    if el is None:el=node(tag,attrs,root)
    elif attrs:el.attrib.update({k:str(v) for k,v in attrs.items()})
    return el
def insert_order(root,el,order):
    rank={name:i for i,name in enumerate(order)};key=E.QName(el).localname
    if el.getparent() is root:root.remove(el)
    for i,x in enumerate(root):
        if rank.get(E.QName(x).localname,999)>rank.get(key,999):root.insert(i,el);return
    root.append(el)
SHEET_ORDER=['sheetPr','dimension','sheetViews','sheetFormatPr','cols','sheetData','sheetCalcPr','sheetProtection','protectedRanges','scenarios','autoFilter','sortState','dataConsolidate','customSheetViews','mergeCells','phoneticPr','conditionalFormatting','dataValidations','hyperlinks','printOptions','pageMargins','pageSetup','headerFooter','rowBreaks','colBreaks','customProperties','cellWatches','ignoredErrors','smartTags','drawing','legacyDrawing','legacyDrawingHF','picture','oleObjects','controls','webPublishItems','tableParts','pivotTableParts','extLst']
WORKBOOK_ORDER=['fileVersion','fileSharing','workbookPr','workbookProtection','bookViews','sheets','functionGroups','externalReferences','definedNames','calcPr','oleSize','customWorkbookViews','pivotCaches','smartTagPr','smartTagTypes','webPublishing','fileRecoveryPr','webPublishObjects','extLst']

def apply(path,spec):
    path=Path(path)
    with zipfile.ZipFile(path) as z:members={n:z.read(n) for n in z.namelist()};infos=z.infolist();comment=z.comment
    workbook=E.fromstring(members['xl/workbook.xml']);wrels=E.fromstring(members['xl/_rels/workbook.xml.rels']);types=E.fromstring(members['[Content_Types].xml'])
    wr={e.get('Id'):target('xl/workbook.xml',e.get('Target')) for e in wrels}
    sheets={s.get('name'):(i,wr[s.get('{'+R+'}id')]) for i,s in enumerate(workbook.find('{'+M+'}sheets'))}
    changed={}
    def sheet_xml(name):
        part=sheets[name][1]
        if part not in changed:changed[part]=E.fromstring(members[part])
        return changed[part]
    def relationships(part):
        rp=relpart(part)
        if rp not in changed:changed[rp]=E.fromstring(members[rp]) if rp in members else E.Element('{'+P+'}Relationships',nsmap={None:P})
        return changed[rp]
    def addtype(part,mime):
        if not any(e.get('PartName')=='/'+part for e in types):node('Override',{'PartName':'/'+part,'ContentType':mime},types,C)
    wb_read=openpyxl.load_workbook(path,data_only=True,read_only=True)
    pivots=[]
    for p in spec.get('pivots',[]):
        if any(k in p for k in ('column_fields','page_fields')):raise ValueError('Adapter supports tabular row fields, no column/report-filter axes.')
        source_sheet=p['source_sheet'];dest_sheet=p['target_sheet'];ref=p['source_range'];row_fields=p.get('row_fields') or [p['row_field']];values=p['values']
        if not isinstance(row_fields,list) or not row_fields or len(set(row_fields))!=len(row_fields):raise ValueError('row_fields must be a nonempty distinct list.')
        c1,r1,c2,r2=range_boundaries(ref)
        rows=list(wb_read[source_sheet].iter_rows(min_row=r1,max_row=r2,min_col=c1,max_col=c2,values_only=True))
        headers=list(rows[0]);data=[list(r) for r in rows[1:] if any(v is not None for v in r)]
        if len(set(headers))!=len(headers) or any(not isinstance(h,str) for h in headers):raise ValueError('Pivot source needs distinct nonempty text column headers.')
        ris=[headers.index(field) for field in row_fields]
        vis=[headers.index(v['field']) for v in values]
        if set(ris)&set(vis):raise ValueError('Row field cannot also be a value field in this adapter.')
        for v in values:
            if v.get('aggregate','sum') not in ('sum','count','average','min','max'):raise ValueError('Unsupported pivot aggregation.')
        shared=[];indices=[]
        for i in range(len(headers)):
            items=[];index={}
            for row in data:
                val=row[i];key=(type(val).__name__,str(val))
                if key not in index:index[key]=len(items);items.append(val)
            shared.append(items);indices.append(index)
        groups=OrderedDict()
        for row in data:groups.setdefault(tuple(row[ri] for ri in ris),[]).append(row)
        def aggregate(rows,v,idx):
            vals=[row[idx] for row in rows if isinstance(row[idx],(int,float)) and not isinstance(row[idx],bool)]
            if v.get('aggregate','sum')=='count':return sum(row[idx] is not None for row in rows)
            if not vals:return 0
            return {'sum':lambda:sum(vals),'average':lambda:sum(vals)/len(vals),'min':lambda:min(vals),'max':lambda:max(vals)}[v.get('aggregate','sum')]()
        labels=[v.get('caption',v.get('aggregate','sum').title()+' of '+v['field']) for v in values]
        display=[[ *row_fields,*labels]]+[[*key,*[aggregate(rs,v,i) for v,i in zip(values,vis)]] for key,rs in groups.items()]+[['Grand Total',*['']*(len(ris)-1),*[aggregate(data,v,i) for v,i in zip(values,vis)]]]
        anchor_col,anchor_row=coordinate_from_string(p.get('target_cell','A1'));ac=column_index_from_string(anchor_col);ar=anchor_row
        end=f'{get_column_letter(ac+len(values)+len(ris)-1)}{ar+len(display)-1}';outref=f'{anchor_col}{ar}:{end}'
        dest=sheet_xml(dest_sheet);sd=child(dest,'sheetData')
        for dr,vals in enumerate(display):
            rn=ar+dr;row=next((x for x in sd if int(x.get('r'))==rn),None)
            if row is None:row=node('row',{'r':rn},sd)
            for dc,value in enumerate(vals):
                address=f'{get_column_letter(ac+dc)}{rn}';existing=next((x for x in row if x.get('r')==address),None)
                if existing is not None:
                    if not p.get('overwrite_target',False):raise ValueError('Pivot target contains existing cells; explicit overwrite_target required.')
                    row.remove(existing)
                cell=node('c',{'r':address},row)
                if isinstance(value,(int,float)):node('v',parent=cell).text=str(value)
                else:cell.set('t','inlineStr');node('t',parent=node('is',parent=cell)).text='' if value is None else str(value)
            row[:]=sorted(row,key=lambda x:column_index_from_string(coordinate_from_string(x.get('r'))[0]))
        sd[:]=sorted(sd,key=lambda x:int(x.get('r')))
        dimension=dest.find('{'+M+'}dimension')
        old=range_boundaries(dimension.get('ref')) if dimension is not None else (ac,ar,ac,ar)
        child(dest,'dimension',{'ref':f'{get_column_letter(min(old[0],ac))}{min(old[1],ar)}:{get_column_letter(max(old[2],ac+len(values)+len(ris)-1))}{max(old[3],ar+len(display)-1)}'})
        for el in list(dest):insert_order(dest,el,SHEET_ORDER)
        number=1
        while f'xl/pivotTables/pivotTable{number}.xml' in members or f'xl/pivotTables/pivotTable{number}.xml' in changed:number+=1
        cache_id=max([int(x.get('cacheId')) for x in workbook.findall('{'+M+'}pivotCaches/{'+M+'}pivotCache')]+[-1])+1
        cachepart=f'xl/pivotCache/pivotCacheDefinition{number}.xml';recordpart=f'xl/pivotCache/pivotCacheRecords{number}.xml';pivotpart=f'xl/pivotTables/pivotTable{number}.xml'
        cache=E.Element('{'+M+'}pivotCacheDefinition',nsmap={None:M,'r':R},attrib={'{'+R+'}id':'rIdRecords','refreshOnLoad':'1','recordCount':str(len(data)),'createdVersion':'3','refreshedVersion':'3','minRefreshableVersion':'3'})
        node('worksheetSource',{'ref':ref,'sheet':source_sheet},node('cacheSource',{'type':'worksheet'},cache))
        fields=node('cacheFields',{'count':len(headers)},cache)
        for i,h in enumerate(headers):
            f=node('cacheField',{'name':h,'numFmtId':0},fields)
            nonempty=[v for v in shared[i] if v is not None]
            numeric=bool(nonempty) and all(isinstance(v,(int,float)) and not isinstance(v,bool) for v in nonempty)
            si=node('sharedItems',{'count':len(shared[i]),'containsString':'0' if numeric else '1','containsNumber':'1' if numeric else '0','containsBlank':'1' if None in shared[i] else '0','containsSemiMixedTypes':'0' if numeric else '1'},f)
            for value in shared[i]:
                if value is None:node('m',parent=si)
                elif isinstance(value,bool):node('b',{'v':int(value)},si)
                elif isinstance(value,(int,float)):node('n',{'v':value},si)
                else:node('s',{'v':str(value)},si)
        records=E.Element('{'+M+'}pivotCacheRecords',nsmap={None:M},attrib={'count':str(len(data))})
        for row in data:
            rec=node('r',parent=records)
            for i,value in enumerate(row):node('x',{'v':indices[i][(type(value).__name__,str(value))]},rec)
        pivot=E.Element('{'+M+'}pivotTableDefinition',nsmap={None:M},attrib={'name':p.get('name',f'Pivot{number}'),'cacheId':str(cache_id),'dataCaption':'Values','rowGrandTotals':'1','colGrandTotals':'0','compact':'0','compactData':'0','outline':'0','outlineData':'0','gridDropZones':'1','multipleFieldFilters':'0','useAutoFormatting':'1'})
        node('location',{'ref':outref,'firstHeaderRow':1,'firstDataRow':1,'firstDataCol':len(ris)},pivot)
        pfields=node('pivotFields',{'count':len(headers)},pivot)
        for i,h in enumerate(headers):
            attrs={'showAll':'0'}
            if i in ris:attrs.update(axis='axisRow',defaultSubtotal='0',compact='0',outline='0')
            if i in vis:attrs['dataField']='1'
            f=node('pivotField',attrs,pfields)
            if i in ris:
                items=node('items',{'count':len(shared[i])+1},f)
                for idx in range(len(shared[i])):node('item',{'x':idx},items)
                node('item',{'t':'default'},items)
        rfs=node('rowFields',{'count':len(ris)},pivot)
        for ri in ris:node('field',{'x':ri},rfs)
        rowitems=node('rowItems',{'count':len(groups)+1},pivot)
        for key in groups:
            item=node('i',{'r':0},rowitems)
            for ri,value in zip(ris,key):node('x',{'v':indices[ri][(type(value).__name__,str(value))]},item)
        grand=node('i',{'t':'grand','r':0},rowitems)
        for ri in ris:node('x',parent=grand)
        if len(values)>1:
            node('field',{'x':-2},node('colFields',{'count':1},pivot))
            cis=node('colItems',{'count':len(values)},pivot)
            for i in range(len(values)):node('x',{'v':i},node('i',{'i':i},cis))
        df=node('dataFields',{'count':len(values)},pivot)
        for v,i,label in zip(values,vis,labels):node('dataField',{'name':label,'fld':i,'subtotal':v.get('aggregate','sum'),'baseField':0,'baseItem':0},df)
        node('pivotTableStyleInfo',{'name':'PivotStyleMedium9','showRowHeaders':'1','showColHeaders':'1','showRowStripes':'0','showColStripes':'0','showLastColumn':'1'},pivot)
        wc=child(workbook,'pivotCaches');rid=unique_id(wrels)
        node('pivotCache',{'cacheId':cache_id,'{'+R+'}id':rid},wc)
        node('Relationship',{'Id':rid,'Type':R+'/pivotCacheDefinition','Target':cachepart[3:]},wrels,P)
        cp_rels=E.Element('{'+P+'}Relationships',nsmap={None:P});node('Relationship',{'Id':'rIdRecords','Type':R+'/pivotCacheRecords','Target':posixpath.basename(recordpart)},cp_rels,P)
        pt_rels=E.Element('{'+P+'}Relationships',nsmap={None:P});node('Relationship',{'Id':'rIdCache','Type':R+'/pivotCacheDefinition','Target':'../pivotCache/'+posixpath.basename(cachepart)},pt_rels,P)
        destpart=sheets[dest_sheet][1];srels=relationships(destpart);rid=unique_id(srels)
        node('Relationship',{'Id':rid,'Type':R+'/pivotTable','Target':'../pivotTables/'+posixpath.basename(pivotpart)},srels,P)
        parts=child(dest,'pivotTableParts');node('pivotTablePart',{'{'+R+'}id':rid},parts);parts.set('count',str(len(parts)))
        changed.update({cachepart:cache,recordpart:records,pivotpart:pivot,relpart(cachepart):cp_rels,relpart(pivotpart):pt_rels})
        for part,kind in [(cachepart,'pivotCacheDefinition'),(recordpart,'pivotCacheRecords'),(pivotpart,'pivotTable')]:addtype(part,'application/vnd.openxmlformats-officedocument.spreadsheetml.'+kind+'+xml')
        pivots.append({'name':pivot.get('name'),'target':dest_sheet+'!'+outref,'source':source_sheet+'!'+ref,'records':len(data),'cached_display_rows':len(display)})
    wb_read.close()
    for p in spec.get('print',[]):
        name=p['sheet'];root=sheet_xml(name)
        attrs={'orientation':p.get('orientation','landscape'),'paperSize':p.get('paper_size',9),'fitToWidth':p.get('fit_to_width',1),'fitToHeight':p.get('fit_to_height',0)}
        child(root,'pageSetup',attrs)
        child(child(root,'sheetPr'),'pageSetUpPr',{'fitToPage':'1'})
        child(root,'pageMargins',{'left':0.25,'right':0.25,'top':0.5,'bottom':0.5,'header':0.2,'footer':0.2})
        child(root,'printOptions',{'horizontalCentered':'1','gridLines':'0','headings':'0'})
        if p.get('area'):
            dns=child(workbook,'definedNames')
            for d in list(dns):
                if d.get('name')=='_xlnm.Print_Area' and d.get('localSheetId')==str(sheets[name][0]):dns.remove(d)
            escaped=name.replace("'","''")
            node('definedName',{'name':'_xlnm.Print_Area','localSheetId':sheets[name][0]},dns).text=f"'{escaped}'!{p['area']}"
        for el in list(root):insert_order(root,el,SHEET_ORDER)
    for el in list(workbook):insert_order(workbook,el,WORKBOOK_ORDER)
    changed.update({'xl/workbook.xml':workbook,'xl/_rels/workbook.xml.rels':wrels,'[Content_Types].xml':types})
    payload={name:xml(value) for name,value in changed.items()}
    tmp=path.with_suffix('.v4-tmp.xlsx')
    with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
        z.comment=comment
        for info in infos:z.writestr(info,payload.pop(info.filename,members[info.filename]))
        for name,data in payload.items():z.writestr(name,data)
    tmp.replace(path)
    return {'adapter':'v4-narrow-ooxml-pivot-print','pivots':pivots,'print_sheets':[p['sheet'] for p in spec.get('print',[])],'unrelated_zip_members_preserved':True}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('workbook',type=Path);p.add_argument('spec',type=Path);a=p.parse_args()
    print(json.dumps(apply(a.workbook,json.loads(a.spec.read_text()))))
