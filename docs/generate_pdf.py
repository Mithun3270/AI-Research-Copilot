import html
import re
import textwrap
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
)
from reportlab.platypus.tableofcontents import TableOfContents


CONTENT_PATH = Path(__file__).resolve().parent / "PROJECT_CONTENT.md"
OUTPUT_PATH = Path(__file__).resolve().parent / "AI_Research_Copilot_Documentation.pdf"
PAGE_WIDTH, PAGE_HEIGHT = letter
LEFT_MARGIN = 0.68 * inch
RIGHT_MARGIN = 0.68 * inch
TOP_MARGIN = 0.72 * inch
BOTTOM_MARGIN = 0.65 * inch


def inline_markup(value):
    escaped = html.escape(value, quote=False)
    escaped = re.sub(r"`([^`]+)`", r'<font name="Courier" color="#155e75">\1</font>', escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", escaped)
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda match: f'<link href="{html.escape(match.group(2), quote=True)}" color="#2563eb">{match.group(1)}</link>',
        escaped,
    )
    return escaped


def split_table_row(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def table_widths(header, available_width):
    names = " ".join(header).casefold()
    if "technology" in names and "where used" in names:
        weights = [0.9, 0.65, 1.45, 1.75]
    elif "model" in names and "purpose" in names:
        weights = [1.1, 1.4, 2.3]
    elif "method" in names and "endpoint" in names:
        weights = [0.62, 1.85, 2.5]
    elif "path" in names and "contents" in names:
        weights = [1.75, 4.25]
    elif "setting" in names and "default" in names:
        weights = [1.35, 1.75, 2.9]
    else:
        weights = [1] * len(header)
    if len(weights) != len(header):
        weights = [1] * len(header)
    total = sum(weights)
    return [available_width * weight / total for weight in weights]


class ArchitectureDiagram(Flowable):
    def __init__(self, source, available_width):
        super().__init__()
        self.available_width = available_width
        self.direction = "TB"
        self.labels = {}
        self.edges = []
        self._parse(source)
        self.node_layers = self._layers()
        self.box_width = 88
        self.box_height = 46
        self.gap = 18
        self._layout()

    def _parse(self, source):
        for line in source.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("flowchart "):
                self.direction = line.split(None, 1)[1].upper()
                continue
            for node_id, label in re.findall(r'([A-Za-z]\w*)\s*\["([^"]+)"\]', line):
                self.labels[node_id] = label.replace("<br/>", "\n").replace("<br>", "\n")
            edge_matches = re.findall(
                r"([A-Za-z]\w*)\s*-->\s*(?:\|([^|]*)\|\s*)?([A-Za-z]\w*)",
                line,
            )
            self.edges.extend(edge_matches)
        for source_id, edge_label, target_id in self.edges:
            self.labels.setdefault(source_id, source_id)
            self.labels.setdefault(target_id, target_id)
        if not self.labels:
            self.labels["A"] = "Diagram not available"

    def _layers(self):
        incoming = {node: 0 for node in self.labels}
        outgoing = {node: [] for node in self.labels}
        for source_id, _, target_id in self.edges:
            outgoing[source_id].append(target_id)
            incoming[target_id] += 1
        ready = [node for node in self.labels if incoming[node] == 0]
        layers = {node: 0 for node in ready}
        visited = 0
        while ready:
            node = ready.pop(0)
            visited += 1
            for target_id in outgoing[node]:
                layers[target_id] = max(layers.get(target_id, 0), layers[node] + 1)
                incoming[target_id] -= 1
                if incoming[target_id] == 0:
                    ready.append(target_id)
        if visited != len(self.labels):
            return {node: index for index, node in enumerate(self.labels)}
        return layers

    def _layout(self):
        grouped = {}
        for node, layer in self.node_layers.items():
            grouped.setdefault(layer, []).append(node)
        self.grouped = grouped
        if self.direction == "LR":
            columns = max(1, len(grouped))
            self.box_width = min(112, (self.available_width - (columns - 1) * 12) / columns)
            self.box_height = 52
            self.gap = 18
            self.width = self.available_width
            self.height = max(len(nodes) for nodes in grouped.values()) * (self.box_height + self.gap)
        else:
            rows = max(1, len(grouped))
            max_nodes = max(len(nodes) for nodes in grouped.values())
            self.box_width = min(250, (self.available_width - (max_nodes - 1) * 14) / max_nodes)
            self.box_height = 44
            self.gap = 18
            self.width = self.available_width
            self.height = rows * (self.box_height + self.gap) - self.gap

    def wrap(self, available_width, available_height):
        return self.width, self.height

    def _positions(self):
        positions = {}
        if self.direction == "LR":
            columns = max(1, len(self.grouped))
            column_width = self.available_width / columns
            for column, (_, nodes) in enumerate(sorted(self.grouped.items())):
                group_height = len(nodes) * (self.box_height + self.gap) - self.gap
                top = (self.height + group_height) / 2 - self.box_height
                for index, node in enumerate(nodes):
                    x = column * column_width + (column_width - self.box_width) / 2
                    y = top - index * (self.box_height + self.gap)
                    positions[node] = (x, y, self.box_width, self.box_height)
        else:
            row_height = self.box_height + self.gap
            for row, (_, nodes) in enumerate(sorted(self.grouped.items())):
                row_width = len(nodes) * self.box_width + (len(nodes) - 1) * 14
                start_x = (self.available_width - row_width) / 2
                y = self.height - (row + 1) * row_height + self.gap
                for index, node in enumerate(nodes):
                    positions[node] = (
                        start_x + index * (self.box_width + 14),
                        y,
                        self.box_width,
                        self.box_height,
                    )
        return positions

    def draw(self):
        canvas = self.canv
        positions = self._positions()
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#64748b"))
        canvas.setLineWidth(1.1)
        for source_id, edge_label, target_id in self.edges:
            if source_id not in positions or target_id not in positions:
                continue
            sx, sy, sw, sh = positions[source_id]
            tx, ty, tw, th = positions[target_id]
            if self.direction == "LR":
                start = (sx + sw, sy + sh / 2)
                end = (tx, ty + th / 2)
                points = [(start[0], start[1]), (end[0] - 6, end[1])]
                label_x = (start[0] + end[0]) / 2
                label_y = (start[1] + end[1]) / 2 + 6
            else:
                start = (sx + sw / 2, sy)
                end = (tx + tw / 2, ty + th)
                points = [(start[0], start[1]), (end[0], end[1] + 6)]
                label_x = (start[0] + end[0]) / 2
                label_y = (start[1] + end[1]) / 2
            canvas.line(points[0][0], points[0][1], points[1][0], points[1][1])
            if self.direction == "LR":
                canvas.line(points[1][0], points[1][1], points[1][0] - 4, points[1][1] - 3)
                canvas.line(points[1][0], points[1][1], points[1][0] - 4, points[1][1] + 3)
            else:
                canvas.line(points[1][0], points[1][1], points[1][0] - 3, points[1][1] + 4)
                canvas.line(points[1][0], points[1][1], points[1][0] + 3, points[1][1] + 4)
            if edge_label:
                canvas.setFont("Helvetica", 6.5)
                canvas.setFillColor(colors.HexColor("#475569"))
                canvas.drawCentredString(label_x, label_y, edge_label[:24])
        for node, (x, y, width, height) in positions.items():
            canvas.setFillColor(colors.HexColor("#eff6ff"))
            canvas.setStrokeColor(colors.HexColor("#3b82f6"))
            canvas.roundRect(x, y, width, height, 7, fill=1, stroke=1)
            canvas.setFillColor(colors.HexColor("#0f172a"))
            canvas.setFont("Helvetica", 7.4)
            label = self.labels[node].replace("\n", " ")
            lines = textwrap.wrap(label, width=max(10, int(width / 4.2))) or [label]
            lines = lines[:4]
            line_height = 9
            start_y = y + height / 2 + (len(lines) - 1) * line_height / 2 - 2
            for index, line in enumerate(lines):
                canvas.drawCentredString(x + width / 2, start_y - index * line_height, line)
        canvas.restoreState()


class ProjectDocTemplate(BaseDocTemplate):
    def __init__(self, filename):
        super().__init__(
            filename,
            pagesize=letter,
            leftMargin=LEFT_MARGIN,
            rightMargin=RIGHT_MARGIN,
            topMargin=TOP_MARGIN,
            bottomMargin=BOTTOM_MARGIN,
            title="AI Research Copilot Documentation",
            author="AI Research Copilot",
        )
        frame = Frame(
            LEFT_MARGIN,
            BOTTOM_MARGIN,
            PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN,
            PAGE_HEIGHT - TOP_MARGIN - BOTTOM_MARGIN,
            id="main",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        self.addPageTemplates(PageTemplate(id="main", frames=frame, onPage=self._draw_page))
        self.heading_index = 0

    def beforeDocument(self):
        self.heading_index = 0

    def _draw_page(self, canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#dbe3ef"))
        canvas.line(LEFT_MARGIN, 0.48 * inch, PAGE_WIDTH - RIGHT_MARGIN, 0.48 * inch)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(LEFT_MARGIN, 0.31 * inch, "AI Research Copilot | Project Documentation")
        canvas.drawRightString(PAGE_WIDTH - RIGHT_MARGIN, 0.31 * inch, f"Page {document.page}")
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if not isinstance(flowable, Paragraph):
            return
        style_name = flowable.style.name
        levels = {"SectionHeading": 0, "SubsectionHeading": 1}
        if style_name not in levels:
            return
        self.heading_index += 1
        key = f"section-{self.heading_index}"
        title = flowable.getPlainText()
        level = levels[style_name]
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(title, key, level=level, closed=False)
        self.notify("TOCEntry", (level, title, self.page, key))


def make_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="CoverTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=27,
        leading=32,
        textColor=colors.HexColor("#10243e"),
        alignment=TA_CENTER,
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name="CoverSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=12,
        leading=18,
        textColor=colors.HexColor("#475569"),
        alignment=TA_CENTER,
        spaceAfter=25,
    ))
    styles.add(ParagraphStyle(
        name="SectionHeading",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=23,
        textColor=colors.HexColor("#12345a"),
        spaceBefore=15,
        spaceAfter=9,
        keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        name="TOCTitleProject",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=23,
        textColor=colors.HexColor("#12345a"),
        spaceBefore=15,
        spaceAfter=9,
        keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        name="SubsectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1d4ed8"),
        spaceBefore=11,
        spaceAfter=6,
        keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        name="SubsubsectionHeading",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#334155"),
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        name="BodyProject",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#263449"),
        spaceAfter=7,
        alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        name="ListProject",
        parent=styles["BodyProject"],
        leftIndent=15,
        firstLineIndent=-8,
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name="TableCellProject",
        parent=styles["BodyProject"],
        fontSize=7.4,
        leading=9.5,
        spaceAfter=0,
    ))
    styles.add(ParagraphStyle(
        name="TableHeaderProject",
        parent=styles["TableCellProject"],
        fontName="Helvetica-Bold",
        textColor=colors.white,
    ))
    styles.add(ParagraphStyle(
        name="CaptionProject",
        parent=styles["BodyProject"],
        fontName="Helvetica-Oblique",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#475569"),
        spaceBefore=4,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="CodeBlockProject",
        fontName="Courier",
        fontSize=7.1,
        leading=9.2,
        textColor=colors.HexColor("#0f172a"),
        backColor=colors.HexColor("#f1f5f9"),
        borderColor=colors.HexColor("#cbd5e1"),
        borderWidth=0.5,
        borderPadding=6,
        leftIndent=5,
        rightIndent=5,
        spaceBefore=4,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="TOCLevel0Project",
        fontName="Helvetica-Bold",
        fontSize=9.3,
        leading=14,
        leftIndent=0,
        firstLineIndent=0,
        textColor=colors.HexColor("#12345a"),
        spaceBefore=4,
    ))
    styles.add(ParagraphStyle(
        name="TOCLevel1Project",
        fontName="Helvetica",
        fontSize=8.2,
        leading=11,
        leftIndent=16,
        firstLineIndent=0,
        textColor=colors.HexColor("#475569"),
    ))
    return styles


