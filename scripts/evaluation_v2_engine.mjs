// Separate original-task engine. Writes only solver-provided content.
import fs from 'node:fs/promises';
import path from 'node:path';
import {Document,Packer,Paragraph,TextRun,Table,TableRow,TableCell,WidthType,HeadingLevel} from 'docx';
import {Workbook,SpreadsheetFile,FileBlob,Presentation,PresentationFile} from '@oai/artifact-tool';
const job=JSON.parse(await fs.readFile(process.argv[2],'utf8'));
const out=job.output, dir=path.dirname(out), content=job.content||{};
await fs.mkdir(dir,{recursive:true});
const result={previews:[],engine:'@oai/artifact-tool / docx',recalculation_engine:null};
const saveBlob=async(p,b)=>fs.writeFile(p,new Uint8Array(await b.arrayBuffer()));
const column=n=>{let s='';for(;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s;return s;};
const cellPos=s=>{const m=/^([A-Z]+)([1-9][0-9]*)$/i.exec(s);if(!m)throw Error('Invalid A1 cell');return [Number(m[2])-1,[...m[1].toUpperCase()].reduce((a,c)=>26*a+c.charCodeAt(0)-64,0)-1];};
if(job.kind==='docx'){
  const children=[];
  if(content.title)children.push(new Paragraph({text:content.title,heading:HeadingLevel.TITLE}));
  for(const section of content.sections){
    if(section.page_break)children.push(new Paragraph({text:'',pageBreakBefore:true}));
    if(section.heading)children.push(new Paragraph({text:section.heading,heading:HeadingLevel.HEADING_1}));
    for(const text of section.paragraphs||[])children.push(new Paragraph({text}));
    for(const text of section.bullets||[])children.push(new Paragraph({text,bullet:{level:0}}));
    if(section.table){
      const t=section.table, rows=[...(t.headers?[t.headers]:[]),...t.rows];
      children.push(new Table({width:{size:100,type:WidthType.PERCENTAGE},rows:rows.map((r,i)=>new TableRow({tableHeader:!!t.headers&&i===0,children:r.map(v=>new TableCell({children:[new Paragraph({children:[new TextRun({text:String(v??''),bold:!!t.headers&&i===0})]})]}))}))}));
    }
  }
  const size=(content.font_size||11)*2, margin=(content.margin_inches??0.8)*1440;
  const doc=new Document({creator:'Evaluation participant',title:content.title||'',styles:{default:{document:{run:{font:'Arial',size,color:'000000'},paragraph:{spacing:{after:100,line:276}}}},paragraphStyles:[{id:'Title',name:'Title',basedOn:'Normal',run:{font:'Arial',size:32,bold:true,color:'000000'}},{id:'Heading1',name:'heading 1',basedOn:'Normal',run:{font:'Arial',size:25,bold:true,color:'000000'},paragraph:{keepNext:true}}]},sections:[{properties:{page:{size:{width:content.landscape?15840:12240,height:content.landscape?12240:15840},margin:{top:margin,right:margin,bottom:margin,left:margin}}},children}]});
  await fs.writeFile(out,await Packer.toBuffer(doc));
}else if(job.kind==='xlsx'||job.kind==='inspect_xlsx'){
  const wb=job.template?await SpreadsheetFile.importXlsx(await FileBlob.load(job.template)):Workbook.create();
  for(const s of content.sheets||[]){
    let sh;try{sh=wb.worksheets.getItem(s.name);}catch{}if(!sh)sh=wb.worksheets.add(s.name);
    const [r0,c0]=cellPos(s.start_cell||'A1'), rows=s.rows||[];
    for(let r=0;r<rows.length;r++)for(let c=0;c<rows[r].length;c++){
      const value=rows[r][c], target=sh.getCell(r0+r,c0+c);
      if(typeof value==='string'&&value.startsWith('='))target.formulas=[[value]];else target.values=[[value??null]];
    }
    for(const u of s.updates||[]){const [r,c]=cellPos(u.cell),target=sh.getCell(r,c);if(typeof u.value==='string'&&u.value.startsWith('='))target.formulas=[[u.value]];else target.values=[[u.value??null]];}
    if(!job.template&&rows.length){
      const nr=rows.length,nc=Math.max(...rows.map(r=>r.length)), used=sh.getRangeByIndexes(r0,c0,nr,nc);
      used.format.font={name:'Arial',size:11};used.format.wrapText=true;used.format.verticalAlignment='center';
      for(let c=0;c<nc;c++)sh.getRangeByIndexes(r0,c0+c,nr,1).format.columnWidth=s.column_widths?.[c]||20;
      if(s.header_row!==null)sh.getRangeByIndexes(r0+(s.header_row||0),c0,1,nc).format={fill:'#17324D',font:{bold:true,color:'#FFFFFF'},wrapText:true};
      used.format.autofitRows();sh.showGridLines=false;
    }
    for(const f of s.number_formats||[])sh.getRange(f.range).setNumberFormat(f.format);
  }
  wb.recalculate();result.recalculation_engine='artifact-tool; not Microsoft Excel';
  let reopened=wb;
  if(job.kind==='xlsx'){await(await SpreadsheetFile.exportXlsx(wb)).save(out);reopened=await SpreadsheetFile.importXlsx(await FileBlob.load(out));reopened.recalculate();}
  result.sheets=[];
  for(const spec of job.coverage){
    const sh=reopened.worksheets.getItem(spec.name),nr=spec.rows,nc=spec.cols;
    const range=sh.getRangeByIndexes(0,0,nr,nc);
    result.sheets.push({name:spec.name,range:`A1:${column(nc)}${nr}`,values:range.values,formulas:range.formulas});
    for(let r=0;r<nr;r+=28)for(let c=0;c<nc;c+=8){
      const address=`${column(c+1)}${r+1}:${column(Math.min(c+8,nc))}${Math.min(r+28,nr)}`;
      const dest=path.join(dir,`view-${result.previews.length+1}.png`);
      await saveBlob(dest,await reopened.render({sheetName:spec.name,range:address,scale:1.2,format:'png'}));
      result.previews.push({path:dest,label:`${spec.name}!${address}`});
    }
  }
  result.formula_error_scan=(await reopened.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:300}})).ndjson;
}else if(job.kind==='pptx'){
  const deck=Presentation.create({slideSize:{width:1280,height:720}});
  for(const s of content.slides){
    const slide=deck.slides.add();slide.background.fill='#FFFFFF';
    const text=(value,left,top,width,height,size,bold=false)=>{const shape=slide.shapes.add({geometry:'textbox',position:{left,top,width,height},fill:'none',line:{fill:'none',width:0}});shape.text=value;shape.text.style={fontFamily:'Arial',fontSize:size,bold,color:'#172A3A'};return shape;};
    text(s.title||'',60,35,1160,90,42,true);
    const body=[...(s.paragraphs||[]),...(s.bullets||[]).map(x=>'• '+x)].join('\n\n');
    if(body)text(body,60,145,s.table||s.chart?550:1160,510,s.font_size||26);
    if(s.table){
      const values=[...(s.table.headers?[s.table.headers]:[]),...s.table.rows];
      const table=slide.tables.add({rows:values.length,columns:values[0].length,left:body?650:60,top:150,width:body?570:1160,height:Math.min(480,values.length*45),values:values.map(r=>r.map(v=>String(v??'')))});
      for(let r=0;r<values.length;r++)for(let c=0;c<values[r].length;c++)table.getCell(r,c).text.style={fontFamily:'Arial',fontSize:20,color:'#172A3A',bold:r===0&&!!s.table.headers};
    }
    if(s.chart)slide.charts.add(s.chart.type||'bar',{position:{left:body?650:60,top:160,width:body?570:1160,height:460},categories:s.chart.categories,series:s.chart.series,hasLegend:true});
    if(s.notes)slide.speakerNotes.text=s.notes;
  }
  await(await PresentationFile.exportPptx(deck)).save(out);
  const reopened=await PresentationFile.importPptx(await FileBlob.load(out));
  for(const [i,slide] of reopened.slides.items.entries()){
    const dest=path.join(dir,`slide-${i+1}.png`);await saveBlob(dest,await reopened.export({slide,format:'png',scale:1}));
    result.previews.push({path:dest,label:`Slide ${i+1}`});
  }
  result.slide_count=content.slides.length;
}else throw Error('Unsupported engine operation');
await fs.writeFile(job.result,JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({kind:job.kind,views:result.previews.length}));
