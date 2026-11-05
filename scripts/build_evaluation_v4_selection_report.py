"""Readable selection rationale and honest execution status, without model runs."""
import json
import html
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/evaluation_v4'

def h(v):return html.escape(str(v))
def link(path,label):return f'<a href="{h(os.path.relpath(path,OUT))}">{h(label)}</a>'

def main():
    selection=json.loads((ROOT/'data/evaluation_v4/selection.json').read_text())
    roster=json.loads((ROOT/'data/evaluation_v4/task-roster.json').read_text())
    OUT.mkdir(parents=True,exist_ok=True)
    body=['<h1>Balanced selection of 40 original GDPval tasks</h1>',
      '<p><strong>Historical selection snapshot: 40 selected, 20 with outputs and 20 awaiting execution at the freeze.</strong> '+link(OUT/'report.html','Open the current 40-task execution report')+'. The counts below preserve the selection-time record.</p>',
      '<p>The public gold release supplies five tasks per occupation. Retaining all five makes 40 tasks across eight occupations the closest complete balanced design to the proposed target of 39. No repeated run, synthetic variation or edited workbook input counts as a new original task.</p>',
      '<table><tr><th>Occupation</th><th>Existing outputs</th><th>Still to run</th><th>Why included</th></tr>']
    for row in selection['occupations']:
        body.append(f'<tr><td>{h(row["occupation"])}</td><td>{row["existing_outputs"]} / 5</td><td>{row["remaining"]}</td><td>{h(row["selection_rationale"])}</td></tr>')
    body+=['</table>','<h2>Selection method</h2>','<pre>'+h((ROOT/'docs/evaluation_v4/selection-method.txt').read_text())+'</pre>',
      '<h2>Before execution</h2>',
      '<p>At selection time the earlier native schema lacked several required spreadsheet features, including actual pivot tables, filters and charts. The v4 execution subsequently qualified these features and added logged builders, research provenance and inspection. '+link(ROOT/'docs/evaluation_v4/artificial-analysis-method-addendum.txt','Read the Artificial Analysis review and harness rationale')+'. A flat table cannot be counted as a requested native pivot.</p>',
      '<p>Retain all selected task IDs when reporting source problems or infrastructure failures. Preserve first attempts and separately label recovery. Do not silently replace a difficult task after seeing its output.</p>',
      '<p>The previous OpenRouter and in-app cohorts differ in tools and resource limits. A balanced roster alone does not make their outcomes comparable. Any model comparison needs a matched execution and grading protocol. Human acceptance remains a separate measured outcome.</p>',
      '<h2>Audit records</h2><p>'+link(ROOT/'data/evaluation_v4/task-roster.csv','All 40 task IDs and selection-time status')+' · '+link(ROOT/'data/evaluation_v4/selection-freeze.json','Frozen selection hashes')+' · '+link(ROOT/'docs/evaluation_v4/candidate-screening.json','Candidate occupation screening')+' · '+link(ROOT/'data/evaluation_v4/tasks.jsonl','Original solver-safe tasks')+' · '+link(ROOT/'output/evaluation_v3/report.html','Earlier 20-task coverage')+'</p>',
      '<p>Dataset provenance: <a href="https://openai.com/index/gdpval/">OpenAI GDPval description</a>; <a href="https://huggingface.co/datasets/openai/gdpval">public dataset</a>. Pinned revision '+h(selection['revision'])+'.</p>',
      '<details><summary>Task roster</summary><table><tr><th>Task ID</th><th>Occupation</th><th>Status</th></tr>']
    for row in roster:body.append(f'<tr><td>{h(row["task_id"])}</td><td>{h(row["occupation"])}</td><td>{h(row["status"])}</td></tr>')
    body+=['</table></details>']
    style='body{font:17px/1.55 system-ui,sans-serif;color:#1c2c38;max-width:1100px;margin:40px auto;padding:0 24px}table{border-collapse:collapse;width:100%;font-size:15px}th,td{padding:10px;text-align:left;vertical-align:top;border-bottom:1px solid #ccd4dc}pre{white-space:pre-wrap;font:inherit}a{color:#165d90}h1,h2{line-height:1.2}'
    p=OUT/'selection.html';p.write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>GDPval balanced selection</title><style>'+style+'</style><body>'+''.join(body)+'</body></html>')
    print(p)

if __name__=='__main__':main()
