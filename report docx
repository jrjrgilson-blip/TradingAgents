"""
Converte o relatório markdown do TradingAgents em um .docx formatado.

Usado pelo app.py (botão "Baixar em Word"). Também roda sozinho:

    python report_docx.py entrada.md saida.docx
"""

import io
import re
from datetime import datetime

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

# --------------------------------------------------------------- estilo

INK = RGBColor(0x1A, 0x1A, 0x1A)
ACCENT = RGBColor(0x0F, 0x4C, 0x5C)
MUTED = RGBColor(0x5B, 0x6B, 0x70)
WARN = RGBColor(0x9A, 0x34, 0x12)

ACCENT_HEX = "0F4C5C"
RULE_HEX = "C9D4D8"
ZEBRA_HEX = "F4F8F9"
BOX_HEX = "F7FAFB"

HEAD_FONT = "Georgia"
BODY_FONT = "Calibri"

# Seções de topo do markdown gerado pelo app. As não listadas em
# SECTION_TITLES são metadados internos do grafo e ficam de fora.
TOPLEVEL = [
    "Decisão final", "Company of interest", "Asset type", "Instrument context",
    "Trade date", "Market report", "Sentiment report", "News report",
    "Fundamentals report", "Investment plan", "Sender",
    "Trader investment plan", "Final trade decision",
]

SECTION_TITLES = [
    ("Market report", "1. Análise Técnica"),
    ("Sentiment report", "2. Análise de Sentimento"),
    ("News report", "3. Notícias e Macroeconomia"),
    ("Fundamentals report", "4. Análise Fundamentalista"),
    ("Investment plan", "5. Plano de Investimento — Comitê de Pesquisa"),
    ("Trader investment plan", "6. Plano Operacional do Trader"),
    ("Final trade decision", "7. Decisão Final — Comitê de Risco"),
]


# --------------------------------------------------------- utilidades XML

