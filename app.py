"""Faro PDF: a local Windows reader and object editor powered by PDFium."""
import argparse
import ctypes as C
import json
import math
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QRectF, QSize, QTimer, QPointF
from PySide6.QtGui import QAction, QImage, QPixmap, QPen, QColor, QKeySequence, QIcon, QFontDatabase, QFont, QActionGroup, QTransform
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QButtonGroup, QListWidget, QListWidgetItem, QGraphicsView,
    QGraphicsScene, QFrame, QFileDialog, QMessageBox, QDialog, QPlainTextEdit,
    QDoubleSpinBox, QComboBox, QCheckBox, QDialogButtonBox, QFormLayout,
    QSpinBox, QStyle, QToolButton, QMenu, QAbstractItemView, QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea,
    QInputDialog,
)

from engine import Document, TEXT, IMAGE, pdf
from inline_edit import InlineController
from document_view import DocumentView

ROOT = Path(__file__).resolve().parent
VERSION = '1.1.1'

STYLE = '''
QMainWindow, QDialog { background: #f5f7fa; color: #172b3a; }
QWidget { font-family: 'Segoe UI'; font-size: 13px; color: #172b3a; }
QFrame#header { background: #142b3a; }
QFrame#header QLabel { color: white; background: transparent; }
QLabel#brand { font-size: 21px; font-weight: 700; letter-spacing: 2px; }
QLabel#subtitle { color: #a9c4d1; font-size: 11px; }
QFrame#tools { background: white; border-bottom: 1px solid #dae2e9; }
QFrame#sidebar, QFrame#properties { background: white; }
QLabel#section { color: #6a7d8d; font-size: 10px; font-weight: 700; letter-spacing: 1.5px; }
QLabel#title { font-size: 17px; font-weight: 600; }
QLabel#muted { color: #6a7d8d; }
QLabel#notice { color: #645224; background: #fff5d9; padding: 10px 16px; }
QPushButton { background: #fff; border: 1px solid #d9e2e9; border-radius: 6px; padding: 8px 13px; }
QPushButton:hover { background: #edf5f6; border-color: #74b1b0; }
QPushButton:checked, QPushButton#primary { background: #087f7b; border-color: #087f7b; color: white; }
QPushButton#primary:hover { background: #066b68; }
QPushButton:disabled, QPushButton#primary:disabled { color: #aab5bd; background: #f3f5f7; border-color: #e8edf1; }
QPushButton#danger { color: #ba4050; }
QListWidget { background: #f4f7fa; border: none; outline: none; }
QListWidget::item { background: white; border: 1px solid #e1e8ee; border-radius: 6px; margin: 7px 12px; padding: 10px; }
QListWidget::item:selected { border: 2px solid #087f7b; background: #e9f5f3; color: #086662; }
QGraphicsView { background: #e2e8ee; border: none; }
QPlainTextEdit, QComboBox, QDoubleSpinBox, QSpinBox { background: white; border: 1px solid #d5dfe6; padding: 5px; border-radius: 4px; }
QComboBox QAbstractItemView { background-color: #ffffff; color: #172b3a; selection-background-color: #087f7b; selection-color: #ffffff; alternate-background-color: #f3f6f8; }
QComboBox QAbstractItemView::item { color: #172b3a; background-color: #ffffff; min-height: 24px; }
QComboBox QAbstractItemView::item:selected { background-color: #087f7b; color: #ffffff; }
QStatusBar { background: #142b3a; color: #d0e0e8; }
QStatusBar QLabel { color: #d0e0e8; }
QToolButton { padding: 4px 7px; border: none; border-radius: 4px; min-height: 24px; }
QToolButton:hover { background: #e4efef; }
QToolButton::menu-indicator { subcontrol-position: right center; }
QMenu { background: white; border: 1px solid #d5dfe6; padding: 5px; }
QMenu::item { padding: 7px 24px; }
QMenu::item:selected { background: #e4f2f0; }
QToolTip { background: #142b3a; color: white; padding: 6px; border: none; }
'''


def pixmap(page, scale):
    bitmap = page.render(scale=scale, force_bitmap_format=pdf.raw.FPDFBitmap_BGRA, rev_byteorder=True)
    image = QImage(bitmap.buffer, bitmap.width, bitmap.height, bitmap.stride, QImage.Format.Format_RGBA8888).copy()
    bitmap.close()
    return QPixmap.fromImage(image)


class TextDialog(QDialog):
    def __init__(self, parent, info=None, adding=False):
        super().__init__(parent)
        self.info = info or {}
        native = self.info.get('type') == TEXT
        self.setWindowTitle('Editar texto' if native else 'Añadir texto' if adding else 'Reemplazar imagen por texto')
        self.resize(510, 400)
        layout = QVBoxLayout(self)
        lead = QLabel('El objeto seleccionado contiene texto nativo.' if native else
                      'El bloque seleccionado es una imagen. Se retirará esa aparición y se insertará el texto que escribas.' if not adding else
                      'Escribe el texto que quieres colocar en esta posición.')
        lead.setWordWrap(True)
        layout.addWidget(lead)
        self.text = QPlainTextEdit(self.info.get('text', ''))
        self.text.setPlaceholderText('Escribe aquí el contenido…')
        self.text.setMinimumHeight(150)
        layout.addWidget(self.text)
        self.keep = QCheckBox('Conservar la fuente original')
        self.keep.setChecked(native)
        self.keep.setVisible(native)
        layout.addWidget(self.keep)
        form = QFormLayout()
        self.font = QComboBox()
        self.font.addItems(['Helvetica', 'Helvetica-Bold', 'Times-Roman', 'Times-Bold', 'Courier'])
        self.size = QDoubleSpinBox()
        self.size.setRange(3, 160)
        self.size.setSuffix(' pt')
        self.size.setDecimals(1)
        bounds = self.info.get('bounds', (0, 0, 200, 16))
        self.size.setValue(self.info.get('size', 12) if native or adding else max(8, min(28, (bounds[3]-bounds[1])*.72)))
        self.color = QComboBox()
        for label, value in [('Azul oscuro', (13, 43, 49)), ('Negro', (0, 0, 0)), ('Gris', (80, 90, 100))]:
            self.color.addItem(label, value)
        form.addRow('Fuente', self.font)
        form.addRow('Tamaño', self.size)
        form.addRow('Color', self.color)
        layout.addLayout(form)
        note = QLabel('Las fuentes originales de una imagen no se recuperan automáticamente. Puedes ajustar fuente y tamaño y deshacer el resultado.')
        note.setObjectName('muted')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.keep.toggled.connect(self.update_fields)
        self.update_fields(self.keep.isChecked())
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Aplicar')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Cancelar')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def update_fields(self, keep):
        for widget in (self.font, self.color):
            widget.setEnabled(not keep)

    def values(self):
        return self.text.toPlainText(), self.size.value(), self.font.currentText(), self.color.currentData()


