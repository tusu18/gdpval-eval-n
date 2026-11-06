#!/usr/bin/env python3
"""Build the published page from output/results.json (written by scripts/build_results.py).

Copies it to docs/results.json (the download link), embeds it in docs/index.html as <script type="application/json" id="site-data">,
and splices in the study v3.1 sections (site_src/v31_sections.html) with their CSS and JS
(site_src/v31_assets.txt). The v3.1 sections render client-side from the embedded data and
hide themselves when results.json has no v3.1 block. Idempotent: re-running replaces the
previous splice.

    python3 scripts/build_site.py                      # docs/index.html in place
    python3 scripts/build_site.py --artifact OUT.html  # also a copy with absolute links
"""
import argparse, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
PITCH_ARTIFACT = 'https://claude.ai/artifact/RULFKAWNQUaPKZ1VLnS72z'
REPO = 'https://github.com/tusu18/gdpval-eval-n'
PAGES = 'https://tusu18.github.io/gdpval-eval-n/'

# section id -> the existing section it is placed before
PLACEMENT = {'h-rep': 'h-tax', 'h-handtax': 'h-short', 'h-tasks': 'h-data'}
NAV = {'h-rep': ('Replication', 'h-tax'), 'h-tasks': ('Every task', 'h-data')}


HEADS = {
    'index.html': ('Right facts, wrong plan: a GDPval evaluation', 'Frontier models on GDPval tasks: every deliverable passed the fact checks, yet half of those read in full carry an error in the clause someone acts on. Grader comparison, hand taxonomy, dataset proposal.', ''),
    'pitch.html': ('Two lab pitches: GDPval evaluation', 'The same evidence pitched to OpenAI and Anthropic researchers, with the hard questions and the answers the record supports.', 'pitch.html'),
    'methods.html': None,  # methods.html writes its own head
}


def head(fname):
    title, desc, path = HEADS[fname]
    url = PAGES + path
    meta = [('name', 'viewport', 'width=device-width, initial-scale=1'), ('name', 'description', desc),
            ('property', 'og:type', 'website'), ('property', 'og:title', title), ('property', 'og:description', desc),
            ('property', 'og:url', url), ('property', 'og:image', PAGES + 'og.png'), ('property', 'og:image:width', '1200'),
            ('property', 'og:image:height', '630'), ('name', 'twitter:card', 'summary_large_image'), ('name', 'twitter:image', PAGES + 'og.png')]
    tags = '\n'.join('<meta %s="%s" content="%s">' % (k, n, v.replace('"', '&quot;')) for k, n, v in meta)
    return '<!doctype html>\n' + wrap('head', '\n<html lang="en">\n<meta charset="utf-8">\n' + tags + '\n') + '\n'


def with_head(html, fname):
    if html.startswith('<!doctype html>\n'):
        html = html[len('<!doctype html>\n'):]
    html = strip(html, 'head')
    return head(fname) + html


def strip(html, name):
    return re.sub(r'<!--v31:%s-->.*?<!--/v31:%s-->\n?' % (name, name), '', html, flags=re.S)


def wrap(name, body):
    return '<!--v31:%s-->%s<!--/v31:%s-->' % (name, body, name)


def sections(src):
    out = {}
    for m in re.finditer(r'<section aria-labelledby="(h-[a-z0-9-]+)".*?</section>', src, re.S):
        out[m.group(1)] = m.group(0)
    missing = set(PLACEMENT) - set(out)
    if missing:
        sys.exit('v31_sections.html is missing: %s' % sorted(missing))
    return out


def build(html, data):
    assets = (ROOT / 'site_src' / 'v31_assets.txt').read_text()
    css, js = assets.split('/*JS*/', 1)
    css = css.replace('/*CSS*/', '').strip()
    secs = sections((ROOT / 'site_src' / 'v31_sections.html').read_text())

    for name in ['css', 'data', 'js', 'nav-h-rep', 'nav-h-tasks'] + list(PLACEMENT):
        html = strip(html, name)

    html = html.replace('</style>', wrap('css', '\n' + css + '\n') + '\n</style>', 1)
    for sid, before in PLACEMENT.items():
        anchor = '<section aria-labelledby="%s">' % before
        if anchor not in html:
            sys.exit('anchor not found: ' + anchor)
        html = html.replace(anchor, wrap(sid, '\n' + secs[sid] + '\n') + '\n' + anchor, 1)
    html = strip(html, 'nav-methods')
    html = html.replace('<a href="pitch.html">Full pitch page →</a>', wrap('nav-methods', '<a href="methods.html">Methods</a>') + '<a href="pitch.html">Full pitch page →</a>', 1)
    for sid, (label, before) in NAV.items():
        a = '<a href="#%s">' % before
        html = html.replace(a, wrap('nav-' + sid, '<a href="#%s" data-v31nav>%s</a>' % (sid, label)) + a, 1)

    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    tail = (wrap('data', '\n<script type="application/json" id="site-data">' + payload + '</script>\n')
            + '\n' + wrap('js', '\n<script>\n' + js.strip() + '\n</script>\n') + '\n')
    i = html.rfind('</body>')
    if i < 0:
        return html.rstrip('\n') + '\n' + tail
    return html[:i] + tail + html[i:]


def artifact_copy(html):
    html = html.replace('href="pitch.html"', 'href="%s"' % PITCH_ARTIFACT)
    html = html.replace('href="results.json" download', 'href="%s/blob/main/docs/results.json"' % REPO)
    html = html.replace('href="methods.html"', 'href="%smethods.html"' % PAGES)
    if html.startswith('<!doctype html>\n'):  # the artifact host supplies its own document skeleton
        html = strip(html[len('<!doctype html>\n'):], 'head')
    return html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--results', default=str(ROOT / 'output' / 'results.json'))
    ap.add_argument('--page', default=str(DOCS / 'index.html'))
    ap.add_argument('--artifact')
    a = ap.parse_args()
    raw = Path(a.results).read_text(); data = json.loads(raw)
    dst = DOCS / 'results.json'
    if Path(a.results).resolve() != dst.resolve():
        if dst.exists(): dst.chmod(0o644)
        dst.write_text(raw)
    page = Path(a.page)
    if page.exists(): page.chmod(0o644)
    html = with_head(build(page.read_text(), data), 'index.html')
    page.write_text(html)
    pitch = DOCS / 'pitch.html'
    if pitch.exists():
        pitch.chmod(0o644); pitch.write_text(with_head(pitch.read_text(), 'pitch.html'))
    print('wrote', page, '%.0f KB' % (len(html.encode()) / 1024), '| v3.1 block:', 'yes' if data.get('v31') else 'no (sections hidden)')
    if a.artifact:
        Path(a.artifact).write_text(artifact_copy(html))
        print('wrote', a.artifact)


if __name__ == '__main__':
    main()
