"""Visible HTML data segments retain exact offsets into untouched input strings."""
from html.parser import HTMLParser
from html import unescape


class VisibleText(HTMLParser):
    def __init__(self, source: str):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.starts = [0] + [i + 1 for i, char in enumerate(source) if char == "\n"]
        self.hidden: list[str] = []
        self.segments: list[tuple[int, str]] = []
        self.parts: list[tuple[str, list]] = []

    def boundary(self):
        self.parts.append(("\n", [None]))

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "template"}:
            self.boundary()
            self.hidden.append(tag)
        elif not self.hidden and tag in {"p", "br", "div", "li", "tr", "h1", "h2", "h3"}:
            self.boundary()

    def handle_endtag(self, tag):
        if self.hidden and tag == self.hidden[-1]:
            self.hidden.pop()
            self.boundary()
        elif not self.hidden and tag in {"p", "div", "li", "tr", "h1", "h2", "h3"}:
            self.boundary()

    def handle_data(self, data):
        if not self.hidden and data:
            line, column = self.getpos()
            start = self.starts[line - 1] + column
            self.segments.append((start, data))
            self.parts.append((data, [(start + i, start + i + 1) for i in range(len(data))]))

    def entity(self, source):
        if not self.hidden:
            line, column = self.getpos()
            start = self.starts[line - 1] + column
            if not self.source[start:].startswith(source):
                source = source.rstrip(";")
            decoded = unescape(source)
            self.parts.append((decoded, [(start, start + len(source))] * len(decoded)))

    def handle_entityref(self, name):
        self.entity("&" + name + ";")

    def handle_charref(self, name):
        self.entity("&#" + name + ";")


def segments(source: str):
    parser = VisibleText(source)
    parser.feed(source)
    parser.close()
    yield from parser.segments


def visible_view(source: str):
    parser = VisibleText(source)
    parser.feed(source)
    parser.close()
    return "".join(text for text, _ in parser.parts), [pos for _, positions in parser.parts for pos in positions]
