"""Markdown helpers: value escaping, Markdown -> HTML, HTML -> plain text.

Supported Markdown subset (the contract every channel renderer builds on):
headings, paragraphs, bold, italic, inline code, links, bullet/numbered lists,
blockquotes, horizontal rules. Anything fancier may be rendered differently
(or not at all) depending on the channel.
"""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser

import markdown as _markdown

# Characters Python-Markdown treats as backslash-escapable.
_MD_ESCAPABLE = set("\\`*_{}[]()#+-.!")


def escape_for_html_markdown(value) -> str:
    """Make a *value* inert before it is spliced into Markdown that becomes HTML.

    Stops values from injecting HTML tags or Markdown structure (headings,
    links, lists...). Newlines inside a value become <br>.
    """
    out = []
    for ch in str(value):
        if ch in "&<>\"'":
            out.append(html.escape(ch, quote=True))
        elif ch in _MD_ESCAPABLE:
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("<br>")
        elif ch == "\r":
            continue
        else:
            out.append(ch)
    return "".join(out)


def markdown_to_html(text: str) -> str:
    return _markdown.markdown(text, extensions=["sane_lists"], output_format="html")


class _TextExtractor(HTMLParser):
    _BLOCKS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
               "ul", "ol", "blockquote", "pre", "table"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []
        self._lists: list[list] = []  # ["ul"] or ["ol", counter]
        self._link: list | None = None  # [href, start index in _out]

    def _break(self, n: int) -> None:
        current = "".join(self._out)
        if not current:
            return
        trailing = len(current) - len(current.rstrip("\n"))
        self._out.append("\n" * max(0, n - trailing))

    def handle_starttag(self, tag, attrs):
        if tag in ("ul", "ol"):
            self._break(2 if not self._lists else 1)
            self._lists.append([tag, 0])
        elif tag in self._BLOCKS:
            self._break(2)
        elif tag == "li":
            self._break(1)
            indent = "  " * max(0, len(self._lists) - 1)
            if self._lists and self._lists[-1][0] == "ol":
                self._lists[-1][1] += 1
                self._out.append(f"{indent}{self._lists[-1][1]}. ")
            else:
                self._out.append(f"{indent}- ")
        elif tag == "br":
            self._out.append("\n")
        elif tag == "hr":
            self._break(2)
            self._out.append("---")
            self._break(2)
        elif tag == "a":
            self._link = [dict(attrs).get("href"), len(self._out)]

    def handle_endtag(self, tag):
        if tag in ("ul", "ol"):
            if self._lists:
                self._lists.pop()
            self._break(2 if not self._lists else 1)
        elif tag in self._BLOCKS:
            self._break(2)
        elif tag == "a" and self._link:
            href, start = self._link
            label = "".join(self._out[start:])
            if href and href != label and href != "mailto:" + label:
                self._out.append(f" ({href})")
            self._link = None

    def handle_data(self, data):
        data = re.sub(r"\s+", " ", data)
        at_line_start = not self._out or self._out[-1].endswith("\n")
        if at_line_start:
            data = data.lstrip()
        if data:
            self._out.append(data)

    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "".join(self._out)).strip() + "\n"


def html_to_text(fragment: str) -> str:
    parser = _TextExtractor()
    parser.feed(fragment)
    parser.close()
    return parser.text()