def _shade(cell, hex_fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tcPr.append(shd)


def _border(paragraph, edge="bottom", size=8, color=RULE_HEX, space=6):
    pPr = paragraph._p.get_or_add_pPr()
    borders = pPr.find(qn("w:pBdr"))
    if borders is None:
        borders = OxmlElement("w:pBdr")
        pPr.append(borders)
    el = OxmlElement(f"w:{edge}")
    el.set(qn("w:val"), "single")
    el.set(qn("w:sz"), str(size))
    el.set(qn("w:space"), str(space))
    el.set(qn("w:color"), color)
    borders.append(el)


def _page_number_field(paragraph):
    run = paragraph.add_run()
    for tag, attrs, text in (
        ("w:fldChar", {"w:fldCharType": "begin"}, None),
        ("w:instrText", {"xml:space": "preserve"}, " PAGE "),
        ("w:fldChar", {"w:fldCharType": "end"}, None),
    ):
        el = OxmlElement(tag)
        for k, v in attrs.items():
            el.set(qn(k), v)
        if text:
            el.text = text
        run._r.append(el)
    run.font.name = BODY_FONT
    run.font.size = Pt(8)
    run.font.color.rgb = MUTED


# --------------------------------------------------------- blocos de texto

INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`)")


def _add_inline(paragraph, text, size=10.5, color=INK, bold=False):
    pos = 0
    for m in INLINE_RE.finditer(text):
        if m.start() > pos:
            r = paragraph.add_run(text[pos:m.start()])
            r.font.name, r.font.size, r.font.color.rgb, r.bold = BODY_FONT, Pt(size), color, bold
        tok = m.group(0)
        if tok.startswith("**"):
            r = paragraph.add_run(tok[2:-2])
            r.font.name, r.font.size, r.font.color.rgb, r.bold = BODY_FONT, Pt(size), color, True
        else:
            r = paragraph.add_run(tok[1:-1])
            r.font.name, r.font.size, r.font.color.rgb = "Consolas", Pt(size - 1), color
        pos = m.end()
    if pos < len(text):
        r = paragraph.add_run(text[pos:])
        r.font.name, r.font.size, r.font.color.rgb, r.bold = BODY_FONT, Pt(size), color, bold


def _para(doc, text, size=10.5, color=INK, justify=True, space_after=7, indent=None):
    p = doc.add_paragraph()
    _add_inline(p, text, size=size, color=color)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.15
    if justify:
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    if indent:
        p.paragraph_format.left_indent = Inches(indent)
    return p


def _heading(doc, text, level):
    sizes = {1: 16, 2: 12.5, 3: 11}
    colors = {1: ACCENT, 2: ACCENT, 3: INK}
    p = doc.add_paragraph(style=f"Heading {level}")
    p.paragraph_format.space_before = Pt(13 if level == 1 else 11)
    p.paragraph_format.space_after = Pt(9 if level == 1 else 5)
    r = p.add_run(text)
    r.font.name = HEAD_FONT
    r.font.size = Pt(sizes[level])
    r.bold = True
    r.font.color.rgb = colors[level]
    if level == 1:
        _border(p, "bottom")
    return p


def _bullet(doc, text, level=0):
    p = doc.add_paragraph(style="List Bullet" if level == 0 else "List Bullet 2")
    _add_inline(p, text)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.1
    return p


def _numbered(doc, num, text):
    """Número literal em vez de numeração automática, que acumula entre listas."""
    p = doc.add_paragraph()
    r = p.add_run(f"{num}.  ")
    r.font.name, r.font.size, r.bold, r.font.color.rgb = BODY_FONT, Pt(10.5), True, ACCENT
    _add_inline(p, text)
    p.paragraph_format.left_indent = Inches(0.28)
    p.paragraph_format.first_line_indent = Inches(-0.14)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.1
    return p


def _quote(doc, text):
    p = _para(doc, text, color=MUTED, indent=0.25)
    _border(p, "left", size=12, color=ACCENT_HEX, space=12)
    return p


def _tbl_borders(table, left_accent=None):
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    spec = {
        "top": (4, RULE_HEX), "bottom": (4, RULE_HEX),
        "left": (4, RULE_HEX), "right": (4, RULE_HEX),
        "insideH": (4, RULE_HEX), "insideV": (4, RULE_HEX),
    }
    if left_accent:
        spec["left"] = (18, left_accent)
    for edge, (size, color) in spec.items():
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color)
        borders.append(el)
    tblPr.append(borders)


def _no_split(table, repeat_header=True):
    """Evita que uma linha se parta entre páginas e repete o cabeçalho."""
    for ri, row in enumerate(table.rows):
        trPr = row._tr.get_or_add_trPr()
        cant = OxmlElement("w:cantSplit")
        trPr.append(cant)
        if ri == 0 and repeat_header:
            hdr = OxmlElement("w:tblHeader")
            trPr.append(hdr)


def _callout(doc, title, lines, color=MUTED):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _tbl_borders(table, left_accent="%s" % ("9A3412" if color is WARN else ACCENT_HEX))
    cell = table.cell(0, 0)
    _shade(cell, BOX_HEX)
    cell.paragraphs[0].text = ""

    p = cell.paragraphs[0]
    r = p.add_run(title)
    r.font.name, r.font.size, r.bold, r.font.color.rgb = HEAD_FONT, Pt(10.5), True, color
    p.paragraph_format.space_after = Pt(5)

    for line in lines:
        q = cell.add_paragraph()
        _add_inline(q, line, size=10)
        q.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        q.paragraph_format.space_after = Pt(4)
        q.paragraph_format.line_spacing = 1.1
    doc.add_paragraph().paragraph_format.space_after = Pt(6)
    return table


def _table(doc, rows, aligns):
    table = doc.add_table(rows=0, cols=len(rows[0]))
    _tbl_borders(table)
    for ri, cells in enumerate(rows):
        row = table.add_row()
        for ci, text in enumerate(cells):
            cell = row.cells[ci]
            cell.text = ""
            p = cell.paragraphs[0]
            _add_inline(
                p, text, size=8.5,
                color=RGBColor(0xFF, 0xFF, 0xFF) if ri == 0 else INK,
                bold=(ri == 0),
            )
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.05
            if ci < len(aligns) and aligns[ci] == "right":
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            _shade(cell, ACCENT_HEX if ri == 0 else (ZEBRA_HEX if ri % 2 == 0 else "FFFFFF"))
    _no_split(table)
    doc.add_paragraph().paragraph_format.space_after = Pt(6)
    return table


# ------------------------------------------------------------- parsing

def _split_sections(lines):
    sections, cur = {}, None
    for line in lines:
        m = re.match(r"^## (.+)$", line)
        if m and m.group(1) in TOPLEVEL:
            cur = m.group(1)
            sections[cur] = []
            continue
        if cur:
            sections[cur].append(line)
    return sections


def _render_block(doc, lines):
    i = 0
    while i < len(lines):
        line = lines[i]
        t = line.strip()

        if t in ("", "---"):
            i += 1
            continue

        # tabela
        if t.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            def cells(s):
                return [x.strip() for x in s.strip().strip("|").split("|")]
            header = cells(t)
            aligns = ["right" if s.endswith(":") and not s.startswith(":") else "left"
                      for s in cells(lines[i + 1])]
            rows = [header]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            _table(doc, rows, aligns)
            continue

        m = re.match(r"^#### (.+)$", t) or re.match(r"^### (.+)$", t)
        if m:
            _heading(doc, m.group(1), 3)
            i += 1
            continue
        m = re.match(r"^## (.+)$", t)
        if m:
            _heading(doc, m.group(1), 2)
            i += 1
            continue
        if re.match(r"^# (.+)$", t):   # redundante com o título da seção
            i += 1
            continue

        if t.startswith("> "):
            _quote(doc, t[2:])
            i += 1
            continue

        m = re.match(r"^[-*] (.+)$", t)
        if m:
            depth = len(line) - len(line.lstrip())
            _bullet(doc, m.group(1), 1 if depth >= 2 else 0)
            i += 1
            continue

        m = re.match(r"^(\d+)\. (.+)$", t)
        if m:
            _numbered(doc, m.group(1), m.group(2))
            i += 1
            continue

        _para(doc, t)
        i += 1


# --------------------------------------------------------------- montagem

def markdown_to_docx(md_text: str) -> bytes:
    lines = md_text.split("\n")

    meta = {}
    for line in lines[:12]:
        m = re.match(r"^- ([^:]+): (.+)$", line)
        if m:
            meta[m.group(1).strip()] = m.group(2).strip()

    ticker = "—"
    m = re.match(r"^# TradingAgents — (.+)$", lines[0]) if lines else None
    if m:
        ticker = m.group(1).strip()

    sections = _split_sections(lines)
    def _text_of(name):
        return " ".join(
            x.strip() for x in sections.get(name, [])
            if x.strip() and x.strip() != "---"
        )

    decision = _text_of("Decisão final")
    company = _text_of("Instrument context")
    company_name = ""
    cm = re.search(r"Company:\s*([^;]+);", company)
    if cm:
        company_name = cm.group(1).strip()

    doc = Document()

    # página e fonte base
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    for side in ("top", "bottom", "left", "right"):
        setattr(sec, f"{side}_margin", Inches(1))

    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = INK

    # cabeçalho e rodapé
    hdr = sec.header.paragraphs[0]
    hdr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    hr = hdr.add_run(f"{ticker} · Análise multiagente · {meta.get('Data da análise', '')}")
    hr.font.name, hr.font.size, hr.font.color.rgb = BODY_FONT, Pt(8), MUTED

    ftr = sec.footer.paragraphs[0]
    ftr.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _page_number_field(ftr)

    # ---------------- capa
    doc.add_paragraph().paragraph_format.space_after = Pt(70)

    p = doc.add_paragraph()
    r = p.add_run("RELATÓRIO DE ANÁLISE MULTIAGENTE")
    r.font.name, r.font.size, r.font.color.rgb = BODY_FONT, Pt(9.5), MUTED
    p.paragraph_format.space_after = Pt(8)

    p = doc.add_paragraph()
    r = p.add_run(ticker)
    r.font.name, r.font.size, r.bold, r.font.color.rgb = HEAD_FONT, Pt(34), True, ACCENT
    p.paragraph_format.space_after = Pt(3)

    if company_name:
        p = doc.add_paragraph()
        r = p.add_run(company_name)
        r.font.name, r.font.size, r.font.color.rgb = HEAD_FONT, Pt(13), INK
        p.paragraph_format.space_after = Pt(10)
        _border(p, "bottom", size=12, color=ACCENT_HEX, space=10)

    doc.add_paragraph().paragraph_format.space_after = Pt(18)

    rows = [
        ("Ativo", ticker),
        ("Data da análise", meta.get("Data da análise", "")),
        ("Gerado em", meta.get("Gerado em", "").replace("T", " às ")),
        ("Motor de análise", "TradingAgents (multiagente)"),
        ("Provedor / modelos", " · ".join(filter(None, [
            meta.get("Provedor", ""), meta.get("Modelo de raciocínio", ""),
            meta.get("Modelo rápido", ""),
        ]))),
        ("Benchmark de alfa", meta.get("Benchmark", "—")),
        ("Recomendação", decision or "—"),
    ]
    t = doc.add_table(rows=0, cols=2)
    for k, v in rows:
        row = t.add_row()
        row.cells[0].text = ""
        row.cells[1].text = ""
        pk = row.cells[0].paragraphs[0]
        rk = pk.add_run(k)
        rk.font.name, rk.font.size, rk.font.color.rgb = BODY_FONT, Pt(9.5), MUTED
        _add_inline(row.cells[1].paragraphs[0], v, size=10)
        row.cells[0].width = Inches(1.8)
        row.cells[1].width = Inches(4.7)
    for row in t.rows:
        for cell in row.cells:
            cell.paragraphs[0].paragraph_format.space_after = Pt(5)

    doc.add_paragraph().paragraph_format.space_after = Pt(30)

    _callout(doc, "Natureza deste documento", [
        "Relatório gerado por um sistema experimental de agentes de linguagem (TradingAgents, "
        "Tauric Research). Não constitui recomendação de investimento nem substitui avaliação "
        "profissional.",
        "O conteúdo reflete dados de mercado obtidos na data indicada e o raciocínio dos modelos "
        "empregados. Execuções repetidas podem produzir conclusões distintas.",
    ])

    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ---------------- sumário
    _heading(doc, "Sumário", 1)
    for key, title in SECTION_TITLES:
        if key not in sections:
            continue
        p = doc.add_paragraph()
        r = p.add_run(title)
        r.font.name, r.font.size, r.bold, r.font.color.rgb = HEAD_FONT, Pt(11), True, ACCENT
        p.paragraph_format.space_before = Pt(7)
        p.paragraph_format.space_after = Pt(1)

    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ---------------- seções
    present = [(k, v) for k, v in SECTION_TITLES if k in sections]
    for idx, (key, title) in enumerate(present):
        _heading(doc, title, 1)
        _render_block(doc, sections[key])
        if idx < len(present) - 1:
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


if __name__ == "__main__":
    import sys
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, encoding="utf-8") as fh:
        data = markdown_to_docx(fh.read())
    with open(dst, "wb") as fh:
        fh.write(data)
    print("ok", dst, len(data))
