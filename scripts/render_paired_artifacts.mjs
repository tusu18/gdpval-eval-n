// Deterministic artifact renderer: preserve every model-authored word/value/formula.
// No business content correction. Invalid or unsupported content is logged.
import fs from 'node:fs/promises';
import path from 'node:path';
import {Document,Packer,Paragraph,TextRun,Table,TableRow,TableCell,WidthType,HeadingLevel,BorderStyle} from 'docx';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const root=path.resolve(path.dirname(new URL(import.meta.url).pathname),'..');
const base=path.join(root,'output/paired_v1');
const out=path.join(base,'artifacts');await fs.mkdir(out,{recursive:true});
const qa=path.join(base,'artifact_qa');await fs.mkdir(qa,{recursive:true});
const files=(await fs.readdir(path.join(base,'runs'))).filter(x=>x.endsWith('.json'));
const log=[];
const border={style:BorderStyle.SINGLE,size:4,color:'D9D9D9'};
for(const filename of files){
 const r=JSON.parse(await fs.readFile(path.join(base,'runs',filename),'utf8'));
 if(r.status!=='completed')continue;
 const dir=path.join(out,r.run_id);await fs.mkdir(dir,{recursive:true});
 for(const [idx,a] of (r.final.artifacts||[]).entries()){
  const name=path.basename(a.filename||`artifact-${idx}`);const dest=path.join(dir,name);
  if(await fs.stat(dest).catch(()=>null)){if(!process.argv.includes('--refresh-xlsx')||!name.endsWith('.xlsx')){log.push({run_id:r.run_id,filename:name,status:'existing'});continue;}}
  try{
   if(name.endsWith('.docx')){
    const children=[new Paragraph({text:String(a.title||''),heading:HeadingLevel.TITLE})];
    for(const s of a.sections||[]){
     if(s.heading)children.push(new Paragraph({text:String(s.heading),heading:HeadingLevel.HEADING_1}));
     for(const p of s.paragraphs||[])children.push(new Paragraph({children:[new TextRun(String(p))]}));
     if(s.table){
      const rows=[s.table.headers||[],...(s.table.rows||[])];const n=Math.max(...rows.map(x=>x.length));
      children.push(new Table({width:{size:100,type:WidthType.PERCENTAGE},rows:rows.map((row,i)=>new TableRow({tableHeader:i===0,children:Array.from({length:n},(_,j)=>new TableCell({width:{size:100/n,type:WidthType.PERCENTAGE},borders:{top:border,bottom:border,left:border,right:border},shading:i===0?{fill:'E9EEF3'}:undefined,margins:{top:80,bottom:80,left:90,right:90},children:[new Paragraph({children:[new TextRun({text:String(row[j]??''),bold:i===0})]})]}))}))}));
     }
    }
    const doc=new Document({styles:{default:{document:{run:{font:'Calibri',size:22,color:'000000'},paragraph:{spacing:{after:100,line:276}}}},paragraphStyles:[
     {id:'Title',name:'Title',basedOn:'Normal',next:'Normal',run:{font:'Calibri',size:32,bold:true,color:'000000'},paragraph:{spacing:{after:160}}},
     {id:'Heading1',name:'heading 1',basedOn:'Normal',next:'Normal',run:{font:'Calibri',size:24,bold:true,color:'000000'},paragraph:{keepNext:true,spacing:{before:120,after:80}}}
    ]},sections:[{properties:{page:{size:{width:12240,height:15840},margin:{top:1440,right:1440,bottom:1440,left:1440}}},children}]});
    await fs.writeFile(dest,await Packer.toBuffer(doc));
    log.push({run_id:r.run_id,filename:name,status:'exported',kind:'docx'});
   }else if(name.endsWith('.xlsx')){
    const wb=Workbook.create();const sheets=a.sheets||[];if(!sheets.length)throw Error('No sheets');
    for(const s of sheets)wb.worksheets.add(s.name);
    for(const s of sheets){
     const sh=wb.worksheets.getItem(s.name);const nr=s.rows.length,nc=Math.max(...s.rows.map(x=>x.length));
     if(nr>2500||nc>40)throw Error('Artifact size limit');
     const matrix=s.rows.map(row=>Array.from({length:nc},(_,i)=>{const v=row[i]??null;return typeof v==='string'&&v.startsWith('=')?null:v}));
     const range=sh.getRangeByIndexes(0,0,nr,nc);range.values=matrix;
     for(let i=0;i<nr;i++)for(let j=0;j<nc;j++){const v=s.rows[i][j];if(typeof v==='string'&&v.startsWith('='))sh.getCell(i,j).formulas=[[v]];}
     range.format.font={name:'Arial',size:11};range.format.wrapText=true;range.format.verticalAlignment='center';
     for(let j=0;j<nc;j++)sh.getRangeByIndexes(0,j,nr,1).format.columnWidth=j===5?42:22;
     range.format.autofitRows();sh.showGridLines=false;
     // Only identify an actual multi-column textual header, without moving rows.
     const h=s.rows.findIndex(row=>row.filter(v=>typeof v==='string'&&v.length>0).length>=Math.min(4,nc));
     if(h>=0){
      sh.getRangeByIndexes(h,0,1,nc).format={fill:'#17324D',font:{bold:true,color:'#FFFFFF'},wrapText:true};
      for(let j=0;j<nc;j++)if(/cost|saving/i.test(String(s.rows[h][j]||''))&&nr>h+1)sh.getRangeByIndexes(h+1,j,nr-h-1,1).setNumberFormat('#,##0.00');
     }
    }
    wb.recalculate();
    const check=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',options:{useRegex:true,maxResults:100}});
    await fs.writeFile(path.join(qa,r.run_id+`-${idx}-formula-check.json`),check.ndjson);
    for(const [j,s] of sheets.entries()){
     const nr=s.rows.length,nc=Math.max(...s.rows.map(x=>x.length));
     const view=await wb.render({sheetName:s.name,range:`A1:${String.fromCharCode(64+Math.min(nc,26))}${Math.min(nr,50)}`,scale:1,format:'png'});
     await fs.writeFile(path.join(qa,r.run_id+`-${idx}-sheet-${j}.png`),new Uint8Array(await view.arrayBuffer()));
    }
    await (await SpreadsheetFile.exportXlsx(wb)).save(dest);
    log.push({run_id:r.run_id,filename:name,status:'exported',kind:'xlsx',sheets:sheets.length});
   }else throw Error('Unsupported artifact extension');
  }catch(e){log.push({run_id:r.run_id,filename:name,status:'renderer_error',error:String(e)});}
 }
}
await fs.writeFile(path.join(qa,'render-log.json'),JSON.stringify(log,null,2));
console.log(JSON.stringify({processed:log.length,errors:log.filter(x=>x.status==='renderer_error')}));
