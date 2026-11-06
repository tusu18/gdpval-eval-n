#!/usr/bin/env python3
"""Write docs/methods.html: every prompt, rule and setting, pulled verbatim from the code that ran.

Strings are read from the source files with ast (nothing is imported or executed), so this page
cannot drift from what was sent to the solvers and judges.

    python3 scripts/build_methods.py
"""
import ast, html, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / 'scripts'
REPO = 'https://github.com/tusu18/gdpval-eval-n/blob/main/'


def const(path, name):
    tree = ast.parse((S / path).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(f'{name} not found in {path}')


def grab(path, pattern):
    m = re.search(pattern, (S / path).read_text())
    if not m:
        raise KeyError(f'{pattern!r} not found in {path}')
    return m.group(1)


e = html.escape
PRE = lambda s: f'<pre>{e(s)}</pre>'


def page():
    cfg = json.loads((ROOT / 'config/study_v31.json').read_text())
    preamble = const('study_v3_pipeline.py', 'SOLVER_PREAMBLE')
    addenda = const('study_v3_pipeline.py', 'TIER_ADDENDUM')
    claude_args = const('study_v3_pipeline.py', 'CLAUDE_ARGS')
    judges = const('study_v3_pipeline.py', 'JUDGES')
    judge_prompt = const('evidence_grader_v2.py', 'JUDGE_INSTRUCTIONS_V2')
    judge_suffix = grab('study_v3_pipeline.py', r"JUDGE_INSTRUCTIONS_V2 \+ '(.*?)'\}")
    severity = const('evidence_grader_v2.py', 'SEVERITY')
    pair_prompt = const('pairwise_grader_16.py', 'INSTRUCTIONS')
    critical = grab('study_v3_pipeline.py', r"CRITICAL = re\.compile\(r'(.*?)'")
    operative = grab('study_v3_pipeline.py', r"OPERATIVE = re\.compile\(r'(.*?)'")
    cap = grab('study_v3_pipeline.py', r'CAP = (\d+);')
    cats = const('human_review_kit.py', 'CATEGORIES')
    questions = const('human_review_kit.py', 'QUESTIONS')
    seed = const('human_review_kit.py', 'SEED_V31'); n_rand = const('human_review_kit.py', 'N_V31')
    loc = grab('evidence_grader_v2.py', r"LOC = re\.compile\(r'(.*?)'")
    sel = json.loads((ROOT / 'data/gdpval_v31/selection_report.json').read_text()) if (ROOT / 'data/gdpval_v31/selection_report.json').exists() else {}
    tasks_csv = (ROOT / 'data/gdpval_v31/task_selection.csv')

    rows = []
    if tasks_csv.exists():
        import csv
        for r in csv.DictReader(tasks_csv.open()):
            rows.append(r)
    task_cfg = {t['id_prefix']: t for t in cfg.get('tasks', [])}

    tiers = ''.join(f'<tr><td class="k">{e(k)}</td><td>{e(v)}</td><td class="mono">{e(addenda.get(k, "(none: tier-A prompt unchanged from v3)"))}</td></tr>' for k, v in cfg['tiers'].items())
    sev = ''.join(f'<tr><td class="n">{k}</td><td>{e(v)}</td></tr>' for k, v in severity.items())
    catrows = ''.join(f'<tr><td class="mono">{e(k)}</td><td>{e(v)}</td></tr>' for k, v in cats.items())
    qs = ''.join(f'<li>{e(q)}</li>' for q in questions)
    budgets = dict(cfg.get('budget_usd_cumulative_guards') or {}); bnote = budgets.pop('note', '')
    bud = ''.join(f'<tr><td class="mono">{e(k)}</td><td class="n">${e(str(v))}</td></tr>' for k, v in budgets.items())
    stops = cfg.get('stop_rules') or []
    stop = ''.join(f'<li>{e(s)}</li>' for s in stops) if isinstance(stops, list) else ''
    pred = ''.join(f'<tr><td class="k">{e(p["id"])}</td><td>{e(p["claim"])}<div class="small muted">Fails if: {e(p.get("fails_if", ""))}</div></td></tr>' for p in cfg.get('predictions', []))

    if rows:
        new = set(cfg['occupations']['new'])
        def tr(r):
            t = task_cfg.get(r['task_id'][:8], {})
            return (f'<tr><td class="mono">{e(r["task_id"][:8])}</td><td>{e(r["occupation"])}{" <span class=muted>· new</span>" if r["occupation"] in new else ""}</td>'
                    f'<td>{e(t.get("tier", ""))}</td><td>{e(t.get("deliverable", r.get("gold_deliverable_formats", "")))}</td><td class="n">{e(r.get("reference_count", ""))}</td><td class="n">{e(r.get("rubric_items", ""))}</td></tr>')
        trows = ''.join(tr(r) for r in rows)
        tasktable = ('<div class="tablewrap"><table><thead><tr><th>Task</th><th>Occupation</th><th>Tier</th><th>Deliverable</th><th style="text-align:right">Ref. files</th><th style="text-align:right">GDPval rubric items</th></tr></thead>'
                     f'<tbody>{trows}</tbody></table></div>')
    else:
        tasktable = '<p class="muted">data/gdpval_v31/task_selection.csv not present.</p>'

    return f'''<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Methods and Prompts</title>
<meta name="description" content="Every prompt, selection rule, validator check, seed and budget behind the GDPval evaluation, generated from the code that ran.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Spectral:wght@600;700&family=Public+Sans:wght@400;600&family=JetBrains+Mono:wght@400&display=swap">
<style>
:root {{ --paper:#F5F7F5; --card:#FFFFFF; --ink:#18201D; --muted:#56625C; --rule:#D6DCD8; --accent:#27479A; --accent-soft:#E5EAF6;
  --display:"Spectral",Georgia,serif; --body:"Public Sans",-apple-system,"Segoe UI",Roboto,Arial,sans-serif; --mono:"JetBrains Mono",ui-monospace,Menlo,Consolas,monospace; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --paper:#101412; --card:#171D1A; --ink:#E3E8E4; --muted:#9AA6A0; --rule:#2A332F; --accent:#9DB1EE; --accent-soft:#1D2640; color-scheme:dark; }} }}
:root[data-theme="dark"] {{ --paper:#101412; --card:#171D1A; --ink:#E3E8E4; --muted:#9AA6A0; --rule:#2A332F; --accent:#9DB1EE; --accent-soft:#1D2640; color-scheme:dark; }}
* {{ box-sizing:border-box; }}
body {{ background:var(--paper); color:var(--ink); font-family:var(--body); font-size:16px; line-height:1.6; margin:0; padding:32px 16px 64px; }}
main {{ max-width:820px; margin:0 auto; display:flex; flex-direction:column; gap:40px; }}
section {{ display:flex; flex-direction:column; gap:12px; min-width:0; }}
h1,h2,h3 {{ font-family:var(--display); margin:0; line-height:1.15; text-wrap:balance; }}
h1 {{ font-size:clamp(2rem,5vw,2.8rem); }} h2 {{ font-size:1.45rem; }} h3 {{ font-size:1.1rem; }}
p,li {{ max-width:70ch; }} p {{ margin:0; }}
a {{ color:var(--accent); }}
.muted {{ color:var(--muted); }} .small {{ font-size:.875rem; }} .mono {{ font-family:var(--mono); font-size:.82em; }}
.eyebrow {{ font-family:var(--mono); font-size:.78rem; color:var(--accent); letter-spacing:.04em; text-transform:uppercase; }}
pre {{ background:var(--card); border:1px solid var(--rule); border-radius:8px; padding:14px 16px; font-family:var(--mono); font-size:.8rem; line-height:1.55; white-space:pre-wrap; word-break:break-word; margin:0; }}
.tablewrap {{ overflow-x:auto; min-width:0; }}
table {{ border-collapse:collapse; width:100%; font-size:.88rem; }}
th,td {{ text-align:left; vertical-align:top; padding:8px 10px 8px 0; border-bottom:1px solid var(--rule); }}
th {{ font-size:.72rem; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); font-weight:600; }}
td.k {{ font-weight:600; white-space:nowrap; }} td.n {{ font-family:var(--mono); text-align:right; white-space:nowrap; padding-right:14px; }}
.nav {{ position:sticky; top:0; background:var(--paper); border-bottom:1px solid var(--rule); margin:-32px -16px 0; padding:10px 16px; display:flex; flex-wrap:wrap; gap:14px; font-family:var(--mono); font-size:.8rem; z-index:2; }}
.nav a {{ color:var(--muted); text-decoration:none; }} .nav a:hover {{ color:var(--accent); }}
ul {{ margin:0; padding-left:1.1rem; display:flex; flex-direction:column; gap:6px; }}
.note {{ border-left:3px solid var(--accent); padding:4px 12px; font-size:.9rem; }}
</style>
<main>
<nav class="nav" aria-label="Sections"><a href="index.html">← Findings</a><a href="#solver">Solver</a><a href="#slice">Slice</a><a href="#select">Requirements</a><a href="#judge">Judge</a><a href="#validator">Validator</a><a href="#pref">Preference</a><a href="#human">Human review</a><a href="#prereg">Pre-registration</a><a href="#repro">Reproduce</a></nav>

<section>
  <div class="eyebrow">Methods · generated from the code that ran</div>
  <h1>Prompts, rules and settings</h1>
  <p>Everything a reviewer needs to rerun or challenge the evaluation. Prompts below are read out of the source files by <a href="{REPO}scripts/build_methods.py">build_methods.py</a>, so they are the strings that were sent, byte for byte.</p>
</section>

<section aria-labelledby="solver">
  <h2 id="solver">Solver harness</h2>
  <p>Each attempt is one headless Claude Code run in its own sandbox folder holding the reference files and an empty <span class="mono">outputs/</span>: <span class="mono">claude -p &lt;prompt&gt; --model sonnet|opus {e(' '.join(claude_args))} --max-turns 40</span>, timeout 30 minutes in the first study and 60 minutes in v3.1. No retries inside a run; a second pass reruns every attempt that did not deliver a file (timeout, no output, error). Repeats (r2) are independent second attempts with the same prompt.</p>
  <h3>Preamble (prepended to every GDPval prompt)</h3>
  {PRE(preamble)}
  <h3>Tiers and the one sentence each adds</h3>
  <div class="tablewrap"><table><thead><tr><th>Tier</th><th>What it covers</th><th>Added to the preamble</th></tr></thead><tbody>{tiers}</tbody></table></div>
  <p class="small muted">Tier W also drops the sentence “There is no internet.” Tier-A prompts are byte-identical to the first study.</p>
</section>

<section aria-labelledby="slice">
  <h2 id="slice">Slice selection</h2>
  <p>Dataset <span class="mono">{e(cfg['dataset']['name'])}</span> at revision <span class="mono">{e(cfg['dataset']['revision'][:12])}</span>, parquet sha256 <span class="mono">{e(cfg['dataset']['parquet_sha256'][:16])}…</span>.</p>
  <p class="note">{e(cfg['dataset']['selection_rule'])}</p>
  {tasktable}
</section>

<section aria-labelledby="select">
  <h2 id="select">Which requirements are judged</h2>
  <p>Requirements are extracted per task family into <span class="mono">data/study_v3/requirements/</span>. A requirement is <b>critical</b> when its text matches the pattern below. The judge sees every critical requirement, then the remaining ones ranked by how many operative keywords they contain, up to <b>{cap}</b> per output. The cap is a cost decision; the full-rubric check reruns human-confirmed errors with every requirement to measure what the cap hides.</p>
  <h3>Critical</h3>{PRE(critical)}
  <h3>Operative keywords (ranking)</h3>{PRE(operative)}
</section>

<section aria-labelledby="judge">
  <h2 id="judge">Rubric judge prompt (system message)</h2>
  <p>Judges: {', '.join(f'<span class="mono">{e(v)}</span>' for v in judges.values())} via OpenRouter; max_tokens 12000, reasoning effort medium, JSON response format, provider fallbacks off. The user message is the packet: request, source documents (reference-file text, capped at 240,000 characters per packet with proportional truncation), the selected requirements, and the extracted output with a locator on every line. Solver identity, earlier grades and human labels are never in the packet.</p>
  <p class="note"><b>Output budget (v3.1, added after solving, before those outputs were judged).</b> Some new outputs are data dumps of up to 30 MB of extracted cells, beyond what either judge accepts. When an output's extracted text exceeds 280,000 characters (the largest output any judge read in the first study, so no earlier packet changes), sheets and sections smaller than an equal share are kept whole and only the largest are cut to their first rows, with a marker line saying how many units were left out and a note that absence cannot be established for that file. Affected outputs are flagged in the results and on the drill-down.</p>
  {PRE(judge_prompt + ast.literal_eval("'" + judge_suffix + "'"))}
  <h3>Severity scale</h3>
  <div class="tablewrap"><table><tbody>{sev}</tbody></table></div>
</section>

<section aria-labelledby="validator">
  <h2 id="validator">Validator: what makes a judgment count</h2>
  <ul>
    <li>Every selected requirement is answered exactly once with a <b>stated</b> and an <b>honored</b> check, each pass / fail / uncertain.</li>
    <li>Every quote must be an exact substring of the named source or output. Output locators must exist in the extracted file and match this pattern: <span class="mono">{e(loc)}</span>.</li>
    <li>Coverage contract: every operative section named in the packet must be listed under <span class="mono">operative_sections_inspected</span> with a real locator and a quote from that unit; otherwise the judgment is invalid, not scored.</li>
    <li>An honored pass resting on fewer than two distinct quotes is downgraded to uncertain.</li>
    <li>An honored fail must carry severity 1–5, consequence, minimum correction and counter-evidence.</li>
    <li>If the judge reports a task defect (yes or uncertain), the output is not scored.</li>
    <li>Scoring is a gate, not an average: any critical honored fail, or any honored fail at severity 4 or above, marks the output as carrying a consequential error.</li>
  </ul>
</section>

<section aria-labelledby="pref">
  <h2 id="pref">Preference judge (GDPval-style comparison)</h2>
  <p>Same two judge models, each pair shown twice with A and B swapped; a verdict counts only when both orders agree (position-consistent). max_tokens 3000, reasoning effort medium. It approximates the comparison GDPval's own automated grader makes; that grader could not be used here because OpenAI's Evals platform went read-only on 31 October 2026.</p>
  {PRE(pair_prompt)}
</section>

<section aria-labelledby="human">
  <h2 id="human">Human review protocol</h2>
  <p>Random sample: {n_rand} first-attempt outputs of original (non-conflict) tasks, stratified by occupation and alternating solver, seed <span class="mono">{seed}</span>, frozen before any v3.1 judge result was opened. Outputs already labeled earlier are excluded from the draw. Packets carry the request, the sources and the full output text, and nothing from any judge. The reviewer answers before opening any judge file and records minutes.</p>
  <p class="note">For the 27 v3.1 cases (22 random sample + 5 historical Sol), the labels were drafted blind by an AI reviewer (Codex) and each draft was then checked by the author against the packet (about 3 hours; all 27 confirmed, none changed). The 8 labels from the first study were written by the author directly. Results count a drafted label only once it carries the author's check.</p>
  <h3>Questions</h3><ol>{qs}</ol>
  <h3>Hand taxonomy (one primary category per confirmed error)</h3>
  <div class="tablewrap"><table><tbody>{catrows}</tbody></table></div>
  <p class="small muted">Each confirmed error also records where it sits in the document and whether the governing rule is stated correctly elsewhere in the same deliverable. A second reviewer uses the same kit; agreement is reported as Cohen's κ when available.</p>
</section>

<section aria-labelledby="prereg">
  <h2 id="prereg">Pre-registration: predictions, budgets, stop rules</h2>
  <p>Registered {e(cfg.get('registered_at', ''))} before any v3.1 output existed: <a href="{REPO}config/study_v31.json">config/study_v31.json</a>, <a href="{REPO}docs/study_v31_plan.md">plan</a>.</p>
  {f'<div class="tablewrap"><table><tbody>{pred}</tbody></table></div>' if pred else ''}
  {f'<h3>Spend guards</h3><p class="small muted">{e(bnote)}</p><div class="tablewrap"><table><tbody>{bud}</tbody></table></div>' if bud else ''}
  {f'<h3>Stop rules</h3><ul>{stop}</ul>' if stop else ''}
</section>

<section aria-labelledby="repro">
  <h2 id="repro">Reproduce</h2>
{PRE("""git clone https://github.com/tusu18/gdpval-eval-n && cd gdpval-eval-n
pip install -r requirements.txt python-pptx reportlab
bash night.sh 1                      # references, prepare, solve r1, freeze sample, blind packets
export OPENROUTER_API_KEY=...        # judge phases only; never written to disk
bash night.sh 2                      # rubric judges + preference judges + report
bash night.sh 3                      # repeats
python3 scripts/human_review_kit.py record --run <id> --reviewer <you> --acceptable yes|no|uncertain --consequential yes|no|uncertain --defect no ...
bash night.sh 4                      # full-rubric check on confirmed errors
python3 scripts/build_results.py && python3 scripts/build_site.py && python3 -m pytest tests -q""")}
  <p class="small muted">Generated by scripts/build_methods.py. Spend is read from the per-call cost OpenRouter returns, logged in the ledgers under <span class="mono">output/</span>.</p>
</section>
</main>
'''


if __name__ == '__main__':
    out = ROOT / 'docs' / 'methods.html'
    if out.exists(): out.chmod(0o644)
    out.write_text(page())
    print('wrote', out)
