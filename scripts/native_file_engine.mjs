// Native artifact engine. Only the model-supplied content is written; no grader data.
import fs from 'node:fs/promises';
import path from 'node:path';
import {Document,Packer,Paragraph,TextRun,Table,TableRow,TableCell,WidthType,HeadingLevel,BorderStyle} from 'docx';
import {Workbook,SpreadsheetFile,FileBlob} from '@oai/artifact-tool';
const [jobPath]=process.argv.slice(2);
const job=JSON.parse(await fs.readFile(jobPath,'utf8'));
const out=job.output; await fs.mkdir(path.dirname(out),{recursive:true});
const border={style:BorderStyle.SINGLE,size:4,color:'D9D9D9'};
const result={filename:path.basename(out),previews:[]};
function para(text,heading){return new Paragraph({children:[new TextRun(String(text))],...(heading?{heading}:{})});}
if(job.kind==='docx'){
 const a=job.content;
 const children=[para(a.title||'',HeadingLevel.TITLE)];
 for(const section of a.sections){
  if(section.heading)children.push(para(section.heading,HeadingLevel.HEADING_1));
  for(const text of section.paragraphs||[])children.push(para(text));
  if(section.table){
   const rows=[section.table.headers,...section.table.rows];const n=rows[0].length;
   const widths=section.table.widths||Array(n).fill(100/n);
   children.push(new Table({width:{size:100,type:WidthType.PERCENTAGE},rows:rows.map((row,i)=>new TableRow({tableHeader:i===0,children:row.map((value,j)=>new TableCell({width:{size:widths[j],type:WidthType.PERCENTAGE},borders:{top:border,bottom:border,left:border,right:border},margins:{top:90,bottom:90,left:100,right:100},shading:{fill:i===0?'DCE6EF':i%2===0?'F5F7F9':'FFFFFF'},children:[new Paragraph({children:[new TextRun({text:String(value??''),bold:i===0})]})]}))}))}));
   children.push(new Paragraph({text:'',spacing:{after:80}}));
  }
 }
 const font=a.font_size||11;
 const doc=new Document({creator:'Evaluation participant',title:a.title||'',styles:{default:{document:{run:{font:'Calibri',size:font*2,color:'000000'},paragraph:{spacing:{after:100,line:276}}}},paragraphStyles:[
  {id:'Title',name:'Title',basedOn:'Normal',next:'Normal',run:{font:'Calibri',size:32,bold:true,color:'000000'},paragraph:{spacing:{after:160}}},
  {id:'Heading1',name:'heading 1',basedOn:'Normal',next:'Normal',run:{font:'Calibri',size:24,bold:true,color:'000000'},paragraph:{keepNext:true,spacing:{before:120,after:80}}}
 ]},sections:[{properties:{page:{size:{width:12240,height:15840},margin:{top:1440,right:1440,bottom:1440,left:1440}}},children}]});
 await fs.writeFile(out,await Packer.toBuffer(doc));
}else if(job.kind==='xlsx'){
 const wb=Workbook.create();const sheets=job.content.sheets;
 for(const s of sheets)wb.worksheets.add(s.name);
 for(const s of sheets){
  const sh=wb.worksheets.getItem(s.name);const nr=s.rows.length,nc=Math.max(...s.rows.map(r=>r.length));
  sh.getRangeByIndexes(0,0,nr,nc).values=s.rows.map(r=>Array.from({length:nc},(_,j)=>typeof r[j]==='string'&&r[j].startsWith('=')?null:r[j]??null));
  for(let i=0;i<nr;i++)for(let j=0;j<nc;j++)if(typeof s.rows[i][j]==='string'&&s.rows[i][j].startsWith('='))sh.getCell(i,j).formulas=[[s.rows[i][j]]];
  const used=sh.getRangeByIndexes(0,0,nr,nc); used.format.font={name:'Arial',size:11};used.format.wrapText=true;used.format.verticalAlignment='center';
  for(let j=0;j<nc;j++)sh.getRangeByIndexes(0,j,nr,1).format.columnWidth=s.column_widths?.[j]||22;
  for(const fmt of s.number_formats||[])sh.getRange(fmt.range).setNumberFormat(fmt.format);
  if(s.header_row!==null){const h=s.header_row??0;sh.getRangeByIndexes(h,0,1,nc).format={fill:'#17324D',font:{bold:true,color:'#FFFFFF'},wrapText:true};}
  used.format.autofitRows();sh.showGridLines=false;
 }
 wb.recalculate();
 result.recalculation_engine='artifact-tool';result.inspection=[];
 for(const s of sheets){
  const sh=wb.worksheets.getItem(s.name);const nr=s.rows.length,nc=Math.max(...s.rows.map(r=>r.length));
  result.inspection.push({sheet:s.name,values:sh.getRangeByIndexes(0,0,nr,nc).values,formulas:sh.getRangeByIndexes(0,0,nr,nc).formulas});
 }
 await (await SpreadsheetFile.exportXlsx(wb)).save(out);
 // Reopen the exported native file and calculate it again before feedback.
 const reopened=await SpreadsheetFile.importXlsx(await FileBlob.load(out));reopened.recalculate();
 result.reopened_inspection=[];
 for(const s of sheets){
  const nr=s.rows.length,nc=Math.max(...s.rows.map(r=>r.length));const sh=reopened.worksheets.getItem(s.name);
  result.reopened_inspection.push({sheet:s.name,values:sh.getRangeByIndexes(0,0,nr,nc).values});
  for(let start=0;start<nr;start+=30){
   const end=Math.min(start+30,nr);const last=String.fromCharCode(64+nc);
   const preview=await reopened.render({sheetName:s.name,range:`A${start+1}:${last}${end}`,scale:1,format:'png'});
   const dest=path.join(path.dirname(out),`preview-${result.previews.length+1}.png`);
   await fs.writeFile(dest,new Uint8Array(await preview.arrayBuffer()));result.previews.push({path:dest,sheet:s.name,range:`A${start+1}:${last}${end}`});
  }
 }
 result.formula_scan=(await reopened.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:100}})).ndjson;
}else throw Error('Unsupported native artifact type');
await fs.writeFile(job.result,JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({created:result.filename,previews:result.previews.length}));
