from html.parser import HTMLParser
import base64
import binascii
from io import BytesIO
from html import escape

from PIL import Image

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt


class _HtmlToDocx(HTMLParser):
    def __init__(self, legal_mode: bool = False):
        super().__init__(convert_charrefs=True)
        self.document = Document()
        self.legal_mode = legal_mode
        if legal_mode:
            section = self.document.sections[0]
            section.top_margin = Inches(1)
            section.bottom_margin = Inches(1)
            section.left_margin = Inches(1.25)
            section.right_margin = Inches(1)
            normal = self.document.styles["Normal"]
            normal.font.name = "Times New Roman"
            normal.font.size = Pt(12)
            normal.paragraph_format.line_spacing = 1.5
            normal.paragraph_format.space_after = Pt(6)
        self.parts = []
        self.bold = self.italic = self.underline = False
        self.list_stack = []

    def _flush(self, tag="p"):
        text = "".join(part[0] for part in self.parts)
        if text.strip():
            style = "List Bullet" if self.list_stack and self.list_stack[-1] == "ul" else (
                "List Number" if self.list_stack else None
            )
            paragraph = self.document.add_paragraph(style=style)
            for value, bold, italic, underline in self.parts:
                run = paragraph.add_run(value)
                run.bold, run.italic, run.underline = bold, italic, underline
            if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                paragraph.style = f"Heading {min(int(tag[1]), 3)}"
            if self.legal_mode:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if tag == "h1" else WD_ALIGN_PARAGRAPH.LEFT
                    paragraph.paragraph_format.keep_with_next = True
                    for run in paragraph.runs:
                        run.font.name = "Times New Roman"
                        run.bold = True
                        run.font.size = Pt(14 if tag == "h1" else 12)
                else:
                    for run in paragraph.runs:
                        run.font.name = "Times New Roman"
                        run.font.size = Pt(12)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li"):
            if self.parts:
                self._flush()
        elif tag == "img":
            source = dict(attrs).get("src", "")
            try:
                header, encoded = source.split(",", 1)
                if header not in {"data:image/png;base64", "data:image/jpeg;base64", "data:image/webp;base64"}:
                    return
                raw = base64.b64decode(encoded, validate=True)
                if not raw or len(raw) > 1024 * 1024:
                    return
                with Image.open(BytesIO(raw)) as image:
                    if image.format not in {"PNG", "JPEG", "WEBP"}:
                        return
                    image.load()
                    mode = "RGBA" if "A" in image.getbands() else "RGB"
                    converted = BytesIO()
                    image.convert(mode).save(converted, format="PNG")
                if self.parts:
                    self._flush()
                self.document.add_picture(BytesIO(converted.getvalue()), width=Inches(5.8))
            except (ValueError, binascii.Error, OSError, SyntaxError):
                return
        elif tag == "br":
            self.parts.append(("\n", self.bold, self.italic, self.underline))
        elif tag in ("ul", "ol"):
            self.list_stack.append(tag)
        elif tag in ("strong", "b"):
            self.bold = True
        elif tag in ("em", "i"):
            self.italic = True
        elif tag == "u":
            self.underline = True

    def handle_endtag(self, tag):
        if tag in ("p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush(tag)
        elif tag in ("ul", "ol") and self.list_stack:
            self.list_stack.pop()
        elif tag in ("strong", "b"):
            self.bold = False
        elif tag in ("em", "i"):
            self.italic = False
        elif tag == "u":
            self.underline = False

    def handle_data(self, data):
        if data:
            self.parts.append((data, self.bold, self.italic, self.underline))


def html_to_docx(content: str, legal_mode: bool = False) -> bytes:
    parser = _HtmlToDocx(legal_mode=legal_mode)
    parser.feed(content or "")
    parser.close()
    if parser.parts:
        parser._flush()
    if not parser.document.paragraphs:
        parser.document.add_paragraph("")
    output = BytesIO()
    parser.document.save(output)
    return output.getvalue()


def docx_to_html(data: bytes) -> str:
    document = Document(BytesIO(data))
    chunks = []
    for paragraph in document.paragraphs:
        style = paragraph.style.name if paragraph.style else ""
        if style.startswith("Heading "):
            try:
                level = max(1, min(6, int(style.split()[-1])))
            except ValueError:
                level = 2
            tag = f"h{level}"
        elif style == "List Bullet":
            tag = "li"
        elif style == "List Number":
            tag = "li"
        else:
            tag = "p"
        runs = []
        for run in paragraph.runs:
            value = escape(run.text).replace("\\n", "<br>")
            if run.bold:
                value = f"<strong>{value}</strong>"
            if run.italic:
                value = f"<em>{value}</em>"
            if run.underline:
                value = f"<u>{value}</u>"
            runs.append(value)
        chunks.append(f"<{tag}>{''.join(runs)}</{tag}>")
    return "".join(chunks)
