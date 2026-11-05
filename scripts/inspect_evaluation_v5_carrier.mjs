// Read-only inspection of a judge disagreement. Never export or edit the input.
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import {FileBlob, SpreadsheetFile} from '@oai/artifact-tool';

const root = '/Users/tusu18/Documents/ChatGPT/Turing';
const task = '5349dd7b-bf0a-4544-9a17-75b7013767e6';
const packet = JSON.parse(await fs.readFile(`${root}/output/evaluation_v5/packets/${task}/packet.json`, 'utf8'));
const input = packet.artifacts[0].native_path;
const hash = async () => crypto.createHash('sha256').update(await fs.readFile(input)).digest('hex');
const before = await hash();
if (before !== packet.artifacts[0].sha256) throw new Error('Frozen artifact hash mismatch');
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
const selected = [
  ['Overview', 'A2:C3'], ['History', 'A2:E9'],
  ['Forecast', 'A9:E14'], ['Routing', 'A2:E8'],
  ['Sources', 'A9:D13'],
];
const ranges = [];
for (const [sheetName, address] of selected) {
  const range = workbook.worksheets.getItem(sheetName).getRange(address);
  ranges.push({sheet: sheetName, range: address, values: range.values, formulas: range.formulas});
}
const after = await hash();
if (before !== after) throw new Error('Input changed during read-only inspection');
const record = {created_at: new Date().toISOString(), task_id: task,
  method: 'Read-only Artifact Tool import and bounded getters; no edits, recalculation command or export.',
  scope: 'Presence of requested carrier comparison results and explicit source/tool limitations; not verification of published shipping rates.',
  native_path: input, before_sha256: before, after_sha256: after, input_unchanged: true, ranges};
await fs.mkdir(`${root}/output/evaluation_v5/analyst-checks`, {recursive:true});
await fs.writeFile(`${root}/output/evaluation_v5/analyst-checks/carrier-workbook.json`, JSON.stringify(record, null, 2) + '\n');
console.log(JSON.stringify({task_id:task, input_unchanged:true, inspected_ranges:ranges.map(r=>r.sheet+'!'+r.range), record:'output/evaluation_v5/analyst-checks/carrier-workbook.json'}));
