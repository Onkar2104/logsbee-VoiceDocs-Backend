from html.parser import HTMLParser
from io import BytesIO
from html import escape

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches


class _HtmlToDocx(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.document = Document()
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
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li"):
            if self.parts:
                self._flush()
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


def html_to_docx(content: str) -> bytes:
    parser = _HtmlToDocx()
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
