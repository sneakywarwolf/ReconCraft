# ===================== gui/ansi_text_viewer.py =====================
# A lightweight ANSI-to-HTML QTextEdit for Raw View rendering + search + copy-as-plain

try:
    from PyQt5.QtWidgets import QTextEdit, QApplication as _QApp
    from PyQt5.QtGui import QTextCursor, QTextDocument
    from PyQt5.QtCore import Qt
except Exception:
    from PySide6.QtWidgets import QTextEdit, QApplication as _QApp
    from PySide6.QtGui import QTextCursor, QTextDocument
    from PySide6.QtCore import Qt

import html
import re

ANSI_PATTERN = re.compile(r"\x1b\[([0-9;]*)m")

# Basic 16/8-bit terminal color map → hex (foreground)
COLOR_MAP = {
    30: "#000000", 31: "#AA0000", 32: "#00AA00", 33: "#AA5500",
    34: "#0000AA", 35: "#AA00AA", 36: "#00AAAA", 37: "#AAAAAA",
    90: "#555555", 91: "#FF5555", 92: "#55FF55", 93: "#FFFF55",
    94: "#5555FF", 95: "#FF55FF", 96: "#55FFFF", 97: "#FFFFFF",
}
BG_COLOR_MAP = {k + 10: v for k, v in COLOR_MAP.items() if k < 40} | {k + 10: v for k, v in COLOR_MAP.items() if k >= 90}


def _ansi_to_html(text: str) -> str:
    """Convert ANSI SGR sequences to HTML spans. Handles bold, underline, fg/bg colors.
    Non-essential SGRs are ignored (safe fallback)."""
    def close_span(state):
        if state["open"]:
            state["html"].append("</span>")
            state["open"] = False

    state = {
        "bold": False,
        "underline": False,
        "italic": False,
        "fg": None,
        "bg": None,
        "open": False,
        "html": [],
    }

    pos = 0
    for m in ANSI_PATTERN.finditer(text):
        # emit literal segment (escaped)
        literal = text[pos:m.start()]
        if literal:
            if not state["open"]:
                # open with current style if needed
                style = []
                if state["bold"]:
                    style.append("font-weight:bold")
                if state["underline"]:
                    style.append("text-decoration:underline")
                if state["italic"]:
                    style.append("font-style:italic")
                if state["fg"]:
                    style.append(f"color:{state['fg']}")
                if state["bg"]:
                    style.append(f"background-color:{state['bg']}")
                if style:
                    state["html"].append(f"<span style=\"{' ;'.join(style)}\">")
                    state["open"] = True
            state["html"].append(html.escape(literal).replace("\n", "<br>"))

        # parse SGR codes
        codes = [int(c) if c else 0 for c in m.group(1).split(";") if c != ""]
        if not codes:
            codes = [0]
        for code in codes:
            if code == 0:  # reset
                close_span(state)
                state.update({"bold": False, "underline": False, "italic": False, "fg": None, "bg": None})
            elif code == 1:
                close_span(state); state["bold"] = True
            elif code == 3:
                close_span(state); state["italic"] = True
            elif code == 4:
                close_span(state); state["underline"] = True
            elif 30 <= code <= 37 or 90 <= code <= 97:
                close_span(state); state["fg"] = COLOR_MAP.get(code)
            elif 40 <= code <= 47 or 100 <= code <= 107:
                close_span(state); state["bg"] = BG_COLOR_MAP.get(code)
            # ignore other SGR codes safely
        pos = m.end()

    # tail
    tail = text[pos:]
    if tail:
        if not state["open"]:
            style = []
            if state["bold"]:
                style.append("font-weight:bold")
            if state["underline"]:
                style.append("text-decoration:underline")
            if state["italic"]:
                style.append("font-style:italic")
            if state["fg"]:
                style.append(f"color:{state['fg']}")
            if state["bg"]:
                style.append(f"background-color:{state['bg']}")
            if style:
                state["html"].append(f"<span style=\"{' ;'.join(style)}\">")
                state["open"] = True
        state["html"].append(html.escape(tail).replace("\n", "<br>"))

    if state["open"]:
        state["html"].append("</span>")

    return "".join(state["html"]) or ""


ANSI_STRIP = re.compile(r"\x1b\[[0-9;]*m")

def strip_ansi(s: str) -> str:
    return ANSI_STRIP.sub("", s)


class AnsiTextViewer(QTextEdit):
    """QTextEdit that renders ANSI-colored text as HTML and supports find/next/prev."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self._raw_text = ""
        self._matches = []
        self._current = -1

    def set_ansi_text(self, text: str):
        self._raw_text = text or ""
        html_text = _ansi_to_html(self._raw_text)
        # wrap in monospace + dark-friendly default
        html_doc = f"""
        <html><head><meta charset='utf-8'>
        <style>
            body {{ font-family: Consolas, 'Fira Code', monospace; font-size: 12px; }}
            .highlight {{ background: yellow; color: black; }}
        </style>
        </head><body>{html_text}</body></html>
        """
        self.setHtml(html_doc)
        self.moveCursor(QTextCursor.Start)
        self._matches.clear(); self._current = -1

    def copy_plain(self):
        # copy stripped ANSI text to clipboard
        cb = _QApp.clipboard() if _QApp.instance() else None
        plain = strip_ansi(self._raw_text)
        if cb:
            cb.setText(plain)
        return plain

    def find_all(self, term: str, case_sensitive: bool = False):
        # For now, just navigate to next/prev using built-in find
        self._matches.clear(); self._current = -1
        if not term:
            return 0
        return self.find_next(term, case_sensitive, reset=True)

    def _new_find_flags(self):
        """Create a QTextDocument.FindFlags value compatible with PyQt/PySide."""
        try:
            return QTextDocument.FindFlags()   # PyQt5 style (callable)
        except TypeError:
            return QTextDocument.FindFlags(0)  # fallback if constructor requires int

    def find_next(self, term: str, case_sensitive: bool = False, reset: bool = False):
        if reset:
            self.moveCursor(QTextCursor.Start)
        flags = self._new_find_flags()
        if case_sensitive:
            flags |= QTextDocument.FindCaseSensitively
        found = self.find(term, flags)
        return 1 if found else 0

    def find_prev(self, term: str, case_sensitive: bool = False):
        flags = QTextDocument.FindBackward
        if case_sensitive:
            flags |= QTextDocument.FindCaseSensitively
        found = self.find(term, flags)
        return 1 if found else 0
