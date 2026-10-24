"""Incremental PDFium text search; overlays never alter document contents."""
from dataclasses import dataclass
import ctypes as C

import pypdfium2 as pdf
from PySide6.QtCore import QObject, QTimer, Qt, QEvent, QRectF
from PySide6.QtGui import QPen, QColor, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLineEdit, QLabel, QToolButton, QCheckBox, QStyle


@dataclass(frozen=True)
class Hit:
    page: int
    start: int
    length: int
    rects: tuple


class SearchSession:
    """One independent snapshot, processed on the GUI thread in small batches.

    PDFium is not thread-safe. Timers keep the UI responsive without sharing its
    global state across workers, or retaining handles owned by the editable model.
    """
    def __init__(self, data, query, match_case=False, whole_word=False, limit=10000):
        self.doc = pdf.PdfDocument(data)
        self.query, self.match_case, self.whole_word = query, match_case, whole_word
        self.limit, self.total = limit, 0
        self.page_index = 0
        self.page = self.text = self.finder = None
        self.done = not bool(query)
        self.truncated = False
        self.has_text = False

    def close_page(self):
        for name in ('finder', 'text', 'page'):
            value = getattr(self, name)
            if value is not None:
                value.close(); setattr(self, name, None)

    def close(self):
        self.close_page()
        if self.doc is not None:
            self.doc.close(); self.doc = None

    def step(self, batch=50):
        hits = []
        if self.done:
            return hits
        if self.page is None:
            if self.page_index >= len(self.doc):
                self.done = True
                return hits
            self.page = self.doc[self.page_index]
            self.text = self.page.get_textpage()
            self.has_text |= self.text.count_chars() > 0
            self.text.count_rects()
            self.finder = self.text.search(self.query, match_case=self.match_case,
                                           match_whole_word=self.whole_word)
        for _ in range(batch):
            found = self.finder.get_next()
            if found is None:
                self.close_page(); self.page_index += 1
                self.done = self.page_index >= len(self.doc)
                break
            start, length = found
            rects = tuple(self.text.get_rect(i) for i in range(min(64, self.text.count_rects(start, length))))
            hits.append(Hit(self.page_index, start, length, rects))
            self.total += 1
            if self.total >= self.limit:
                self.done = self.truncated = True
                break
        return hits


