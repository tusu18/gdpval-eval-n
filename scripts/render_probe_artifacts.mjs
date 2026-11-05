// Same document styling as v1; preserve every model-authored word and value.
import fs from 'node:fs/promises';
import path from 'node:path';
import {Document,Packer,Paragraph,TextRun,Table,TableRow,TableCell,WidthType,HeadingLevel,BorderStyle} from 'docx';
const root=path.resolve(path.dirname(new URL(import.meta.url).pathname),'..');
const base=path.join(root,'output/repair_probe_01');
const out=path.join(base,'artifacts');await fs.mkdir(out,{recursive:true});
const qa=path.join(base,'artifact_qa');await fs.mkdir(qa,{recursive:true});
const log=[];const border={style:BorderStyle.SINGLE,size:4,color:'D9D9D9'};
for(const filename of (await fs.readdir(path.join(base,'runs'))).filter(x=>x.endsWith('.json'))){
 const run=JSON.parse(await fs.readFile(path.join(base,'runs',filename),'utf8'));
 if(run.status!=='completed')continue;
 const dir=path.join(out,run.run_id);await fs.mkdir(dir,{recursive:true});
 for(const [i,a] of (run.final.artifacts||[]).entries()){
  const name=path.basename(a.filename||`artifact-${i}.docx`);const dest=path.join(dir,name);
  try{
   if(!name.endsWith('.docx'))throw Error('Expected a DOCX deliverable');
   if(await fs.stat(dest).catch(()=>null)){log.push({run_id:run.run_id,filename:name,status:'existing'});continue;}
   const children=[new Paragraph({text:String(a.title||''),heading:HeadingLevel.TITLE})];
   for(const s of a.sections||[]){
    if(s.heading)children.push(new Paragraph({text:String(s.heading),heading:HeadingLevel.HEADING_1}));
    for(const p of s.paragraphs||[])children.push(new Paragraph({children:[new TextRun(String(p))]}));
    if(s.table){
     const rows=[s.table.headers||[],...(s.table.rows||[])];const n=Math.max(...rows.map(x=>x.length));
     if(!n)throw Error('Empty table');
     children.push(new Table({width:{size:100,type:WidthType.PERCENTAGE},rows:rows.map((row,j)=>new TableRow({tableHeader:j===0,children:Array.from({length:n},(_,k)=>new TableCell({width:{size:100/n,type:WidthType.PERCENTAGE},borders:{top:border,bottom:border,left:border,right:border},shading:j===0?{fill:'E9EEF3'}:undefined,margins:{top:80,bottom:80,left:90,right:90},children:[new Paragraph({children:[new TextRun({text:String(row[k]??''),bold:j===0})]})]}))}))}));
    }
   }
   const doc=new Document({styles:{default:{document:{run:{font:'Calibri',size:22,color:'000000'},paragraph:{spacing:{after:100,line:276}}}},paragraphStyles:[{id:'Title',name:'Title',basedOn:'Normal',next:'Normal',run:{font:'Calibri',size:32,bold:true,color:'000000'},paragraph:{spacing:{after:160}}},{id:'Heading1',name:'heading 1',basedOn:'Normal',next:'Normal',run:{font:'Calibri',size:24,bold:true,color:'000000'},paragraph:{keepNext:true,spacing:{before:120,after:80}}}]},sections:[{properties:{page:{size:{width:12240,height:15840},margin:{top:1440,right:1440,bottom:1440,left:1440}}},children}]});
   await fs.writeFile(dest,await Packer.toBuffer(doc));log.push({run_id:run.run_id,filename:name,status:'exported'});
  }catch(e){log.push({run_id:run.run_id,filename:name,status:'renderer_error',error:String(e)});}
 }
}
await fs.writeFile(path.join(qa,'render-log.json'),JSON.stringify(log,null,2));
console.log(JSON.stringify({documents:log.length,errors:log.filter(x=>x.status==='renderer_error')}));
