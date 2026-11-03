"""Exporta o relatório Markdown para PDF e DOCX, incluindo os três programas."""
import os
import re
import textwrap
from pathlib import Path
from xml.sax.saxutils import escape

from docx import Document
from docx.shared import Cm, Pt
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    LongTable, PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer, TableStyle,
)

RAIZ = Path(__file__).resolve().parent


def blocos(texto):
    """Lê o subconjunto Markdown usado pelo relatório: títulos, tabelas e código."""
    linhas = texto.splitlines()
    i = 0
    while i < len(linhas):
        linha = linhas[i]
        if not linha.strip():
            i += 1
            continue
        if linha.startswith("```"):
            codigo = []
            i += 1
            while i < len(linhas) and not linhas[i].startswith("```"):
                codigo.append(linhas[i])
                i += 1
            yield "codigo", "\n".join(codigo)
        elif linha.startswith("|"):
            tabela = []
            while i < len(linhas) and linhas[i].startswith("|"):
                colunas = [c.strip() for c in linhas[i].strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in colunas):
                    tabela.append(colunas)
                i += 1
            yield "tabela", tabela
            continue
        elif linha.startswith("#"):
            nivel = len(linha) - len(linha.lstrip("#"))
            yield "titulo", (nivel, linha[nivel:].strip())
        elif linha.startswith("- "):
            yield "item", linha[2:]
        else:
            partes = [linha]
            i += 1
            while i < len(linhas) and linhas[i].strip() and not linhas[i].startswith(("#", "|", "```", "- ")):
                partes.append(linhas[i])
                i += 1
            yield "paragrafo", " ".join(partes)
            continue
        i += 1


def simples(texto):
    return texto.replace("`", "").replace("**", "")


def fontes_pdf():
    windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    candidatos = [
        (windows / "calibri.ttf", windows / "calibrib.ttf", windows / "consola.ttf"),
        (windows / "arial.ttf", windows / "arialbd.ttf", windows / "consola.ttf"),
        tuple(Path("/usr/share/fonts/truetype/dejavu") / p for p in
              ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSansMono.ttf")),
    ]
    for normal, negrito, mono in candidatos:
        if all(p.exists() for p in (normal, negrito, mono)):
            for nome, caminho in (("Texto", normal), ("TextoBold", negrito), ("Codigo", mono)):
                pdfmetrics.registerFont(TTFont(nome, str(caminho)))
            return "Texto", "TextoBold", "Codigo"
    return "Helvetica", "Helvetica-Bold", "Courier"


def exportar_pdf(conteudo):
    normal, negrito, mono = fontes_pdf()
    corpo = ParagraphStyle("Corpo", fontName=normal, fontSize=10, leading=15,
                           spaceAfter=9, alignment=TA_JUSTIFY)
    celula = ParagraphStyle("Celula", parent=corpo, fontSize=8, leading=11, alignment=0)
    titulo = ParagraphStyle("Titulo", fontName=negrito, fontSize=20, leading=25, spaceAfter=20)
    secao = ParagraphStyle("Secao", fontName=negrito, fontSize=13, leading=18,
                          spaceBefore=13, spaceAfter=9, keepWithNext=True)
    codigo = ParagraphStyle("Codigo", fontName=mono, fontSize=7, leading=9, spaceAfter=8)
    historia = []
    for tipo, valor in conteudo:
        if tipo == "quebra":
            historia.append(PageBreak())
        elif tipo == "titulo":
            nivel, texto = valor
            historia.append(Paragraph(escape(texto), titulo if nivel == 1 else secao))
        elif tipo == "tabela":
            linhas = [[Paragraph(escape(simples(c)), celula) for c in r] for r in valor]
            tabela = LongTable(linhas, colWidths=[(A4[0] - 100) / len(valor[0])] * len(valor[0]), repeatRows=1)
            tabela.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7edf3")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c0c9d2")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            historia.extend([tabela, Spacer(1, 10)])
        elif tipo == "codigo":
            # Mantém a apresentação dentro das margens; os fontes executáveis são entregues separados.
            linhas = []
            for linha in valor.splitlines():
                linhas.extend(textwrap.wrap(linha.expandtabs(4), width=110, replace_whitespace=False,
                                             drop_whitespace=False, subsequent_indent="    ") or [""])
            historia.append(Preformatted("\n".join(linhas), codigo))
        else:
            texto = ("• " if tipo == "item" else "") + simples(valor)
            historia.append(Paragraph(escape(texto), corpo))

    def rodape(canvas, documento):
        canvas.setFont(normal, 8)
        canvas.drawString(50, 25, "Qualidade do ar | MongoDB + Redis + Python | Etapa I")
        canvas.drawRightString(A4[0] - 50, 25, str(documento.page))

    pdf = SimpleDocTemplate(str(RAIZ / "RELATORIO_TECNICO.pdf"), pagesize=A4,
                            leftMargin=50, rightMargin=50, topMargin=45, bottomMargin=45,
                            title="Integração MongoDB + Redis com Python — Etapa I")
    pdf.build(historia, onFirstPage=rodape, onLaterPages=rodape)


def exportar_docx(conteudo):
    documento = Document()
    secao = documento.sections[0]
    secao.top_margin = secao.bottom_margin = Cm(2)
    secao.left_margin = secao.right_margin = Cm(2)
    estilo = documento.styles["Normal"]
    estilo.font.name = "Calibri"
    estilo.font.size = Pt(10)
    estilo.paragraph_format.space_after = Pt(7)
    for tipo, valor in conteudo:
        if tipo == "quebra":
            documento.add_page_break()
        elif tipo == "titulo":
            nivel, texto = valor
            documento.add_heading(texto, level=0 if nivel == 1 else min(nivel - 1, 3))
        elif tipo == "tabela":
            tabela = documento.add_table(rows=0, cols=len(valor[0]))
            tabela.style = "Table Grid"
            for linha in valor:
                celulas = tabela.add_row().cells
                for celula, texto in zip(celulas, linha):
                    celula.text = simples(texto)
        elif tipo == "codigo":
            paragrafo = documento.add_paragraph()
            paragrafo.paragraph_format.space_after = Pt(5)
            paragrafo.paragraph_format.line_spacing = 1
            fonte = paragrafo.add_run(valor).font
            fonte.name = "Consolas"
            fonte.size = Pt(7)
        else:
            documento.add_paragraph(simples(valor), style="List Bullet" if tipo == "item" else None)
    secao.footer.paragraphs[0].text = "Qualidade do ar — MongoDB + Redis + Python — Etapa I"
    documento.save(RAIZ / "RELATORIO_TECNICO.docx")


def main():
    conteudo = list(blocos((RAIZ / "RELATORIO_TECNICO.md").read_text(encoding="utf-8-sig")))
    for arquivo in ("mongodb.py", "agregacoes.py", "main.py"):
        conteudo.extend([
            ("quebra", None), ("titulo", (2, f"Código-fonte integral — {arquivo}")),
            ("codigo", (RAIZ / arquivo).read_text(encoding="utf-8-sig")),
        ])
    exportar_pdf(conteudo)
    exportar_docx(conteudo)
    print("Gerados RELATORIO_TECNICO.pdf e RELATORIO_TECNICO.docx com código-fonte em apêndice.")


if __name__ == "__main__":
    main()
