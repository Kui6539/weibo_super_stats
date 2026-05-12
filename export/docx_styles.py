from __future__ import annotations

from typing import Any

from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor


def setup_document_styles(document) -> None:
    normal = document.styles["Normal"]
    normal.font.name = "Microsoft YaHei"
    normal.font.size = Pt(11)
    _set_east_asia_font(normal, "Microsoft YaHei")


def add_heading(document, text: str, level: int = 1):
    paragraph = document.add_paragraph()
    if level == 1:
        paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run = paragraph.add_run(str(text))
    run.bold = True
    run.font.name = "Microsoft YaHei"
    run.font.size = Pt(26 if level == 1 else 13 if level == 2 else 11)
    run.font.color.rgb = RGBColor(33, 37, 41)
    _set_run_east_asia_font(run, "Microsoft YaHei")
    return paragraph


def add_paragraph_text(document, text: str, size: int = 11, bold: bool = False, color: tuple[int, int, int] | None = None):
    paragraph = document.add_paragraph()
    run = paragraph.add_run()
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = "Microsoft YaHei"
    if color:
        run.font.color.rgb = RGBColor(*color)
    _set_run_east_asia_font(run, "Microsoft YaHei")
    _add_preserved_text(run, str(text or ""))
    return paragraph


def add_hyperlink(paragraph, text: str, url: str):
    rel_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), rel_id)
    run = paragraph.add_run(str(text))
    run.font.color.rgb = RGBColor(0, 102, 204)
    run.font.underline = True
    run.font.name = "Microsoft YaHei"
    run.font.size = Pt(10)
    _set_run_east_asia_font(run, "Microsoft YaHei")
    hyperlink.append(run._r)
    paragraph._p.append(hyperlink)
    return run


def _add_preserved_text(run, text: str) -> None:
    for idx, part in enumerate(str(text or "").splitlines() or [""]):
        if idx > 0:
            run.add_break()
        if part:
            run.add_text(part)


def _set_east_asia_font(style: Any, font_name: str) -> None:
    style._element.rPr.rFonts.set(qn("w:eastAsia"), font_name)


def _set_run_east_asia_font(run: Any, font_name: str) -> None:
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font_name)
