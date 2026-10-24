"""Copy selectable native/OCR text without opening the text editor."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QApplication
from engine import pdf


class TextSelection:
    def __init__(self, window):
        self.window = window
        self.anchor = None
        self.value = ''
        self.items = []

    def clear(self):
        scene = self.window.canvas.scene()
        for item in self.items: scene.removeItem(item)
        self.items.clear(); self.anchor = None; self.value = ''

    def character(self, position):
        model = self.window.model
        x, y = self.window.canvas.to_page(position)
        tolerance = 6 / self.window.zoom
        return pdf.raw.FPDFText_GetCharIndexAtPos(model.textpage, x, y, tolerance, tolerance)

    def select(self, start, count):
        self.clear()
        text = self.window.model.textpage
        self.value = text.get_text_range(start, count)
        canvas = self.window.canvas
        for i in range(min(1000, text.count_rects(start, count))):
            item = canvas.scene().addRect(canvas.object_rect(text.get_rect(i)),
                QPen(Qt.PenStyle.NoPen), QColor(0, 130, 200, 65))
            item.setZValue(22); self.items.append(item)

    def press(self, position):
        index = self.character(position)
        self.clear()
        if index >= 0:
            self.select(index, 1); self.anchor = index

    def move(self, position):
        if self.anchor is None: return
        index = self.character(position)
        if index < 0: return
        anchor = self.anchor
        self.select(min(anchor, index), abs(index-anchor)+1)
        self.anchor = anchor

    def word(self, position):
        text = self.window.model.textpage
        index = self.character(position)
        if index < 0: return
        def letter(i):
            c = chr(pdf.raw.FPDFText_GetUnicode(text, i))
            return c.isalnum() or c == '_'
        start, end = index, index
        while start > 0 and letter(start-1): start -= 1
        while end+1 < text.count_chars() and letter(end+1): end += 1
        self.select(start, end-start+1)

    def all(self):
        if self.window.model and self.window.mode == 'select':
            text = self.window.model.textpage
            if text.count_chars(): self.select(0, text.count_chars())

    def copy(self):
        if self.window.inline.active:
            cursor = self.window.inline.editor.textCursor()
            if cursor.hasSelection(): QApplication.clipboard().setText(cursor.selectedText().replace('\u2029', '\n'))
        elif self.value:
            QApplication.clipboard().setText(self.value)
            self.window.statusBar().showMessage('Texto copiado.', 4000)
