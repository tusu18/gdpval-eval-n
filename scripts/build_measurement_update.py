"""Render a source-linked research/action note without API calls or new labels."""
from pathlib import Path
import html
import json

ROOT = Path(__file__).resolve().parents[1]


def build(root=ROOT):
    root = Path(root)
    source = root / 'data/measurement_update_11/literature_sources.json'
    data = json.loads(source.read_text())
    out = root / 'output/measurement_update_11'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'literature-review.json').write_text(json.dumps(data, indent=2) + '\n')
    e = html.escape
    entries = []
    for paper in data['papers']:
        extra = ''.join(f'<li><a href="{e(url)}">Accessible primary source</a></li>' for url in paper.get('accessible_sources', []))
        entries.append(f'''<article><h2><a href="{e(paper['url'])}">{e(paper['title'])}</a></h2>
<p class="status">{e(paper['status'].replace('_', ' '))}</p>
<p><b>What the source supports:</b> {e(paper['source_lesson'])}</p>
<p><b>Project action:</b> {e(paper['project_action'])}</p>
<p><b>Limit:</b> {e(paper['limit'])}</p><p class="access">{e(paper['access'])}</p>
{('<ul>'+extra+'</ul>') if extra else ''}</article>''')
    corrections = ''.join('<li>'+e(x)+'</li>' for x in data['corrections_to_user_note'])
    native = data['native_inspection_protocol']
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Judge measurement update</title><style>
body{{font:17px/1.55 system-ui,sans-serif;max-width:960px;margin:40px auto;padding:0 24px;color:#17323b;background:#fafcfb}}
h1{{font-size:38px;line-height:1.15}}h2{{font-size:22px}}a{{color:#086b63}}article{{background:white;border:1px solid #d7e3df;border-radius:10px;padding:20px 24px;margin:20px 0}}
.status{{font-size:14px;font-weight:700;color:#73560b}}.access{{font-size:14px;color:#50636b}}.lead{{font-size:21px}}p{{margin:10px 0}}li{{margin:8px 0}}
</style><h1>Test the measurement before trusting the score</h1>
<p class="lead">Implemented diagnostics and prepared controls; no new judge requests or human labels were created by this update.</p>
<p>Source review: {e(data['review_date'])}. {e(data['purpose'])}</p>
<p>The completed 144-request study remains a separate result. The new controlled protocol is unrun. Manual full-output review remains the assignment priority.</p>
<h2>Corrections and interpretation</h2><ul>{corrections}</ul>
{''.join(entries)}
<h2>Native-file inspection comparison: specified, not executed</h2>
<p>{e(native['question'])}</p><p><b>Comparison:</b> {e(' versus '.join(native['arms']))}.</p>
<p><b>Record:</b> {e(', '.join(native['inspection_record']))}.</p>
<p><b>Measure:</b> {e(', '.join(native['human_endpoints']))}.</p><p>{e(native['limitations'])}</p>
<p>No external paper's performance figures are included as project evidence. No learned judge ensemble or training intervention has been performed.</p>
</html>'''
    (out / 'literature-review.html').write_text(page)
    return {'papers': len(entries), 'api_calls': 0, 'human_labels_created': 0}


if __name__ == '__main__':
    print(json.dumps(build()))