class Canvas(QGraphicsView):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setScene(QGraphicsScene(self))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.drag_start = None
        self.resize_start=None
        self.text_drag_start=None
        self.text_grip=None
        self.resize_handles=[]
        self.text_selecting = False
        self.outline = None
        self.text_boxes = []
        self.page_item = None
        self.page_width = self.page_height = 1
        self.box_start = None
        self.box_draft = None
        self.pan_start = None
        self.setAcceptDrops(True)
        self.setMouseTracking(True)

    def display(self, image):
        self.scene().clear()
        self.text_grip=None
        self.resize_handles=[]
        self.outline = None
        self.text_boxes = []
        self.page_item = self.scene().addPixmap(image)
        self.scene().setSceneRect(QRectF(-28, -28, image.width()+56, image.height()+56))
        self.page_width, self.page_height = image.width(), image.height()
        self._axes=None
        self.refresh_text_boxes()

    def dragging(self):
        return any(value is not None for value in
                   (self.drag_start, self.resize_start, self.text_drag_start,
                    self.box_start, self.pan_start)) or self.text_selecting

    def bounded_position(self, point):
        return QPointF(max(0, min(self.page_width, point.x())),
                       max(0, min(self.page_height, point.y())))

    def to_page(self, point):
        origin,dx,dy = self.page_axes()
        return (origin[0]+dx[0]*point.x()+dy[0]*point.y(),
                origin[1]+dx[1]*point.x()+dy[1]*point.y())

    def page_axes(self):
        if getattr(self,'_axes',None) is not None: return self._axes
        points=[]
        for sx,sy in ((0,0),(self.page_width,0),(0,self.page_height)):
            x,y=C.c_double(),C.c_double()
            pdf.raw.FPDF_DeviceToPage(self.owner.model.page,0,0,self.page_width,self.page_height,
                                     0,sx,sy,C.byref(x),C.byref(y))
            points.append((x.value,y.value))
        p,a,b=points
        self._axes=p,((a[0]-p[0])/self.page_width,(a[1]-p[1])/self.page_width),((b[0]-p[0])/self.page_height,(b[1]-p[1])/self.page_height)
        return self._axes

    def to_scene(self, x, y):
        p,a,b=self.page_axes()
        determinant=a[0]*b[1]-a[1]*b[0]
        x,y=x-p[0],y-p[1]
        return (x*b[1]-y*b[0])/determinant,(a[0]*y-a[1]*x)/determinant

    def refresh_text_boxes(self):
        for item in self.text_boxes:
            self.scene().removeItem(item)
        self.text_boxes=[]
        if not self.owner.model or self.owner.mode!='text': return
        pen=QPen(QColor('#b3bec8'),1)
        pen.setCosmetic(True)
        for block in self.owner.model.text_blocks():
            item=self.scene().addRect(self.object_rect(block['bounds']).adjusted(-1.5,-1.5,1.5,1.5),pen)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            item.setZValue(5)
            self.text_boxes.append(item)

    def object_rect(self, bounds):
        points = [self.to_scene(x, y) for x in (bounds[0], bounds[2]) for y in (bounds[1], bounds[3])]
        xs, ys = zip(*points)
        return QRectF(min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys))

    def select_outline(self, bounds):
        if self.text_grip:self.scene().removeItem(self.text_grip);self.text_grip=None
        for _,item in self.resize_handles:self.scene().removeItem(item)
        self.resize_handles=[]
        if self.outline:
            self.scene().removeItem(self.outline)
        pen = QPen(QColor('#07847e'), 1.5)
        pen.setCosmetic(True)
        self.outline = self.scene().addRect(self.object_rect(bounds).adjusted(-2,-2,2,2), pen)
        self.outline.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.outline.setZValue(10)
        if self.owner.mode=='images':self.draw_resize_handles(self.object_rect(bounds))
        elif self.owner.mode=='text':
            rect=self.object_rect(bounds)
            self.text_grip=self.scene().addRect(QRectF(rect.left(),rect.top()-11,18,7),QPen(QColor('#087f7b')),QColor('#087f7b'))
            self.text_grip.setToolTip('Arrastra este tirador para mover el cuadro de texto')
            self.text_grip.setAcceptedMouseButtons(Qt.MouseButton.NoButton);self.text_grip.setZValue(20)

    def draw_resize_handles(self,rect):
        for _,item in self.resize_handles:self.scene().removeItem(item)
        self.resize_handles=[]
        for key,point in [('lt',rect.topLeft()),('rt',rect.topRight()),('lb',rect.bottomLeft()),('rb',rect.bottomRight()),('l',QPointF(rect.left(),rect.center().y())),('r',QPointF(rect.right(),rect.center().y())),('t',QPointF(rect.center().x(),rect.top())),('b',QPointF(rect.center().x(),rect.bottom()))]:
            item=self.scene().addRect(QRectF(point.x()-4,point.y()-4,8,8),QPen(QColor('#087f7b')),QColor('white'))
            item.setZValue(20);item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.resize_handles.append((key,item))

    def resized_rect(self,pos):
        key,original,index=self.resize_start
        rect=QRectF(original)
        if 'l' in key:rect.setLeft(min(pos.x(),rect.right()-10))
        if 'r' in key:rect.setRight(max(pos.x(),rect.left()+10))
        if 't' in key:rect.setTop(min(pos.y(),rect.bottom()-10))
        if 'b' in key:rect.setBottom(max(pos.y(),rect.top()+10))
        if len(key)==2:
            scale=max(rect.width()/original.width(),rect.height()/original.height())
            width,height=original.width()*scale,original.height()*scale
            if 'l' in key:rect.setLeft(original.right()-width)
            else:rect.setRight(original.left()+width)
            if 't' in key:rect.setTop(original.bottom()-height)
            else:rect.setBottom(original.top()+height)
        return rect

    def hit_object(self, scene_position, allowed=(TEXT, IMAGE)):
        if not self.owner.model:
            return None
        # Prefer text over a larger background image and allow a few screen
        # pixels around small glyphs. These are PDF bounds, not Qt text metrics.
        for kind in allowed:
            candidates = []
            if kind==TEXT:
                for run in self.owner.model.text_runs():
                    rect=self.object_rect(run['bounds'])
                    if rect.adjusted(-3,-3,3,3).contains(scene_position):
                        dx=max(rect.left()-scene_position.x(),0,scene_position.x()-rect.right())
                        dy=max(rect.top()-scene_position.y(),0,scene_position.y()-rect.bottom())
                        on_own_glyph=run.get('layout') and any(self.object_rect((row['bounds'][0],row['bounds'][2],row['bounds'][1],row['bounds'][3])).contains(scene_position) for row in run['characters'] if not row['character'].isspace())
                        candidates.append((-1 if on_own_glyph else 0 if rect.contains(scene_position) else 1,dx*dx+dy*dy,
                                           abs(rect.center().y()-scene_position.y()),run['indices'][0]))
                if candidates: return min(candidates)[-1]
                for block in self.owner.model.text_blocks():
                    if self.object_rect(block['bounds']).adjusted(-1.5,-1.5,1.5,1.5).contains(scene_position):
                        run=min(block['runs'],key=lambda r:abs(self.object_rect(r['bounds']).center().y()-scene_position.y()))
                        return run['indices'][0]
                continue
            for i, obj in enumerate(self.owner.model.objects):
                if obj.type != kind:
                    continue
                rect = self.object_rect(obj.get_bounds())
                if rect.adjusted(-3, -4, 3, 4).contains(scene_position):
                    candidates.append((max(rect.width()*rect.height(), 1), i))
            if candidates:
                return min(candidates)[1]
        return None

    def mousePressEvent(self, event):
        owner = self.owner
        pos = self.mapToScene(event.position().toPoint())
        if owner.model and owner.mode == 'read' and event.button() == Qt.MouseButton.LeftButton:
            self.pan_start = (event.globalPosition(), owner.document_view.verticalScrollBar().value(),
                              owner.document_view.horizontalScrollBar().value())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept(); return
        if owner.mode=='text' and event.button()==Qt.MouseButton.LeftButton and self.text_grip and self.text_grip.rect().adjusted(-3,-3,3,3).contains(pos):
            index=owner.selected
            if owner.inline.active:
                owner.last_text_selection=index
                if not owner.inline.commit():event.accept();return
                index=owner.last_text_selection
            if index is not None and index<len(owner.model.objects) and owner.model.objects[index].type==TEXT:
                owner.select(index)
                self.text_drag_start=(pos,index)
            event.accept();return
        if owner.mode=='images' and owner.selected is not None and event.button()==Qt.MouseButton.LeftButton:
            for key,item in self.resize_handles:
                if item.rect().adjusted(-3,-3,3,3).contains(pos):
                    self.resize_start=(key,self.object_rect(owner.model.objects[owner.selected].get_bounds()),owner.selected)
                    event.accept();return
        if event.button() == Qt.MouseButton.RightButton:
            event.accept()
            return
        if owner.inline.active and event.button() == Qt.MouseButton.LeftButton:
            if not owner.inline.pristine and owner.inline.editor.contains(owner.inline.editor.mapFromScene(pos)):
                return super().mousePressEvent(event)
            found=self.hit_object(pos,(TEXT,))
            active_indices=owner.inline.session.get('indices',[owner.inline.session['index']])
            if owner.inline.source_contains(pos) or found in active_indices or (found is None and owner.inline.source_rect().adjusted(-2,-2,2,2).contains(pos)):
                owner.inline.place_source_cursor(pos, bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
                self.text_selecting = True
                owner.focus_editor()
                event.accept()
                return
            if not owner.inline.commit():
                event.accept()
                return
        if not owner.model or owner.mode == 'read' or event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        px, py = self.to_page(pos)
        if owner.mode == 'add':
            if 0 <= pos.x() <= self.page_width and 0 <= pos.y() <= self.page_height:
                self.box_start = self.bounded_position(pos)
                self.box_draft = self.scene().addRect(QRectF(pos,pos),
                    QPen(QColor('#087f7b'), 1.5, Qt.PenStyle.DashLine), QColor(8,127,123,20))
                self.box_draft.setZValue(25)
            event.accept(); return
        if owner.mode=='imageadd':
            owner.place_image(px,py)
            return
        allowed = (IMAGE,) if owner.mode == 'images' else (TEXT, IMAGE)
        found = self.hit_object(pos, allowed)
        owner.select(found)
        if found is not None and owner.mode == 'text':
            owner.inline.begin(found, pos)
            self.text_selecting = owner.inline.active
            if self.text_selecting:
                owner.focus_editor()
            else:
                owner.statusBar().showMessage(owner.inline.status.text(), 16000)
        if found is not None and owner.mode == 'images':
            self.drag_start = (px, py, pos)
        event.accept()

    def mouseMoveEvent(self, event):
        if self.pan_start:
            start, vertical, horizontal = self.pan_start
            delta = event.globalPosition()-start
            self.owner.document_view.verticalScrollBar().setValue(vertical-round(delta.y()))
            self.owner.document_view.horizontalScrollBar().setValue(horizontal-round(delta.x()))
            event.accept(); return
        if self.box_start is not None:
            self.box_draft.setRect(QRectF(self.box_start,
                self.bounded_position(self.mapToScene(event.position().toPoint()))).normalized())
            event.accept(); return
        if self.text_drag_start and self.outline:
            delta=self.mapToScene(event.position().toPoint())-self.text_drag_start[0]
            self.outline.setPos(delta)
            if self.text_grip:self.text_grip.setPos(delta)
            event.accept();return
        if self.resize_start:
            rect=self.resized_rect(self.mapToScene(event.position().toPoint()))
            self.outline.setRect(rect);self.draw_resize_handles(rect)
            event.accept();return
        if self.text_selecting and self.owner.inline.active:
            self.owner.inline.place_source_cursor(self.mapToScene(event.position().toPoint()), True)
            event.accept()
            return
        if self.drag_start and self.outline:
            delta = self.mapToScene(event.position().toPoint()) - self.drag_start[2]
            self.outline.setPos(delta)
            for _,item in self.resize_handles:item.setPos(delta)
            event.accept()
        else:
            if self.owner.mode=='text':
                pos=self.mapToScene(event.position().toPoint())
                grip=self.text_grip and self.text_grip.rect().adjusted(-3,-3,3,3).contains(pos)
                self.setCursor(Qt.CursorShape.SizeAllCursor if grip else Qt.CursorShape.IBeamCursor if self.hit_object(pos,(TEXT,)) is not None else Qt.CursorShape.ArrowCursor)
            if self.owner.mode=='images':
                pos=self.mapToScene(event.position().toPoint());cursor=Qt.CursorShape.ArrowCursor
                for key,item in self.resize_handles:
                    if item.rect().adjusted(-3,-3,3,3).contains(pos):
                        cursor=Qt.CursorShape.SizeFDiagCursor if key in ('lt','rb') else Qt.CursorShape.SizeBDiagCursor if len(key)==2 else Qt.CursorShape.SizeHorCursor if key in ('l','r') else Qt.CursorShape.SizeVerCursor
                        break
                self.setCursor(cursor)
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.pan_start:
            self.pan_start = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept(); return
        if self.box_start is not None:
            rect = QRectF(self.box_start,self.bounded_position(self.mapToScene(event.position().toPoint()))).normalized()
            if rect.width() < 12 or rect.height() < 12:
                rect = QRectF(self.box_start.x(),self.box_start.y(),220*self.owner.zoom,65*self.owner.zoom).intersected(QRectF(0,0,self.page_width,self.page_height))
            self.scene().removeItem(self.box_draft)
            self.box_draft = self.box_start = None
            corners = [self.to_page(point) for point in (rect.topLeft(), rect.bottomRight())]
            xs,ys = zip(*corners)
            bounds = (min(xs),min(ys),max(xs),max(ys))
            self.owner.add_text(bounds[0],bounds[3],bounds)
            event.accept(); return
        if self.text_drag_start:
            start,index=self.text_drag_start;self.text_drag_start=None
            a=self.to_page(start);b=self.to_page(self.mapToScene(event.position().toPoint()))
            run=self.owner.model.text_run(index)
            if run:
                self.owner.change(lambda:self.owner.model.move_text(run['indices'],b[0]-a[0],b[1]-a[1]))
                self.owner.select(index)
            event.accept();return
        if self.resize_start:
            rect=self.resized_rect(self.mapToScene(event.position().toPoint()))
            index=self.resize_start[2];self.resize_start=None
            points=[self.to_page(p) for p in (rect.topLeft(),rect.topRight(),rect.bottomLeft(),rect.bottomRight())]
            xs,ys=zip(*points)
            self.owner.change(lambda:self.owner.model.resize_image(index,(min(xs),min(ys),max(xs),max(ys))))
            self.owner.select(index);event.accept();return
        if self.text_selecting:
            self.text_selecting = False
            if self.owner.inline.active:
                self.owner.inline.place_source_cursor(self.mapToScene(event.position().toPoint()), True)
            event.accept()
            return
        if self.drag_start:
            start = self.drag_start
            self.drag_start = None
            px, py = self.to_page(self.mapToScene(event.position().toPoint()))
            if abs(px-start[0]) + abs(py-start[1]) > .4:
                index=self.owner.selected
                self.owner.change(lambda: self.owner.model.move(index, px-start[0], py-start[1]))
                self.owner.select(index)
            elif self.outline:
                self.outline.setPos(0, 0)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.owner.inline.active:
            if not self.owner.inline.pristine:
                return super().mouseDoubleClickEvent(event)
            self.text_selecting = False
            pos=self.mapToScene(event.position().toPoint())
            found=self.hit_object(pos,(TEXT,))
            indices=self.owner.inline.session.get('indices',[self.owner.inline.session['index']])
            if found is not None and found not in indices and not self.owner.inline.source_contains(pos):
                if not self.owner.inline.commit(): event.accept(); return
                self.owner.select(found)
                self.owner.inline.begin(found,pos)
            if self.owner.inline.active: self.owner.inline.select_word(pos)
            self.owner.focus_editor()
            event.accept()
            return
        if self.owner.mode in ('text', 'images'):
            pos=self.mapToScene(event.position().toPoint())
            found=self.hit_object(pos,(TEXT,) if self.owner.mode=='text' else (IMAGE,))
            self.owner.select(found)
            if found is not None:
                self.owner.inline.begin(found,pos)
                if self.owner.inline.active:
                    self.owner.inline.select_word(pos)
                    self.owner.focus_editor()
            self.text_selecting=False
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        self.text_selecting = False
        self.owner.show_context_menu(event.globalPos(), self.mapToScene(event.pos()))
        event.accept()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.owner.change_zoom(1.15 if event.angleDelta().y() > 0 else 1/1.15)
            event.accept()
        else:
            event.ignore()  # The document scroll area owns page scrolling.

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.toLocalFile().lower().endswith('.pdf'):
                self.owner.open_file(url.toLocalFile())
                event.acceptProposedAction()
                break


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.model = None
        self.selected = None
        self.mode = 'read'
        self.zoom = 1.0
        self.fit = True
        self.setWindowTitle('Faro PDF')
        self.resize(1360, 900)
        self.setMinimumSize(880, 520)
        outer = QWidget()
        stack = QVBoxLayout(outer)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(0)
        self.setCentralWidget(outer)
        tools = QFrame()
        tools.setObjectName('tools')
        bar = QHBoxLayout(tools)
        bar.setContentsMargins(12, 4, 12, 4)
        bar.setSpacing(4)
        brand = QLabel('FARO PDF')
        brand.setStyleSheet('font-weight:700; color:#087f7b; margin-right:12px;')
        bar.addWidget(brand)
        self.filename = QLabel(self)
        self.filename.hide()
        self.file_menu = QMenu(self)
        self.edit_menu = QMenu(self)
        self.view_menu = QMenu(self)
        for name, menu in [('Archivo', self.file_menu), ('Edición', self.edit_menu), ('Ver', self.view_menu)]:
            b = QToolButton()
            b.setText(name)
            b.setMenu(menu)
            b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            b.setAutoRaise(True)
            bar.addWidget(b)
        self.file_menu.addAction('Abrir PDF…\tCtrl+O', self.open_dialog)
        self.menu_save = self.file_menu.addAction('Guardar copia…\tCtrl+Mayús+S', self.save_as)
        self.file_menu.addSeparator()
        self.file_menu.addAction('Cerrar ventana', self.close)
        self.edit_menu.addAction('Insertar imagen…',self.choose_image)
        self.edit_menu.addAction('Insertar páginas de otros PDF…',self.insert_pdf_dialog)
        self.edit_menu.addAction('Mover página…',self.move_page_dialog)
        self.edit_menu.addAction('Borrar página completa…',self.delete_page_dialog)
        self.edit_menu.addSeparator()
        self.save_button = self.icon_button(bar, QStyle.StandardPixmap.SP_DialogSaveButton, 'Guardar copia', self.save_as)
        self.undo_button = self.icon_button(bar, QStyle.StandardPixmap.SP_ArrowBack, 'Deshacer · Ctrl+Z', self.undo)
        self.redo_button = self.icon_button(bar, QStyle.StandardPixmap.SP_ArrowForward, 'Rehacer · Ctrl+Mayús+Z', self.redo)
        history_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload).pixmap(18,18)
        self.undo_button.setIcon(QIcon(history_icon.transformed(QTransform().scale(-1,1))))
        self.redo_button.setIcon(QIcon(history_icon))
        self.menu_undo = self.edit_menu.addAction('Deshacer\tCtrl+Z', self.undo)
        self.menu_redo = self.edit_menu.addAction('Rehacer\tCtrl+Mayús+Z', self.redo)
        self.edit_menu.addSeparator()
        self.mode_picker = QToolButton()
        self.mode_picker.setAutoRaise(True)
        self.mode_picker.setMinimumWidth(122)
        self.mode_picker.setStyleSheet('background:#e6f3f1; color:#076b66; font-weight:600; padding:4px 12px;')
        mode_menu = QMenu(self)
        self.mode_picker.setMenu(mode_menu)
        self.mode_picker.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.modes = QActionGroup(self)
        self.modes.setExclusive(True)
        self.mode_buttons = {}
        self.mode_titles = {'read':'Leer', 'text':'Editar texto', 'images':'Imágenes', 'add':'Añadir texto','imageadd':'Insertar imagen'}
        for key, title in self.mode_titles.items():
            action = QAction(title, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, k=key: self.choose_image() if k=='imageadd' else self.set_mode(k))
            self.modes.addAction(action)
            mode_menu.addAction(action)
            self.edit_menu.addAction(action)
            self.mode_buttons[key] = action
        self.mode_buttons['read'].setChecked(True)
        self.mode_picker.setText('Leer')
        bar.addSpacing(10)
        bar.addWidget(self.mode_picker)
        self.edit_menu.addSeparator()
        self.edit_menu.addAction('Opciones de la selección…', self.show_properties)
        self.edit_menu.aboutToShow.connect(self.refresh_menus)
        self.file_menu.aboutToShow.connect(self.refresh_menus)
        self.view_menu.addAction('Páginas…', self.show_pages)
        self.view_menu.addAction('Opciones de la selección…', self.show_properties)
        self.view_menu.addAction('Fuentes del documento…', self.font_report)
        self.view_menu.addSeparator()
        self.continuous_action = self.view_menu.addAction('Desplazamiento vertical continuo')
        self.continuous_action.setCheckable(True)
        self.continuous_action.setChecked(True)
        self.continuous_action.toggled.connect(self.set_continuous)
        self.view_menu.addAction('Ajustar al ancho', self.fit_width)
        self.view_menu.addAction('Tamaño 100 %', self.actual_size)
        bar.addStretch()
        self.icon_button(bar, QStyle.StandardPixmap.SP_ArrowLeft, 'Página anterior', lambda: self.page_step(-1))
        self.page_number = QSpinBox()
        self.page_number.setPrefix('Pág. ')
        self.page_number.setRange(1, 1)
        self.page_number.setFixedWidth(84)
        self.page_number.valueChanged.connect(lambda n: self.pages.setCurrentRow(n-1))
        bar.addWidget(self.page_number)
        self.icon_button(bar, QStyle.StandardPixmap.SP_ArrowRight, 'Página siguiente', lambda: self.page_step(1))
        bar.addSpacing(10)
        for title, callback in [('−', lambda: self.change_zoom(1/1.2)), ('+', lambda: self.change_zoom(1.2))]:
            b = QToolButton()
            b.setText(title)
            b.setAutoRaise(True)
            b.clicked.connect(callback)
            if title == '+':
                plus = b
            else:
                bar.addWidget(b)
        self.zoom_label = QLabel('100%')
        self.zoom_label.setMinimumWidth(42)
        bar.addWidget(self.zoom_label)
        bar.addWidget(plus)
        self.icon_button(bar, QStyle.StandardPixmap.SP_TitleBarMaxButton, 'Ajustar al ancho', self.fit_width)
        stack.addWidget(tools)
        self.notice = QLabel()
        self.notice.setObjectName('notice')
        self.notice.setWordWrap(True)
        self.notice.hide()
        stack.addWidget(self.notice)
        self.canvas = Canvas(self)
        self.document_view = DocumentView(self)
        stack.addWidget(self.document_view, 1)
        self.pages_dialog = QDialog(self, Qt.WindowType.Tool)
        self.pages_dialog.setWindowTitle('Páginas')
        self.pages_dialog.resize(190, 520)
        side = QVBoxLayout(self.pages_dialog)
        self.pages = QListWidget()
        self.pages.setViewMode(QListWidget.ViewMode.IconMode)
        self.pages.setMovement(QListWidget.Movement.Static)
        self.pages.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.pages.setIconSize(QSize(108,144))
        self.pages.setSpacing(0)
        self.pages.currentRowChanged.connect(self.navigate)
        side.addWidget(self.pages)
        self.properties_dialog = QDialog(self, Qt.WindowType.Tool)
        self.properties_dialog.setWindowTitle('Opciones de la selección')
        self.properties_dialog.resize(320, 580)
        options_layout = QVBoxLayout(self.properties_dialog)
        props = QFrame()
        props.setObjectName('properties')
        right = QVBoxLayout(props)
        right.setContentsMargins(20, 22, 20, 20)
        label = QLabel('SELECCIÓN')
        label.setObjectName('section')
        right.addWidget(label)
        self.selection_title = QLabel('Todo listo para leer')
        self.selection_title.setObjectName('title')
        self.selection_title.setWordWrap(True)
        right.addWidget(self.selection_title)
        self.details = QLabel('Abre un PDF o arrástralo al área central.')
        self.details.setObjectName('muted')
        self.details.setWordWrap(True)
        right.addWidget(self.details)
        right.addSpacing(14)
        self.edit_button = self.button(right, 'Editar texto', self.edit_selected, primary=True)
        self.inline = InlineController(self, right)
        self.text_format = QWidget()
        format_layout = QHBoxLayout(self.text_format)
        format_layout.setContentsMargins(12,3,12,3)
        format_layout.addWidget(QLabel('Formato de texto'))
        self.inline.fonts.setMinimumWidth(240)
        self.inline.fonts.setMaximumWidth(420)
        self.inline.size.setMaximumWidth(110)
        format_layout.addWidget(self.inline.fonts)
        format_layout.addWidget(self.inline.size)
        format_options = QToolButton()
        format_options.setText('Más opciones…')
        format_options.clicked.connect(self.show_properties)
        format_layout.addWidget(format_options)
        format_layout.addStretch()
        stack.insertWidget(1,self.text_format)
        self.text_format.hide()
        self.delete_button = self.button(right, 'Borrar objeto', self.delete_selected)
        self.delete_button.setObjectName('danger')
        right.addSpacing(18)
        self.move_group = QWidget()
        move_layout = QVBoxLayout(self.move_group)
        move_layout.setContentsMargins(0, 0, 0, 0)
        movement = QLabel('MOVER OBJETO')
        movement.setObjectName('section')
        move_layout.addWidget(movement)
        moveform = QFormLayout()
        self.dx, self.dy = QDoubleSpinBox(), QDoubleSpinBox()
        for spin in (self.dx, self.dy):
            spin.setRange(-1000, 1000)
            spin.setSuffix(' pt')
        self.dx.setValue(12)
        moveform.addRow('Horizontal →', self.dx)
        moveform.addRow('Vertical ↑', self.dy)
        move_layout.addLayout(moveform)
        self.move_button = self.button(move_layout, 'Aplicar movimiento', lambda: self.change(lambda: self.model.move(self.selected, self.dx.value(), self.dy.value())))
        right.addWidget(self.move_group)
        right.addStretch()
        hint = QLabel('Atajos\nCtrl+O   Abrir\nCtrl+S   Guardar\nCtrl+Z   Deshacer\nSupr   Borrar selección\nCtrl+rueda   Zoom')
        hint.setObjectName('muted')
        self.key_hint = hint
        right.addWidget(hint)
        scroll_props = QScrollArea()
        scroll_props.setWidgetResizable(True)
        scroll_props.setFrameShape(QFrame.Shape.NoFrame)
        scroll_props.setWidget(props)
        options_layout.addWidget(scroll_props)
        self.properties_dialog.finished.connect(lambda *_: self.focus_editor())
        self.page_status = QLabel('Sin documento')
        self.statusBar().addPermanentWidget(self.page_status)
        self.statusBar().showMessage('Abre un PDF. Las opciones están en los menús y el clic derecho.')
        self.shortcut_actions = {}
        for shortcut, callback in [('Ctrl+O', self.open_dialog), ('Ctrl+S', self.save), ('Ctrl+Shift+S', self.save_as), ('Ctrl+Z', self.undo), ('Ctrl+Shift+Z', self.redo), ('Delete', self.delete_selected)]:
            action = QAction(self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(callback)
            self.addAction(action)
            self.shortcut_actions[shortcut] = action
        self.refresh_controls()

    def icon_button(self, layout, icon, tooltip, callback):
        b = QToolButton()
        b.setAutoRaise(True)
        b.setIcon(self.style().standardIcon(icon))
        b.setIconSize(QSize(17,17))
        b.setToolTip(tooltip)
        b.clicked.connect(callback)
        layout.addWidget(b)
        return b

    def focus_editor(self):
        self.canvas.setFocus()
        if self.inline.active:
            self.inline.editor.setFocus(Qt.FocusReason.OtherFocusReason)

    def show_properties(self):
        self.properties_dialog.show()
        self.properties_dialog.raise_()

    def show_pages(self):
        self.pages_dialog.show()
        self.pages_dialog.raise_()

    def refresh_menus(self):
        self.menu_save.setEnabled(self.model is not None)
        self.menu_undo.setEnabled(self.undo_button.isEnabled())
        self.menu_redo.setEnabled(self.redo_button.isEnabled())

    def page_step(self, delta):
        if self.model:
            self.pages.setCurrentRow(max(0, min(len(self.model.doc)-1, self.model.index+delta)))

    def actual_size(self):
        if self.inline.active and not self.inline.commit():
            return
        self.fit = False
        self.zoom = 1
        self.render_page()

    def show_context_menu(self, global_position, scene_position):
        if not self.inline.active:
            self.select(self.canvas.hit_object(scene_position))
        menu = QMenu(self)
        if self.inline.active:
            menu.addAction('Seleccionar todo', lambda: self.inline.select_all())
            copy = menu.addAction('Copiar', lambda: QApplication.clipboard().setText(self.inline.editor.textCursor().selectedText()))
            copy.setEnabled(self.inline.editor.textCursor().hasSelection())
            menu.addSeparator()
        elif self.selected is not None:
            index = self.selected
            if self.model.objects[index].type == TEXT:
                menu.addAction('Editar texto', lambda: self.edit_context_object(index, scene_position))
            else:
                menu.addAction('Editar imagen', lambda: self.edit_context_object(index, scene_position, 'images'))
            menu.addAction('Borrar objeto', self.delete_selected)
        menu.addSeparator()
        menu.addAction('Opciones de la selección…', self.show_properties)
        menu.addAction('Páginas…', self.show_pages)
        menu.exec(global_position)

    def edit_context_object(self, index, position, mode='text'):
        self.set_mode(mode)
        self.select(index)
        if mode == 'text':
            self.inline.begin(index, position)

    def button(self, layout, text, callback, primary=False, icon=None):
        b = QPushButton(text)
        if primary:
            b.setObjectName('primary')
        if icon:
            b.setIcon(self.style().standardIcon(icon))
        b.clicked.connect(callback)
        layout.addWidget(b)
        return b

    def error(self, error):
        QMessageBox.warning(self, 'Faro PDF', str(error))

    def confirm_discard(self):
        if self.inline.active and not self.inline.commit():
            return False
        if not self.model or not self.model.dirty:
            return True
        choice = QMessageBox.question(self, 'Cambios sin guardar', 'Hay cambios sin guardar. ¿Quieres guardarlos antes de continuar?',
                                      QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if choice == QMessageBox.StandardButton.Save:
            return self.save()
        return choice == QMessageBox.StandardButton.Discard

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Abrir PDF', str(Path.home()/'Downloads'), 'PDF (*.pdf)')
        if path:
            self.open_file(path)

    def open_file(self, path):
        if not self.confirm_discard():
            return
        self.inline.cancel()
        try:
            candidate = Document(path)
        except Exception as error:
            self.error(f'No se pudo abrir este PDF. Los archivos cifrados requieren una versión con soporte de contraseña.\n\n{error}')
            return
        if self.model:
            self.model.close()
        self.model = candidate
        self.pages.blockSignals(True)
        self.pages.clear()
        for i in range(len(candidate.doc)):
            item = QListWidgetItem(f'Página {i+1}')
            item.setSizeHint(QSize(140, 175))
            if i < 30:
                page = candidate.doc[i]
                item.setIcon(QIcon(pixmap(page, 108/page.get_width())))
                page.close()
            self.pages.addItem(item)
        self.pages.setCurrentRow(0)
        self.pages.blockSignals(False)
        self.fit = True
        self.set_mode('read')
        self.render_page()

    def set_continuous(self, enabled):
        if self.inline.active and not self.inline.commit():
            self.continuous_action.blockSignals(True)
            self.continuous_action.setChecked(self.document_view.continuous)
            self.continuous_action.blockSignals(False)
            return
        self.document_view.continuous = enabled
        if self.model:
            self.render_page()
            self.document_view.scroll_to_page(self.model.index)

    def navigate(self, index, scroll=True):
        if self.model and index >= 0:
            if self.inline.active and not self.inline.commit():
                self.pages.blockSignals(True)
                self.pages.setCurrentRow(self.model.index)
                self.pages.blockSignals(False)
                self.page_number.blockSignals(True)
                self.page_number.setValue(self.model.index+1)
                self.page_number.blockSignals(False)
                return
            self.inline.cancel()
            self.model.set_page(index)
            self.selected = None
            self.render_page()
            if scroll:
                self.document_view.scroll_to_page(index)

    def render_page(self):
        if not self.model:
            return
        if getattr(self,'page_list_version',None)!=self.model.current_version:
            self.pages.blockSignals(True);self.pages.clear();self.pages.blockSignals(False)
            self.page_list_version=self.model.current_version
        if self.pages.count()!=len(self.model.doc):
            self.pages.blockSignals(True);self.pages.clear()
            for i in range(len(self.model.doc)):
                item=QListWidgetItem(f'Página {i+1}')
                page=self.model.doc[i]
                if i<30:item.setIcon(QIcon(pixmap(page,108/page.get_width())))
                page.close();item.setSizeHint(QSize(140,175));self.pages.addItem(item)
            self.pages.setCurrentRow(self.model.index);self.pages.blockSignals(False)
        if self.fit:
            width = max(w for w,h in self.document_view.dimensions()) if self.document_view.continuous else self.model.page.get_width()
            self.zoom = max(.2, min(3, (self.document_view.viewport().width()-126)/width))
        self.canvas.display(pixmap(self.model.page, self.zoom))
        self.document_view.sync()
        self.zoom_label.setText(f'{self.zoom*100:.0f}%')
        self.selected = None
        self.refresh_controls()
        has_text = any(o.type == TEXT for o in self.model.objects)
        self.notice.setVisible(not has_text)
        self.notice.setText('Esta página contiene letras en imágenes. Se conserva su apariencia: la conversión automática a texto con fuentes aproximadas está desactivada.')
        self.page_number.blockSignals(True)
        self.page_number.setRange(1, len(self.model.doc))
        self.page_number.setValue(self.model.index+1)
        self.page_number.blockSignals(False)
        self.pages.blockSignals(True)
        self.pages.setCurrentRow(self.model.index)
        self.pages.blockSignals(False)
        self.page_status.setText(f'Página {self.model.index+1} de {len(self.model.doc)}   ·   {len(self.model.objects)} objetos')

    def refresh_controls(self):
        ready = self.model is not None
        chosen = ready and self.selected is not None
        self.save_button.setEnabled(ready)
        self.undo_button.setEnabled(ready and bool(self.model.undo_stack))
        self.redo_button.setEnabled(ready and bool(self.model.redo_stack))
        for b in (self.edit_button, self.delete_button, self.move_button):
            b.setEnabled(chosen)
        if ready:
            dirty = self.model.dirty
            self.filename.setText(self.model.source.name + ('  • Sin guardar' if dirty else ''))
            self.setWindowTitle(('• ' if dirty else '') + self.model.source.name + ' — Faro PDF')
        if not chosen:
            self.selection_title.setText('Selecciona un objeto' if self.mode != 'read' else 'Modo lectura')
            self.details.setText('Haz clic sobre el texto para situar el cursor y escribir.' if self.mode == 'text' else
                                 'Selecciona una imagen y arrástrala para moverla.' if self.mode == 'images' else
                                 'Haz clic en la página para añadir texto.' if self.mode == 'add' else
                                 'Navega entre páginas, ajusta el zoom o cambia a un modo de edición.')

    def set_mode(self, mode):
        if self.inline.active and not self.inline.commit():
            self.mode_buttons[self.mode].setChecked(True)
            return
        self.inline.cancel()
        self.mode = mode
        self.mode_buttons[mode].setChecked(True)
        self.mode_picker.setText(self.mode_titles[mode])
        self.canvas.setDragMode(QGraphicsView.DragMode.ScrollHandDrag if mode == 'read' else QGraphicsView.DragMode.NoDrag)
        self.canvas.setCursor(Qt.CursorShape.CrossCursor if mode == 'add' else Qt.CursorShape.ArrowCursor)
        self.select(None)
        self.canvas.refresh_text_boxes()
        if mode == 'add':
            self.statusBar().showMessage('Arrastra un cuadro en la hoja y escribe dentro. Fuente y tamaño aparecen en la barra de formato.',15000)

    def select(self, index):
        if self.canvas.text_grip:
            self.canvas.scene().removeItem(self.canvas.text_grip);self.canvas.text_grip=None
        for _,item in self.canvas.resize_handles:self.canvas.scene().removeItem(item)
        self.canvas.resize_handles=[]
        self.selected = index
        if self.canvas.outline:
            self.canvas.scene().removeItem(self.canvas.outline)
            self.canvas.outline = None
        self.refresh_controls()
        if index is None:
            return
        info = self.model.info(index)
        run=self.model.text_run(index) if info['type']==TEXT else None
        self.canvas.select_outline(run['bounds'] if run else info['bounds'])
        native = info['type'] == TEXT
        self.selection_title.setText('Texto editable' if native else 'Imagen seleccionada')
        left, bottom, right, top = info['bounds']
        effective_size = info['size']*math.hypot(info['matrix'][2], info['matrix'][3]) if native else None
        self.details.setText((f"{effective_size:.1f} pt\n{info['text'][:180]}" if native else
                             'Puede ser un logotipo, una foto o texto dibujado como píxeles. Arrástralo en modo Imágenes.') +
                            f'\n\n{right-left:.1f} × {top-bottom:.1f} pt\nPosición: {left:.1f}, {bottom:.1f}')
        if native:
            self.details.setText(self.details.text()+'\n\n'+self.inline.source_description(info))
        self.edit_button.setText('Editar en la página' if native else 'Acerca de este bloque')

    def change(self, callback):
        if not self.model:
            return
        try:
            callback()
            self.render_page()
            self.statusBar().showMessage('Cambio aplicado. Puedes deshacerlo o guardar una copia.', 6000)
        except Exception as error:
            self.error(error)
            self.render_page()

    def edit_selected(self):
        if self.selected is None:
            return
        self.inline.begin(self.selected)
        if not self.inline.active:
            self.statusBar().showMessage(self.inline.status.text(), 16000)

    def set_edit_shortcuts(self, enabled):
        if hasattr(self, 'shortcut_actions'):
            self.shortcut_actions['Delete'].setEnabled(enabled)

    def add_text(self, x, y, box=None):
        if not self.model:return
        defaults=getattr(self,'text_defaults',{'size':12,'face':None})
        try:self.model.add_text('Texto',x,y,defaults['size'])
        except Exception as error:self.error(error);return
        self.render_page();self.set_mode('text')
        index=max(i for i,o in enumerate(self.model.objects) if o.type==TEXT)
        self.select(index);self.inline.begin(index)
        if not self.inline.active:return
        self.inline.session['newly_created']=True
        self.inline.session['box_bounds']=box or (x,y-65,min(self.model.page.get_width(),x+220),y)
        if defaults.get('face'):
            choice=self.inline.fonts.findData(defaults['face'])
            if choice>=0:self.inline.fonts.setCurrentIndex(choice)
        self.inline.select_all();self.inline.refresh_preview();self.focus_editor()
        self.statusBar().showMessage('Escribe directamente. Enter añade líneas; ajusta fuente y tamaño en las opciones. Arrastra el tirador para mover el cuadro.',15000)

    def choose_image(self):
        if not self.model:return
        path,_=QFileDialog.getOpenFileName(self,'Insertar imagen',str(Path.home()/'Downloads'),'Imágenes (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)')
        if not path:
            self.mode_buttons[self.mode].setChecked(True);return
        self.pending_image=path;self.set_mode('imageadd')
        self.canvas.setCursor(Qt.CursorShape.CrossCursor)
        self.statusBar().showMessage('Haz clic en la página para colocar la imagen.',15000)

    def place_image(self,x,y):
        path=getattr(self,'pending_image',None)
        if not path:return
        dialog=QDialog(self);dialog.setWindowTitle('Tamaño de la imagen')
        layout=QFormLayout(dialog);width=QDoubleSpinBox();width.setRange(5,2000)
        width.setValue(min(180,self.model.page.get_width()*.35));width.setSuffix(' pt')
        layout.addRow('Ancho (se conserva la proporción)',width)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.change(lambda:self.model.add_image(path,x,y,width.value()))
            self.set_mode('images')

    def insert_pdf_dialog(self):
        if not self.model:return
        if self.inline.active and not self.inline.commit():return
        paths,_=QFileDialog.getOpenFileNames(self,'Seleccionar PDFs para combinar',str(Path.home()/'Downloads'),'PDF (*.pdf)')
        if not paths:return
        dialog=QDialog(self);dialog.setWindowTitle('Insertar páginas PDF');dialog.resize(550,420)
        layout=QVBoxLayout(dialog);layout.addWidget(QLabel('Arrastra los documentos para ordenar sus páginas:'))
        files=QListWidget();files.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        for path in paths:
            item=QListWidgetItem(Path(path).name);item.setData(Qt.ItemDataRole.UserRole,path);item.setToolTip(path);files.addItem(item)
        layout.addWidget(files)
        position=QComboBox();position.addItems(['Al final','Al inicio','Después de la página indicada'])
        layout.addWidget(position);number=QSpinBox();number.setRange(1,len(self.model.doc));number.setValue(self.model.index+1)
        number.setPrefix('Página ');number.setVisible(False);layout.addWidget(number)
        position.currentIndexChanged.connect(lambda i:number.setVisible(i==2))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            ordered=[files.item(i).data(Qt.ItemDataRole.UserRole) for i in range(files.count())]
            at=len(self.model.doc) if position.currentIndex()==0 else 0 if position.currentIndex()==1 else number.value()
            self.change(lambda:self.model.insert_pdfs(ordered,at))

    def move_page_dialog(self):
        if not self.model:return
        if self.inline.active and not self.inline.commit():return
        destination,ok=QInputDialog.getInt(self,'Mover página',f'Mover la página {self.model.index+1} a la posición:',self.model.index+1,1,len(self.model.doc))
        if ok:self.change(lambda:self.model.move_page(self.model.index,destination-1))

    def delete_page_dialog(self):
        if not self.model:return
        if self.inline.active and not self.inline.commit():return
        if len(self.model.doc)<=1:
            self.statusBar().showMessage('El PDF debe conservar al menos una página.',10000);return
        result=QMessageBox.question(self,'Borrar página completa',f'¿Borrar la página {self.model.index+1}? Puedes recuperarla con Deshacer.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)
        if result==QMessageBox.StandardButton.Yes:self.change(lambda:self.model.delete_page(self.model.index))

    def delete_selected(self):
        if self.inline.active:
            cursor = self.inline.editor.textCursor()
            cursor.deleteChar()
            self.inline.editor.setTextCursor(cursor)
            return
        if self.selected is not None:
            self.change(lambda: self.model.delete(self.selected))

    def undo(self):
        if self.inline.active:
            self.inline.editor.document().undo()
            return
        if self.model and self.model.undo_stack:
            self.change(self.model.undo)

    def redo(self):
        if self.inline.active:
            self.inline.editor.document().redo()
            return
        if self.model and self.model.redo_stack:
            self.change(self.model.redo)

    def save(self):
        if self.inline.active and not self.inline.commit():
            return False
        if not self.model:
            return False
        if not self.model.saved_path:
            return self.save_as()
        return self.write_file(self.model.saved_path)

    def save_as(self):
        if self.inline.active and not self.inline.commit():
            return False
        if not self.model:
            return False
        default = self.model.source.with_name(self.model.source.stem + '-editado.pdf')
        path, _ = QFileDialog.getSaveFileName(self, 'Guardar una copia del PDF', str(default), 'PDF (*.pdf)')
        if not path:
            return False
        if not path.lower().endswith('.pdf'):
            path += '.pdf'
        return self.write_file(path)

    def write_file(self, path):
        try:
            self.model.save(path)
            self.refresh_controls()
            self.statusBar().showMessage(f'Guardado: {path}', 12000)
            return True
        except Exception as error:
            self.error(error)
            return False

    def change_zoom(self, factor):
        if self.inline.active and not self.inline.commit():
            return
        if self.model:
            self.fit = False
            self.zoom = max(.2, min(4, self.zoom*factor))
            self.render_page()

    def fit_width(self):
        if self.inline.active and not self.inline.commit():
            return
        self.fit = True
        self.render_page()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.model and self.fit and not self.inline.active and not self.inline.busy:
            QTimer.singleShot(0, self.render_page)

    def closeEvent(self, event):
        if any(worker.isRunning() for worker in self.inline.workers):
            self.statusBar().showMessage('Espera a que termine el reconocimiento local antes de cerrar.', 8000)
            event.ignore()
            return
        if self.confirm_discard():
            if self.model:
                self.model.close()
            event.accept()
        else:
            event.ignore()

    def font_report(self):
        if not self.model:
            return
        if self.inline.active and not self.inline.commit():
            return
        catalog = self.inline.catalog
        fonts = {}
        for i in range(len(self.model.doc)):
            page = self.model.doc[i]
            try:
                for obj in page.get_objects(max_depth=10):
                    if obj.type != TEXT:
                        continue
                    font = obj.get_font()
                    name = font.get_base_name()
                    for declared in self.model._font_resources.get(i, []):
                        if declared.split('+')[-1] == name:
                            name = declared
                            break
                    row = fonts.setdefault(name, dict(embedded=font.is_embedded, family=font.get_family_name(),
                                                     weight=font.get_weight(), sizes=set()))
                    matrix = obj.get_matrix().get()
                    row['sizes'].add(round(obj.get_font_size()*math.hypot(matrix[2], matrix[3]), 2))
            finally:
                page.close()
        dialog = QDialog(self)
        dialog.setWindowTitle('Fuentes del PDF')
        dialog.resize(900, 430)
        layout = QVBoxLayout(dialog)
        if not fonts:
            label = QLabel('Este PDF no contiene fuentes de texto nativo. Las letras están dibujadas como imágenes. Su conversión a texto está bloqueada para conservar la tipografía visible.')
            label.setWordWrap(True)
            layout.addWidget(label)
        else:
            table = QTableWidget(len(fonts), 5)
            table.setHorizontalHeaderLabels(['Fuente del PDF', 'Incrustada', 'Instalada', 'Tamaños (pt)', 'Alternativa local'])
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            for r, (name, info) in enumerate(fonts.items()):
                exact = catalog.matching(name, info['weight'] >= 600)
                alternatives = catalog.alternatives(info['family'] or name, info['weight'] >= 600)
                values = [name, 'Sí' if info['embedded'] else 'No', 'Sí' if exact else 'No',
                          ', '.join(f'{n:g}' for n in sorted(info['sizes'])), alternatives[0].name if alternatives else 'Importar TTF']
                for column, value in enumerate(values):
                    table.setItem(r, column, QTableWidgetItem(value))
            layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('file', nargs='?')
    parser.add_argument('--screenshot')
    parser.add_argument('--edit-object', type=int)
    parser.add_argument('--self-test', metavar='REPORT', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_test:
        from packaging_smoke import run
        return run(Path(args.self_test))
    app = QApplication(sys.argv[:1])
    if sys.platform == 'win32':
        C.windll.shell32.SetCurrentProcessExplicitAppUserModelID('FaroPDF.Desktop')
    # Explicit font loading also supports restricted Windows font enumeration.
    for name in ('segoeui.ttf', 'segoeuib.ttf'):
        path = Path('C:/Windows/Fonts') / name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont('Segoe UI', 10))
    app.setApplicationName('Faro PDF')
    app.setApplicationVersion(VERSION)
    app.setWindowIcon(QIcon(str(ROOT / 'assets' / 'faro.ico')))
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    window = Window()
    if args.screenshot:
        window.show()
    else:
        window.showMaximized()
    opening = args.file
    if opening and Path(opening).exists():
        def open_requested():
            window.open_file(opening)
            if args.edit_object is not None and window.model and 0 <= args.edit_object < len(window.model.objects):
                window.set_mode('text')
                window.select(args.edit_object)
                window.inline.begin(args.edit_object)
        QTimer.singleShot(100, open_requested)
    if args.screenshot:
        capture_attempts = [0]
        def capture():
            if (window.inline.busy or window.inline.workers) and capture_attempts[0] < 65:
                capture_attempts[0] += 1
                QTimer.singleShot(1000, capture)
                return
            window.grab().save(args.screenshot)
            window.inline.cancel()
            app.quit()
        QTimer.singleShot(2500, capture)
    sys.exit(app.exec())


if __name__ == '__main__':
    sys.exit(main())