class SearchController(QObject):
    def __init__(self, window, layout):
        super().__init__(window)
        self.window = window
        self.session = None
        self.hits = []
        self.by_page = {}
        self.current = -1
        self.key = None
        self.items = []
        self.pending_jump = False
        self.running = False
        self.bar = QFrame(); self.bar.setObjectName('searchBar')
        self.bar.setStyleSheet('#searchBar { background:white; border-bottom:1px solid #d5dfe6; }')
        row = QHBoxLayout(self.bar); row.setContentsMargins(12, 3, 12, 3)
        row.addWidget(QLabel('Buscar'))
        self.query = QLineEdit(); self.query.setPlaceholderText('Texto en este documento…')
        self.query.setClearButtonEnabled(True); self.query.setMaxLength(256)
        self.query.setMinimumWidth(180); self.query.setMaximumWidth(400)
        self.query.setStyleSheet('background:white; color:#172b3a; padding:5px; border:1px solid #d5dfe6; border-radius:4px;')
        self.query.installEventFilter(self); row.addWidget(self.query, 1)
        self.count = QLabel(''); self.count.setMinimumWidth(115); row.addWidget(self.count)
        self.previous = self.tool(row, '↑', 'Coincidencia anterior · Mayús+F3', lambda:self.move(-1))
        self.next = self.tool(row, '↓', 'Coincidencia siguiente · Enter / F3', lambda:self.move(1))
        self.match_case = QCheckBox('Aa'); self.match_case.setToolTip('Distinguir mayúsculas y minúsculas')
        self.whole_word = QCheckBox('Palabra completa')
        row.addWidget(self.match_case); row.addWidget(self.whole_word); row.addStretch()
        close = self.tool(row, '', 'Cerrar búsqueda · Esc', self.hide)
        close.setIcon(window.style().standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton))
        layout.insertWidget(2, self.bar); self.bar.hide()
        self.debounce = QTimer(self); self.debounce.setSingleShot(True); self.debounce.setInterval(180)
        self.debounce.timeout.connect(self.start)
        self.timer = QTimer(self); self.timer.setInterval(1); self.timer.timeout.connect(self.step)
        self.query.textChanged.connect(self.schedule)
        self.match_case.toggled.connect(self.schedule); self.whole_word.toggled.connect(self.schedule)
        self.refresh_count()

    def tool(self, row, text, tooltip, callback):
        button = QToolButton(); button.setText(text); button.setToolTip(tooltip)
        button.clicked.connect(callback); row.addWidget(button)
        return button

    def eventFilter(self, obj, event):
        if obj is self.query:
            if event.type() == QEvent.Type.FocusIn:
                self.window.set_edit_shortcuts(False)
            elif event.type() == QEvent.Type.FocusOut:
                self.window.set_edit_shortcuts(not self.window.inline.active)
            elif event.type() == QEvent.Type.KeyPress:
                if event.key() == Qt.Key.Key_Escape:
                    self.hide(); return True
                if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    if self.debounce.isActive():
                        self.debounce.stop(); self.start()
                    else:
                        self.move(-1 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1)
                    return True
        return super().eventFilter(obj, event)

    def show(self):
        if not self.window.model:
            self.window.statusBar().showMessage('Abre un PDF para buscar texto.', 6000); return
        if self.window.inline.active and not self.window.inline.commit():
            return
        self.bar.show(); self.query.setFocus(); self.query.selectAll()
        self.document_changed()
        if self.query.text() and not self.hits and not self.running:
            self.schedule()

    def hide(self):
        self.bar.hide(); self.stop(); self.hits.clear(); self.by_page.clear(); self.current = -1
        self.refresh_overlays(); self.window.focus_editor()

    def stop(self):
        self.debounce.stop(); self.timer.stop(); self.running = False
        if self.session:
            self.session.close(); self.session = None

    def schedule(self, *_):
        self.stop(); self.hits.clear(); self.by_page.clear(); self.current = -1
        self.refresh_overlays(); self.refresh_count()
        if self.query.text() and self.window.model and self.bar.isVisible():
            self.count.setText('Buscando…'); self.debounce.start()

    def start(self):
        self.stop()
        if not self.window.model or not self.query.text() or not self.bar.isVisible():
            return
        self.key = (id(self.window.model), self.window.model.current_version)
        try:
            self.session = SearchSession(self.window.model._data, self.query.text(),
                                         self.match_case.isChecked(), self.whole_word.isChecked())
            self.running = True; self.timer.start(); self.refresh_count()
        except Exception as error:
            self.failed(error)

    def step(self):
        if not self.session:
            return
        try:
            for hit in self.session.step():
                index = len(self.hits); self.hits.append(hit)
                self.by_page.setdefault(hit.page, []).append((index, hit))
            self.refresh_count()
            if self.session.done:
                truncated, has_text = self.session.truncated, self.session.has_text
                self.stop()
                if self.hits:
                    self.current = next((i for i,h in enumerate(self.hits)
                                         if h.page >= self.window.model.index), 0)
                    self.visit()
                self.refresh_overlays(); self.refresh_count()
                if truncated:
                    self.count.setText(f'{self.current+1} / {len(self.hits)}+')
                    self.count.setToolTip('Se muestran las primeras 10 000 coincidencias. Afina el texto de búsqueda.')
                elif not has_text:
                    self.count.setText('Sin texto buscable')
                    self.count.setToolTip('Para buscar en escaneos: Edición → Reconocer texto (OCR).')
            elif self.hits:
                self.draw_active()
        except Exception as error:
            self.failed(error)

    def failed(self, error):
        self.stop(); self.count.setText('Error de búsqueda')
        self.count.setToolTip(str(error)); self.window.statusBar().showMessage(str(error), 10000)

    def refresh_count(self):
        self.count.setToolTip('')
        self.count.setText(f'{len(self.hits)} · Buscando…' if self.running else
                           f'{self.current+1} / {len(self.hits)}' if self.hits else
                           'Sin coincidencias' if self.query.text() else '')
        for button in (self.next, self.previous):
            button.setEnabled(bool(self.hits) and not self.running)

    def move(self, direction):
        if self.bar.isHidden():
            self.show()
            if self.query.text(): self.schedule()
            return
        if not self.hits or self.running:
            return
        self.current = (self.current+direction) % len(self.hits)
        self.visit(); self.refresh_count()

    def visit(self):
        hit = self.hits[self.current]
        self.window.navigate(hit.page)
        if self.window.model.index != hit.page:
            return
        self.refresh_overlays()
        if hit.rects:
            rect = self.window.canvas.object_rect(hit.rects[0])
            canvas = self.window.canvas
            point = canvas.mapTo(self.window.document_view.widget(),
                                 canvas.mapFromScene(rect.center()))
            view = self.window.document_view
            view.ensureVisible(point.x(), point.y(), 55, 0)
            view.verticalScrollBar().setValue(point.y()-view.viewport().height()//2)

    def document_changed(self):
        model = self.window.model
        key = (id(model), model.current_version) if model else None
        if self.key != key:
            self.key = key
            self.schedule()
        self.draw_active()

    def refresh_overlays(self):
        self.draw_active()
        for slot in self.window.document_view.slots:
            slot.preview_version = None
        self.window.document_view.timer.start()

    def draw_active(self):
        canvas = self.window.canvas
        for item in self.items:
            if item.scene() is canvas.scene(): canvas.scene().removeItem(item)
        self.items = []
        if self.bar.isHidden() or not self.window.model:
            return
        for index, hit in self.by_page.get(self.window.model.index, [])[:1500]:
            color = QColor('#ffb54a' if index == self.current else '#ffe861'); color.setAlpha(110)
            pen = QPen(QColor('#b76506') if index == self.current else Qt.PenStyle.NoPen)
            for bounds in hit.rects:
                item = canvas.scene().addRect(canvas.object_rect(bounds).adjusted(-1,-1,1,1),pen,color)
                item.setZValue(3); item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                self.items.append(item)

    def before_canvas_clear(self):
        # QGraphicsScene.clear() deletes its C++ items immediately.
        self.items = []

    def decorate_preview(self, image, page, index):
        hits = self.by_page.get(index, []) if not self.bar.isHidden() else []
        if not hits:
            return image
        painter = QPainter(image)
        try:
            for number, hit in hits[:1500]:
                color = QColor('#ffb54a' if number == self.current else '#ffe861'); color.setAlpha(110)
                for bounds in hit.rects:
                    points = []
                    for x in (bounds[0], bounds[2]):
                        for y in (bounds[1], bounds[3]):
                            dx,dy=C.c_int(),C.c_int()
                            pdf.raw.FPDF_PageToDevice(page,0,0,image.width(),image.height(),0,x,y,C.byref(dx),C.byref(dy))
                            points.append((dx.value,dy.value))
                    xs,ys=zip(*points)
                    painter.fillRect(QRectF(min(xs)-1,min(ys)-1,max(xs)-min(xs)+2,max(ys)-min(ys)+2),color)
        finally:
            painter.end()
        return image