def build_table(rows, styles, available_width):
    if not rows:
        return Spacer(1, 1)
    header = rows[0]
    widths = table_widths(header, available_width)
    data = []
    for row_index, row in enumerate(rows):
        cells = []
        for value in row[:len(header)]:
            style_name = "TableHeaderProject" if row_index == 0 else "TableCellProject"
            cells.append(Paragraph(inline_markup(value), styles[style_name]))
        if len(cells) < len(header):
            cells.extend(
                Paragraph("", styles["TableCellProject"])
                for _ in range(len(header) - len(cells))
            )
        data.append(cells)
    table = Table(
        data,
        colWidths=widths,
        repeatRows=1,
        hAlign="LEFT",
        splitByRow=1,
        splitInRow=1,
    )
    table.setStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173b65")),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ])
    return table


def parse_markdown(content, styles, available_width):
    lines = content.splitlines()
    story = []
    index = 0
    in_cover = True
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line == "[[TOC]]":
            toc = TableOfContents()
            toc.levelStyles = [styles["TOCLevel0Project"], styles["TOCLevel1Project"]]
            story.append(toc)
            story.append(PageBreak())
            in_cover = False
            index += 1
            continue
        if line.startswith("```diagram"):
            index += 1
            diagram_lines = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                diagram_lines.append(lines[index])
                index += 1
            story.append(ArchitectureDiagram("\n".join(diagram_lines), available_width))
            story.append(Spacer(1, 8))
            index += 1
            continue
        if line.startswith("```"):
            index += 1
            code_lines = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            story.append(Preformatted("\n".join(code_lines), styles["CodeBlockProject"], maxLineLength=96))
            story.append(Spacer(1, 4))
            index += 1
            continue
        if line.startswith("|") and index + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{3,}", lines[index + 1]):
            rows = [split_table_row(line)]
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(split_table_row(lines[index]))
                index += 1
            story.append(build_table(rows, styles, available_width))
            story.append(Spacer(1, 7))
            continue
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            title = line[level:].strip()
            if level == 1:
                story.append(Spacer(1, 0.6 * inch))
                story.append(Paragraph(inline_markup(title), styles["CoverTitle"]))
                story.append(Paragraph("PROJECT DOCUMENTATION", styles["CoverSubtitle"]))
                story.append(Spacer(1, 0.25 * inch))
            elif level == 2:
                heading_style = styles["TOCTitleProject"] if title.casefold() == "table of contents" else styles["SectionHeading"]
                story.append(Paragraph(inline_markup(title), heading_style))
            else:
                story.append(Paragraph(inline_markup(title), styles["SubsectionHeading"] if level == 3 else styles["SubsubsectionHeading"]))
            index += 1
            continue
        if line.startswith("**") and line.endswith("**"):
            story.append(Paragraph(inline_markup(line), styles["CaptionProject"]))
            index += 1
            continue
        if line.startswith("|"):
            index += 1
            continue
        if re.match(r"^[-*]\s+", line) or re.match(r"^\d+[.)]\s+", line):
            ordered = bool(re.match(r"^\d+[.)]\s+", line))
            items = []
            while index < len(lines):
                item_line = lines[index].strip()
                match = re.match(r"^(?:[-*]|\d+[.)])\s+(.*)$", item_line)
                if not match or bool(re.match(r"^\d+[.)]\s+", item_line)) != ordered:
                    break
                bullet = "bullet" if not ordered else "1"
                items.append(ListItem(Paragraph(inline_markup(match.group(1)), styles["ListProject"])))
                index += 1
            story.append(ListFlowable(
                items,
                bulletType="1" if ordered else "bullet",
                start="1",
                leftIndent=17,
                bulletFontName="Helvetica",
                bulletFontSize=7.5,
                bulletColor=colors.HexColor("#2563eb"),
                spaceAfter=6,
            ))
            continue
        paragraph_lines = [line]
        index += 1
        while index < len(lines):
            next_line = lines[index].strip()
            if (
                not next_line
                or next_line.startswith("#")
                or next_line.startswith("```")
                or next_line == "[[TOC]]"
                or next_line.startswith("|")
                or next_line.startswith("**")
                or re.match(r"^[-*]\s+|^\d+[.)]\s+", next_line)
            ):
                break
            paragraph_lines.append(next_line)
            index += 1
        markup = "<br/>".join(inline_markup(part) for part in paragraph_lines)
        style = styles["CoverSubtitle"] if in_cover else styles["BodyProject"]
        story.append(Paragraph(markup, style))
    return story


def main():
    if not CONTENT_PATH.is_file():
        raise FileNotFoundError(f"Documentation source is missing: {CONTENT_PATH}")
    content = CONTENT_PATH.read_text(encoding="utf-8")
    styles = make_styles()
    available_width = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN
    story = parse_markdown(content, styles, available_width)
    document = ProjectDocTemplate(str(OUTPUT_PATH))
    document.multiBuild(story, maxPasses=5)
    print(f"Documentation PDF created: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
