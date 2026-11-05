// Read/recalculate/render without exporting over the retained native artifact.
import fs from 'node:fs/promises';
import path from 'node:path';
import {SpreadsheetFile,FileBlob} from '@oai/artifact-tool';
const job=JSON.parse(await fs.readFile(process.argv[2],'utf8'));
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(job.path));
wb.recalculate();
const result={previews:[],sheets:[],recalculation_engine:'artifact-tool in-memory inspection; saved original is never replaced'};
const col=n=>{let s='';for(;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s;return s;};
const totalTiles=job.coverage.reduce((n,s)=>n+Math.ceil(s.rows/28)*Math.ceil(s.cols/8),0);
const sampled=totalTiles>120;
result.visual_coverage={mode:sampled?'systematic sampled tiles':'all populated-cell and drawing tiles',
  complete_tile_count:totalTiles,rendered_tile_count:0,full_native_text_extraction:true,
  limitation:sampled?'Large workbook: maximum 12 evenly spaced tiles per sheet including first/last; undisplayed cell layouts remain unverified. Complete cell text/formulas and native file retained.':null};
for(const spec of job.coverage){
  const sh=wb.worksheets.getItem(spec.name),nr=spec.rows,nc=spec.cols;
  const used=sh.getRangeByIndexes(0,0,nr,nc);
  result.sheets.push({name:spec.name,range:`A1:${col(nc)}${nr}`,values:used.values,formulas:used.formulas});
  const sheetTiles=[];
  for(let r=0;r<nr;r+=28)for(let c=0;c<nc;c+=8)sheetTiles.push([r,c]);
  const selected=sampled&&sheetTiles.length>12?new Set(Array.from({length:12},(_,i)=>Math.round(i*(sheetTiles.length-1)/11))):null;
  for(const [index,[r,c]] of sheetTiles.entries()){
    if(selected&&!selected.has(index))continue;
    const address=`${col(c+1)}${r+1}:${col(Math.min(c+8,nc))}${Math.min(r+28,nr)}`;
    const target=path.join(job.folder,`view-${result.previews.length+1}.png`);
    const image=await wb.render({sheetName:spec.name,range:address,scale:1.2,format:'png'});
    await fs.writeFile(target,new Uint8Array(await image.arrayBuffer()));
    result.previews.push({path:target,label:`${spec.name}!${address}${sampled?' [sampled visual coverage]':''}`});
  }
  for(const address of spec.drawing_ranges||[]){
    const target=path.join(job.folder,`view-${result.previews.length+1}.png`);
    const image=await wb.render({sheetName:spec.name,range:address,scale:1.2,format:'png'});
    await fs.writeFile(target,new Uint8Array(await image.arrayBuffer()));
    result.previews.push({path:target,label:`${spec.name}!${address} [complete drawing area]`});
  }
}
result.visual_coverage.rendered_tile_count=result.previews.length;
result.formula_error_scan=(await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:300}})).ndjson;
await fs.writeFile(job.result,JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({views:result.previews.length,sheets:result.sheets.length,original_unchanged:true}));
