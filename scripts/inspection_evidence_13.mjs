// Read-only workbook inspection. The input is a disposable copy with formula
// caches removed. Formulas and non-formula content are never repaired.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {FileBlob, SpreadsheetFile} from '@oai/artifact-tool';

const job=JSON.parse(await fs.readFile(process.argv[2], 'utf8'));
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const before=hash(await fs.readFile(job.input));
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(job.input));
wb.recalculate();
const sheets=[];
const images=[];
await fs.mkdir(job.output_dir,{recursive:true});
for(const [i,spec] of job.sheets.entries()){
  const sheet=wb.worksheets.getItem(spec.name);
  const range=sheet.getRange(spec.range);
  sheets.push({name:spec.name,range:spec.range,values:range.values,formulas:range.formulas});
  const blob=await wb.render({sheetName:spec.name,range:spec.range,scale:1.5,format:'png'});
  const name=`sheet-${i+1}.png`;
  const bytes=new Uint8Array(await blob.arrayBuffer());
  await fs.writeFile(path.join(job.output_dir,name),bytes);
  images.push({name,sheet:spec.name,range:spec.range,sha256:hash(bytes)});
}
if(before!==hash(await fs.readFile(job.input)))throw new Error('Inspection mutated its disposable input');
const report={engine:'@oai/artifact-tool; bundled runtime 26.1026.10807',node_version:process.version,
  input_sha256:before,formula_cache_policy:'Formula caches removed from disposable OOXML copy before import; all original formulas retained.',
  sheets,images,scope:'Read-only recalculation and rendering of disposable copies. Not a Microsoft Excel application validation.'};
await fs.writeFile(path.join(job.output_dir,'recalculation.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({sheets:sheets.length,images:images.length}));
