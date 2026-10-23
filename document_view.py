"""Continuous pages with one reusable editor and bounded preview memory."""
from PySide6.QtCore import Qt, QTimer, QPoint, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QScrollArea, QWidget, QVBoxLayout, QLabel, QApplication


class PageSlot(QWidget):
    def __init__(self, view, index):
        super().__init__()
        self.view, self.index = view, index
        self.preview_version = None
        self.forwarding = False
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.preview = QLabel()
        self.preview.setStyleSheet('background:white;')
        self.layout.addWidget(self.preview)
        self.preview.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def forward(self, event):
        canvas = self.view.owner.canvas
        point = canvas.viewport().mapFromGlobal(event.globalPosition().toPoint())
        forwarded = QMouseEvent(event.type(), point, event.globalPosition(),
                                event.button(), event.buttons(), event.modifiers())
        QApplication.sendEvent(canvas.viewport(), forwarded)
        event.accept()

    def mousePressEvent(self, event):
        if self.view.activate(self.index):
            self.forwarding = True
            self.forward(event)

    def mouseMoveEvent(self, event):
        if self.forwarding:
            self.forward(event)

    def mouseReleaseEvent(self, event):
        if self.forwarding:
            self.forwarding = False
            self.forward(event)

    def contextMenuEvent(self, event):
        if self.view.activate(self.index):
            canvas=self.view.owner.canvas
            point=canvas.viewport().mapFromGlobal(event.globalPos())
            self.view.owner.show_context_menu(event.globalPos(),canvas.mapToScene(point))
            event.accept()


class DocumentView(QScrollArea):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.continuous = True
        self.slots = []
        self.signature = None
        self.active_index = None
        self.syncing = False
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setStyleSheet('QScrollArea, #documentPages { background:#e2e8ee; border:0; }')
        self.content = QWidget()
        self.content.setObjectName('documentPages')
        self.layout = QVBoxLayout(self.content)
        self.layout.setContentsMargins(28, 22, 28, 22)
        self.layout.setSpacing(22)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.setWidget(self.content)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(35)
        self.timer.timeout.connect(self.visible_pages)
        self.verticalScrollBar().valueChanged.connect(lambda *_: self.timer.start())

    def activate(self, index):
        if self.owner.model.index != index:
            self.owner.navigate(index, scroll=False)
        return self.owner.model.index == index

    def dimensions(self):
        model = self.owner.model
        key = (id(model), model.current_version)
        if getattr(self,'dimension_key',None) != key:
            result = []
            for i in range(len(model.doc)):
                page = model.doc[i]
                try:result.append(tuple(page.get_size()))
                finally:page.close()
            self.dimension_cache, self.dimension_key = result, key
        return self.dimension_cache

    def sync(self):
        model, canvas = self.owner.model, self.owner.canvas
        self.syncing = True
        try:
            dimensions = self.dimensions()
            signature = (id(model), tuple(dimensions), round(self.owner.zoom, 6))
            if signature != self.signature:
                canvas.setParent(self)
                for slot in self.slots:
                    self.layout.removeWidget(slot)
                    slot.deleteLater()
                self.slots = []
                for i, (width, height) in enumerate(dimensions):
                    slot = PageSlot(self, i)
                    # PDFium rounds rendered dimensions upwards.
                    import math
                    slot.setFixedSize(math.ceil(width*self.owner.zoom)+56,
                                      math.ceil(height*self.owner.zoom)+56)
                    self.layout.addWidget(slot, 0, Qt.AlignmentFlag.AlignHCenter)
                    self.slots.append(slot)
                self.signature = signature
                self.active_index = None
            old = self.active_index
            if old != model.index or canvas.parentWidget() is not self.slots[model.index]:
                if old is not None and old < len(self.slots):
                    self.slots[old].preview.show()
                    self.slots[old].preview_version = None
                slot = self.slots[model.index]
                slot.preview.hide()
                slot.layout.addWidget(canvas)
                canvas.show()
                self.active_index = model.index
            slot = self.slots[model.index]
            canvas.setFixedSize(slot.size())
            canvas.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            canvas.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            for i, item in enumerate(self.slots):
                item.setVisible(self.continuous or i == model.index)
            self.layout.activate()
        finally:
            self.syncing = False
        self.timer.start()

    def scroll_to_page(self, index):
        self.layout.activate()
        self.verticalScrollBar().setValue(max(0, self.slots[index].y()-22))
        self.timer.start()

    def visible_pages(self):
        if self.syncing or not self.owner.model or not self.slots:
            return
        from app import pixmap
        model = self.owner.model
        top = self.verticalScrollBar().value()
        bottom = top+self.viewport().height()
        for i, slot in enumerate(self.slots):
            near = slot.isVisible() and slot.y()+slot.height() >= top-250 and slot.y() <= bottom+250
            if i == model.index:
                continue
            if near and slot.preview_version != model.current_version:
                page = model.doc[i]
                try:
                    slot.preview.setPixmap(pixmap(page, self.owner.zoom))
                    slot.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    slot.preview.setStyleSheet('background:#e2e8ee;')
                    slot.preview_version = model.current_version
                finally:
                    page.close()
            elif not near:
                slot.preview.clear()
                slot.preview_version = None
        # Changing pages must never commit an unfinished edit merely by scrolling.
        if self.continuous and not self.owner.inline.active and not self.owner.canvas.dragging():
            target = min(range(len(self.slots)), key=lambda i:
                         abs(self.slots[i].y()+min(self.slots[i].height()/2, self.viewport().height()/2)-
                             (top+self.viewport().height()/2)))
            if target != model.index:
                self.activate(target)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.owner.change_zoom(1.15 if event.angleDelta().y() > 0 else 1/1.15)
            event.accept()
        else:
            super().wheelEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.timer.start()
