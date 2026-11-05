"""One-page leave-behind for the paired GDPval pilot. Numbers come from findings.json."""
import json
from pathlib import Path
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
F = json.loads((ROOT / "output/paired_v1/findings.json").read_text())
OUT = ROOT / "output/pdf/paired-pilot-one-pager.pdf"
INK = HexColor("#1C1915")
MUTED = HexColor("#5C564C")
PAPER = HexColor("#F3EFE6")
CARD = HexColor("#FFFDF8")
LINE = HexColor("#D9D0C2")
RUST = HexColor("#8D3418")

def wrap(c, text, font, size, x, y, width, leading, color=INK):
    c.setFont(font, size)
    c.setFillColor(color)
    words = text.split()
    line = ""
    for w in words:
        trial = w if not line else line + " " + w
        if c.stringWidth(trial, font, size) <= width:
            line = trial
        else:
            c.drawString(x, y, line)
            y -= leading
            line = w
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUT), pagesize=letter)
    w, h = letter
    c.setFillColor(PAPER)
    c.rect(0, 0, w, h, fill=1, stroke=0)
    c.setFillColor(MUTED)
    c.setFont("Times-Roman", 9)
    c.drawString(36, h - 32, "Turing field-engineer take-home  |  public GDPval gold  |  30 October 2026")
    c.drawRightString(w - 36, h - 32, "Reported API spend $3.88 of $25")
    c.setFillColor(INK)
    c.setFont("Times-Bold", 20)
    c.drawString(36, h - 58, "The hidden fact was not the failure.")
    y = wrap(
        c,
        "Both models stated the approved number when they returned a parseable file. Buy a dataset that grades the fact, the file contract, and the consequential sentence separately. This is a paired probe, not a claim to beat GDPval.",
        "Times-Roman", 11, 36, h - 78, w - 72, 14,
    )
    stats = [
        ("53/60", "Critical fields correct. Zero explicit wrong numbers."),
        ("7/60", "No file. Five of seven are GPT, truncated JSON on the SOP."),
        ("18/35", "Prose documents over the 2-3 page limit."),
        ("6/16", "Claude memos a GPT judge called critical. 0/16 GPT memos."),
    ]
    box_w = (w - 72 - 18) / 4
    top = y - 8
    for i, (n, label) in enumerate(stats):
        x = 36 + i * (box_w + 6)
        c.setFillColor(CARD)
        c.setStrokeColor(LINE)
        c.roundRect(x, top - 62, box_w, 62, 3, fill=1, stroke=1)
        c.setFillColor(INK)
        c.setFont("Times-Bold", 16)
        c.drawString(x + 8, top - 22, n)
        wrap(c, label, "Times-Roman", 8, x + 8, top - 36, box_w - 16, 10, MUTED)
    y = top - 82
    c.setFillColor(INK)
    c.setFont("Times-Bold", 12)
    c.drawString(36, y, "What to say")
    y -= 16
    left = [
        "OpenAI. Fact recovery saturated, including on GPT-6.1 Sol. The miss is the artifact: 5 of 6 change-control runs returned truncated JSON under a 6,500-token cap. Ask for an eval where a pass requires the native files and the page budget. Do not sell harder hidden facts.",
        "Anthropic. Claude finished more SOPs and still wrote coverage the 21-day record does not support. Show the sentence. The critical flags are a GPT judge on Claude outputs; the one overlap a Claude judge also saw was a disagreement. Buy expert labels, not a leaderboard.",
    ]
    col_w = (w - 72 - 12) / 2
    y2 = y
    for i, text in enumerate(left):
        x = 36 + i * (col_w + 12)
        y2 = min(y2, wrap(c, text, "Times-Roman", 9, x, y, col_w, 12))
    y = y2 - 8
    c.setFont("Times-Bold", 12)
    c.setFillColor(INK)
    c.drawString(36, y, "Seeding, said in one breath")
    y -= 14
    y = wrap(
        c,
        "Source seed: five public GDPval tasks, revision 11e7900. Task seed: the deliverable stays fixed; one operative fact is in the brief, behind record-17.txt, or contradicted by an unapproved draft. Generation seed: deterministic edits, no teacher model; 20261030 shuffles run order only. Training seed: none. A new random seed does not create an independent scenario and does not prevent contamination.",
        "Times-Roman", 9, 36, y, w - 72, 12,
    )
    y -= 2
    c.setFont("Times-Bold", 12)
    c.setFillColor(INK)
    c.drawString(36, y, "Three failures worth funding")
    y -= 16
    rows = [
        ("Unfinished file", "GPT lost 5 of 6 change-control SOPs to truncated JSON near 33k characters. Score a closed schema, and keep the token cap in the protocol."),
        ("Too long to use", "18 of 35 prose documents exceed 3 pages. GPT missed the limit on all 6 rendered supplier-exit memos. A correct memo can still be unusable."),
        ("Unsupported commitment", "Three supplier-exit memos used the right 21-day cutoff, then asserted coverage the capacity math does not support. Expert-label the sentence. The GPT judge and the Claude judge already disagreed once."),
    ]
    for title, body in rows:
        c.setFillColor(RUST)
        c.setFont("Times-Bold", 9)
        c.drawString(36, y, title)
        y = wrap(c, body, "Times-Roman", 9, 150, y, w - 186, 12)
        y -= 4
    c.setFillColor(INK)
    c.setFont("Times-Bold", 12)
    c.drawString(36, y, "Do not claim")
    y -= 14
    y = wrap(
        c,
        "Better than GDPval or AfterQuery. Training uplift. Expert acceptance. Clean pretraining. Verified workbook formulas. Content review covers 32 of 53 completed runs. Solver cost per schema-valid decision is $0.049, before human review. These five families stay evaluation-only.",
        "Times-Roman", 9, 36, y, w - 72, 12,
    )
    c.setFillColor(MUTED)
    c.setFont("Times-Roman", 8)
    c.drawString(36, 28, "Full brief: site/index.html    Numbers: output/paired_v1/findings.json    Models: GPT-6.1 Sol and Claude Sonnet 5.5")
    c.showPage()
    c.save()
    print(OUT)

if __name__ == "__main__":
    main()
