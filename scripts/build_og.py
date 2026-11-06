#!/usr/bin/env python3
"""Render docs/og.png (1200x630 link preview) from output/results.json with headless Chromium.

    python3 scripts/build_og.py [--fonts DIR]   # DIR holds Spectral/Public Sans/JetBrains Mono woff2 files (optional)
"""
import argparse, json, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def card(R, fonts):
    h, hu, f = R['historical'], R['human_reviews'], R['follow_up']
    g, s = f['per_judge']['gemini'], f['per_judge']['sol']
    stats = [
        (f"{h['fact_checks']['decision_pass']} / {h['parseable_outputs']}", 'deliverables passed the fact checks'),
        (f"{hu['consequential_errors']} of {hu['reviewed']}", 'read in full still carry an error someone would act on'),
        (f"{g['clean']} vs {s['clean']}", f"of {g['outputs']} outputs cleared by Gemini vs by Sol: the judge decides"),
    ]
    v = R.get('v31')
    if v and v.get('random_sample', {}).get('labeled'):
        rs = v['random_sample']
        stats[1] = (f"{rs['prevalence'][0]} of {rs['prevalence'][1]}", 'random-sample outputs with a human-confirmed consequential error')
    ff = ''
    if fonts:
        for fam, file, w in [('Spectral', 'spectral-latin-700-normal.woff2', 700), ('Public Sans', 'public-sans-latin-400-normal.woff2', 400),
                             ('Public Sans', 'public-sans-latin-600-normal.woff2', 600), ('JetBrains Mono', 'jetbrains-mono-latin-400-normal.woff2', 400)]:
            p = next(Path(fonts).rglob(file), None)
            if p: ff += f"@font-face{{font-family:'{fam}';font-weight:{w};src:url('file://{p}') format('woff2')}}\n"
    cells = ''.join(f'<div class="s"><div class="v">{a}</div><div class="l">{b}</div></div>' for a, b in stats)
    return f'''<!doctype html><meta charset="utf-8"><style>{ff}
*{{box-sizing:border-box;margin:0}}
body{{width:1200px;height:630px;background:#F5F7F5;color:#18201D;font-family:'Public Sans',sans-serif;padding:64px 72px;display:flex;flex-direction:column;justify-content:space-between;border-top:14px solid #27479A}}
.e{{font-family:'JetBrains Mono',monospace;font-size:22px;color:#27479A;letter-spacing:.04em;text-transform:uppercase}}
h1{{font-family:'Spectral',serif;font-weight:700;font-size:88px;line-height:1;margin-top:18px;letter-spacing:-.01em}}
p{{font-size:28px;color:#56625C;margin-top:18px;max-width:1000px;line-height:1.35}}
.row{{display:grid;grid-template-columns:repeat(3,1fr);gap:22px}}
.s{{border:2px solid #D6DCD8;border-radius:14px;background:#fff;padding:20px 22px}}
.v{{font-family:'Spectral',serif;font-weight:700;font-size:52px;line-height:1;color:#B42318}}
.s:nth-child(1) .v{{color:#2E6A3E}}.s:nth-child(3) .v{{color:#27479A}}
.l{{font-size:21px;color:#56625C;margin-top:8px;line-height:1.3}}
</style><body><div><div class="e">GDPval evaluation · Turing take-home</div><h1>Right facts, wrong plan</h1>
<p>Frontier models write documents that state the rule correctly and break it in the clause someone acts on.</p></div>
<div class="row">{cells}</div></body>'''


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--fonts'); ap.add_argument('--out', default=str(ROOT / 'docs/og.png')); a = ap.parse_args()
    R = json.loads((ROOT / 'output/results.json').read_text())
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory() as d:
        page_path = Path(d) / 'og.html'; page_path.write_text(card(R, a.fonts))
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={'width': 1200, 'height': 630}, device_scale_factor=1)
            pg.goto(page_path.as_uri()); pg.wait_for_timeout(300); pg.screenshot(path=a.out); b.close()
    print('wrote', a.out)


if __name__ == '__main__':
    main()
