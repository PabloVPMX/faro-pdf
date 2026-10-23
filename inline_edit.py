"""Caret editing on the PDF canvas, with explicit font provenance."""
import hashlib
import ctypes as C
import math
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import Qt, QTimer, QPointF, QByteArray, QRectF
from PySide6.QtGui import QFont, QFontDatabase, QFontMetricsF, QColor, QPen, QTransform, QTextCursor, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QGraphicsTextItem, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDoubleSpinBox, QPushButton, QFileDialog, QLayout

from engine import TEXT, IMAGE, pdf, comparable_text, align_character_geometry
from typography import Catalog, clean_name, read_face

ROOT = Path(__file__).resolve().parent


class CaretItem(QGraphicsTextItem):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.document().setDocumentMargin(0)
        self.setZValue(30)

    def boundingRect(self):
        rect = super().boundingRect()
        if self.controller.editor is self and self.controller.session:
            source = self.controller.source_rect()
            if not source.isNull():
                rect = rect.united(self.mapRectFromScene(source.adjusted(-8,-12,8,12)))
        return rect

    def paint(self, painter, option, widget=None):
        if self.controller.pristine:
            if not self.controller.suppress_decorations:
                self.controller.paint_source_caret(painter)
            return
        painter.save()
        painter.setPen(QPen(QColor('#07847e'), 1, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.boundingRect().adjusted(-3, -2, 3, 2))
        painter.restore()
        super().paint(painter, option, widget)

    def mousePressEvent(self, event):
        if self.controller.pristine:
            self.controller.place_source_cursor(event.scenePos(), bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.controller.pristine and event.buttons() & Qt.MouseButton.LeftButton:
            self.controller.place_source_cursor(event.scenePos(), True)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.controller.pristine:
            self.controller.place_source_cursor(event.scenePos())
            cursor = self.textCursor()
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
            self.setTextCursor(cursor)
            self.update()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            QTimer.singleShot(0, self.controller.cancel)
            event.accept()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            QTimer.singleShot(0, self.controller.commit)
            event.accept()
        else:
            cursor=self.textCursor()
            cursor.beginEditBlock()
            try:
                super().keyPressEvent(event)
            finally:
                cursor.endEditBlock()


class InlineController:
    def __init__(self, window, right):
        self.window = window
        self.catalog = Catalog()
        self.editor = None
        self.session = None
        self.busy = False
        self.generation = 0
        self.workers = []
        self.loaded_fonts = {}
        self.pristine = True
        self.suppress_decorations = False
        self.background_item = None
        self.caret_visible=True
        self.caret_timer=QTimer(window)
        self.caret_timer.setInterval(550)
        self.caret_timer.timeout.connect(self.blink_caret)
        self.panel = QFrame()
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(0, 4, 0, 8)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.status = QLabel('')
        self.status.setWordWrap(True)
        self.status.setObjectName('muted')
        layout.addWidget(self.status)
        self.fonts = QComboBox()
        self.fonts.setToolTip('Original, misma familia instalada o una alternativa elegida por ti.')
        self.fonts.currentIndexChanged.connect(self.update_style)
        layout.addWidget(self.fonts)
        self.size = QDoubleSpinBox()
        self.size.setDecimals(2)
        self.size.setRange(3, 160)
        self.size.setSuffix(' pt')
        self.size.valueChanged.connect(self.update_style)
        layout.addWidget(self.size)
        buttons = QHBoxLayout()
        self.apply = QPushButton('Aplicar')
        self.apply.setObjectName('primary')
        self.apply.clicked.connect(lambda: self.commit(force=True))
        cancel = QPushButton('Cancelar')
        cancel.clicked.connect(self.cancel)
        buttons.addWidget(self.apply)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        links = QVBoxLayout()
        imported = QPushButton('Importar TTF')
        imported.clicked.connect(self.import_font)
        download = QPushButton('Buscar / descargar')
        download.setToolTip('Abre Google Fonts para buscar una descarga. Después puedes importar el TTF.')
        download.clicked.connect(self.find_font)
        links.addWidget(imported)
        links.addWidget(download)
        layout.addLayout(links)
        for control in (self.fonts, self.size, self.apply, cancel, imported, download):
            control.setMinimumHeight(32)
        note = QLabel('Enter añade una línea · Ctrl+Enter aplica · Esc cancela\nTambién se aplica al hacer clic fuera del bloque.')
        note.setObjectName('muted')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.edit_controls = (self.fonts, self.size, self.apply, cancel, imported, download, note)
        right.addWidget(self.panel)
        self.panel.hide()

    @property
    def active(self):
        return self.editor is not None

    def blink_caret(self):
        self.caret_visible=not self.caret_visible
        if self.editor:self.editor.update()

    def reset_caret(self,*_):
        self.caret_visible=True
        if self.editor:
            self.caret_timer.start();self.editor.update()

    def source_description(self, info):
        if info['type'] != TEXT:
            return 'Texto en una imagen: no hay fuente original. Se conserva sin convertir para evitar cambios de tipografía.'
        name = clean_name(info['font'])
        exact = self.catalog.matching(name, info.get('weight', 400) >= 600, info.get('italic', False))
        if info['embedded']:
            return f"{name} · Incrustada en el PDF" + (' (subconjunto)' if info['subset'] else '')
        if exact:
            return f'{name} · Familia disponible en Windows'
        return f'{name} · No está instalada. Elige una sustituta o importa la original.'

    def begin(self, index, click=None):
        if self.busy:
            return
        if self.active and not self.commit():
            return
        model = self.window.model
        info = model.info(index)
        run=model.text_run(index) if info['type']==TEXT else None
        indices=run['indices'] if run else [index]
        index=indices[0]
        if len(indices)>1:
            info=model.info(index)
            info['bounds']=run['bounds']
            info['text']=''.join(r['character'] for r in run['characters'])
        if run and run.get('layout'):
            info['text']=run['text'];info['bounds']=run['bounds'];info['matrix']=run['matrix']
        self.generation += 1
        for control in self.edit_controls:
            control.setVisible(info['type'] == TEXT)
        self.panel.setMinimumHeight(290 if info['type'] == TEXT else 70)
        self.fonts.setEnabled(info['type'] == TEXT)
        self.size.setEnabled(info['type'] == TEXT)
        self.apply.setEnabled(False)
        if info['type'] != TEXT:
            self.session = None
            self.fonts.clear()
            self.panel.show()
            self.status.setText(self.source_description(info))
            self.window.statusBar().showMessage('Imagen conservada. No se sustituirá por texto con una fuente aproximada.', 12000)
            return
        self.session = dict(index=index, info=info, version=model.current_version,
                            page=model.index, click=click, indices=list(indices),layout=run.get('layout') if run else None,
                            end_origin=run.get('end_origin') if run else None)
        if run and run.get('box_bounds'):self.session['box_bounds']=run['box_bounds']
        self.panel.show()
        self.status.setText(self.source_description(info))
        if info['type'] == TEXT:
            self._start_native()

    def _start_native(self):
        info = self.session['info']
        bold, italic = info.get('weight', 400) >= 600, info.get('italic', False)
        exact = self.catalog.matching(info['font'], bold, italic)
        self.session.update(text=info['text'], color=info.get('color', (0, 0, 0)),
                            original_available=info['embedded'] or bool(exact))
        self.fonts.blockSignals(True)
        self.fonts.clear()
        self.fonts.addItem('Original · '+clean_name(info['font']), None)
        self.fonts.model().item(0).setEnabled(self.session['original_available'])
        alternatives = self.catalog.alternatives(info['font'], bold, italic)
        for face in alternatives:
            self.fonts.addItem(('Instalada · ' if exact else 'Similar al aspecto · ')+face.name, face.path)
        self._add_all_faces()
        self.fonts.setCurrentIndex(0)
        self.fonts.blockSignals(False)
        _, _, c, d, _, _ = info['matrix']
        self.session['size_scale'] = math.hypot(c, d) or 1
        self.size.blockSignals(True)
        self.size.setValue(info['size']*self.session['size_scale'])
        self.size.blockSignals(False)
        self.session['start_size'] = self.size.value()
        self.session['start_face'] = None
        if self.session['original_available']:
            preflight = self.window.model.native_preflight.get(self.window.model.index, {})
            if preflight.get('error'):
                self.status.setText('La edición con la fuente original está bloqueada en esta página: '+preflight['error'])
            else:
                self._show_caret()
        else:
            self.status.setText('La fuente original no está disponible. El bloque conserva su aspecto original. Importa la fuente o elige explícitamente otra para iniciar la edición.')

    def _add_all_faces(self):
        paths = {self.fonts.itemData(i) for i in range(self.fonts.count())}
        for face in self.catalog.faces:
            if not face.restricted and face.path not in paths:
                self.fonts.addItem(face.name, face.path)
                paths.add(face.path)

    def raw_size(self):
        return self.size.value()/self.session.get('size_scale', 1)

    def _family(self):
        path = self.fonts.currentData()
        if path:
            if path not in self.loaded_fonts:
                font_id = QFontDatabase.addApplicationFont(path)
                families = QFontDatabase.applicationFontFamilies(font_id)
                self.loaded_fonts[path] = families[0] if families else read_face(path).family
            face = read_face(path)
            return self.loaded_fonts[path], face.bold, face.italic
        info = self.session['info']
        if not self.session['original_available']:
            raise ValueError('La fuente original no está disponible. Se requiere una elección explícita para editar.')
        data = self.window.model.font_data(self.session['index'])
        if data:
            digest = hashlib.sha256(data).hexdigest()
            if digest not in self.loaded_fonts:
                font_id = QFontDatabase.addApplicationFontFromData(QByteArray(data))
                families = QFontDatabase.applicationFontFamilies(font_id)
                self.loaded_fonts[digest] = families[0] if families else ''
            if self.loaded_fonts[digest]:
                return self.loaded_fonts[digest], info.get('weight', 400) >= 600, info.get('italic', False)
        exact = self.catalog.matching(info['font'], info.get('weight', 400) >= 600, info.get('italic', False))
        if exact:
            face = exact[0]
            font_id = QFontDatabase.addApplicationFont(face.path)
            families = QFontDatabase.applicationFontFamilies(font_id)
            return families[0] if families else face.family, face.bold, face.italic
        raise ValueError('No se pudo cargar la fuente original para la edición. Se conserva el bloque sin cambios; importa la fuente original para continuar.')

    def _show_caret(self):
        from app import pixmap
        model, canvas = self.window.model, self.window.canvas
        if self.fonts.currentData():
            try:self._family()
            except ValueError as error:
                self.status.setText(str(error));self.apply.setEnabled(False);return
        run=model.text_run(self.session['index'])
        characters=run['characters'] if run and run.get('layout') else [row for index in self.session['indices'] for row in model.character_geometry(index)]
        characters = self.complete_geometry(characters, self.session['text'])
        if characters is None:
            self.status.setText('La geometría de este bloque no se corresponde de forma segura con sus caracteres. Se conserva el original; la edición está bloqueada.')
            self.apply.setEnabled(False)
            return
        self.session['characters'] = characters
        self.session['original_characters'] = characters
        self.session['original_end_origin']=self.session.get('end_origin')
        self.last_valid_text=self.session['text']
        self.last_valid_face=self.fonts.currentData()
        self.last_valid_size=self.size.value()
        self.original_background = pixmap(model.page, self.window.zoom)
        objects=[model.objects[i] for i in self.session['indices']]
        disabled=[]
        try:
            for obj in objects:
                if not pdf.raw.FPDFPageObj_SetIsActive(obj, False):
                    self.status.setText('No se pudo preparar la vista de edición.')
                    return
                disabled.append(obj)
            self.changed_background = pixmap(model.page, self.window.zoom)
        finally:
            for obj in disabled: pdf.raw.FPDFPageObj_SetIsActive(obj, True)
        self.pristine = True
        canvas.display(self.original_background)
        self.background_item = canvas.page_item
        canvas.select_outline(self.session['info']['bounds'])
        self.editor = CaretItem(self)
        self.editor.setPlainText(self.session['text'])
        self.editor.document().contentsChanged.connect(self.refresh_preview)
        self.editor.document().cursorPositionChanged.connect(self.reset_caret)
        self.editor.document().undoAvailable.connect(self.window.undo_button.setEnabled)
        self.editor.document().redoAvailable.connect(self.window.redo_button.setEnabled)
        canvas.scene().addItem(self.editor)
        self.window.text_format.show()
        self.reset_caret()
        self.apply.setEnabled(True)
        self.update_style()
        self.editor.setFocus(Qt.FocusReason.MouseFocusReason)
        canvas.setFocus()
        click = self.session.get('click')
        if click is not None:
            self.place_source_cursor(click)
        self.window.set_edit_shortcuts(False)
        self.window.move_group.hide()
        self.window.delete_button.hide()
        self.window.edit_button.hide()
        self.window.selection_title.setText('Editando texto')
        self.window.details.setText('Haz clic entre las letras, selecciona, borra o escribe. El documento no cambia hasta aplicar.')
        self.window.key_hint.setText('Edición directa\nCtrl+A   Seleccionar texto\nCtrl+Z   Deshacer escritura\nEnter   Nueva línea\nCtrl+Enter   Aplicar al PDF\nEsc   Cancelar')
        self.window.statusBar().showMessage('Edición sobre la fuente y los recursos originales del PDF. Los caracteres no disponibles se bloquean.', 12000)

    @staticmethod
    def complete_geometry(characters, value):
        aligned=align_character_geometry(characters,value)
        if aligned is not None: return aligned
        actual = ''.join(row['character'] for row in characters)
        if comparable_text(actual) == comparable_text(value):
            return characters
        # PDFium extraction may add terminal whitespace with no glyph object.
        # It is only a cursor position; it must never synthesize visible letters.
        if characters and value.startswith(actual) and value[len(actual):].strip() == '':
            result = list(characters)
            last = characters[-1]
            x, y = last['bounds'][1], last['origin'][1]
            for character in value[len(actual):]:
                result.append(dict(character=character, origin=(x,y), bounds=(x,x,y,y)))
            return result
        if not value:
            return []
        return None

    def refresh_preview(self):
        if not self.editor or not self.session or getattr(self,'rejecting_input',False):
            return
        previous_characters=self.session['characters']
        previous_background=self.background_item.pixmap()
        previous_end=self.session.get('end_origin')
        self.pristine = (self.editor.toPlainText() == self.session['text']
                         and self.fonts.currentData() is None
                         and abs(self.size.value()-self.session['start_size']) < .01)
        self.preview_error = None
        self.apply.setEnabled(True)
        if self.pristine:
            self.editor.prepareGeometryChange()
            self.session['characters'] = self.session['original_characters']
            self.background_item.setPixmap(self.original_background)
            self.session['end_origin']=self.session.get('original_end_origin')
        elif self.session.get('box_bounds') or self.session.get('layout') or self.fonts.currentData() or '\n' in self.editor.toPlainText() or abs(self.size.value()-self.session['start_size'])>=.01:
            self.pristine=True
            candidate=page=textpage=None
            try:
                from text_layout import block_records,block_geometry
                from app import pixmap
                model=self.window.model
                data,key=model.layout_text_bytes(self.session['indices'],self.editor.toPlainText(),self.raw_size(),self.fonts.currentData(),self.session['color'],self.session.get('new_layout_id'),self.session.get('box_bounds'))
                self.session['new_layout_id']=key
                candidate=pdf.PdfDocument(data);page=candidate[model.index];textpage=page.get_textpage()
                objects=[o for o in page.get_objects(max_depth=0,textpage=textpage) if o.type==TEXT]
                record=block_records(data,model.index).get(key)
                rows,end=block_geometry(model,textpage,objects,record) if record else ([],self.session['info']['matrix'][4:6])
                self.editor.prepareGeometryChange();self.session['characters']=rows;self.session['end_origin']=end
                self.background_item.setPixmap(pixmap(page,self.window.zoom))
                self.status.setText(self.source_description(self.session['info']) if not self.fonts.currentData() else 'Fuente elegida: '+read_face(self.fonts.currentData()).name)
            except Exception as error:
                message='Cambio rechazado; puedes seguir editando. '+str(error)
                self.status.setText(message);self.window.statusBar().showMessage(message,16000)
                self.rejecting_input=True
                try:
                    self.fonts.blockSignals(True);self.fonts.setCurrentIndex(self.fonts.findData(self.last_valid_face));self.fonts.blockSignals(False)
                    self.size.blockSignals(True);self.size.setValue(self.last_valid_size);self.size.blockSignals(False)
                    if self.editor.toPlainText()!=self.last_valid_text:
                        if self.editor.document().isUndoAvailable():self.editor.document().undo()
                        else:self.editor.setPlainText(self.last_valid_text)
                finally:self.rejecting_input=False
                self.session['characters']=previous_characters;self.session['end_origin']=previous_end
                self.background_item.setPixmap(previous_background);self.preview_error=None;self.apply.setEnabled(True)
            finally:
                if textpage is not None:textpage.close()
                if page is not None:page.close()
                if candidate is not None:candidate.close()
        elif self.fonts.currentData() is None:
            self.pristine = True  # Paint caret/selection only, never Qt glyphs.
            candidate = page = textpage = None
            try:
                from app import pixmap
                model = self.window.model
                value = self.editor.toPlainText()
                multiple=len(self.session['indices'])>1
                if multiple:
                    if abs(self.size.value()-self.session['start_size'])>=.01:
                        raise ValueError('Mantén el tamaño original para conservar los fragmentos de esta línea.')
                    data=model.native_run_bytes(self.session['indices'],self.session['text'],value)
                else:
                    data = model.native_text_bytes(self.session['index'], value, self.raw_size())
                candidate = pdf.PdfDocument(data)
                page = candidate[model.index]
                textpage = page.get_textpage()
                ordinal = sum(obj.type == TEXT for obj in model.objects[:self.session['index']])
                objects = [obj for obj in page.get_objects(max_depth=0, textpage=textpage) if obj.type == TEXT]
                count=len(self.session['indices'])-(sum(o.type==TEXT for o in model.objects)-len(objects))
                selected=objects[ordinal:ordinal+count]
                targets={C.cast(o.raw,C.c_void_p).value for o in selected}
                geometry=model.page_character_geometry(textpage,targets)
                rows=[row for obj in selected for row in geometry.get(C.cast(obj.raw,C.c_void_p).value,[])]
                rows = self.complete_geometry(rows, value)
                if rows is None:
                    raise ValueError('No se puede situar el cursor con fidelidad para este cambio. El original se conserva.')
                self.editor.prepareGeometryChange()
                self.session['characters'] = rows
                self.background_item.setPixmap(pixmap(page, self.window.zoom))
                self.status.setText(self.source_description(self.session['info']))
                self.status.setStyleSheet('')
            except Exception as error:
                message='Cambio rechazado; puedes seguir editando o seleccionar otro bloque. '+str(error)
                self.status.setText(message)
                self.window.statusBar().showMessage(message, 20000)
                self.status.setStyleSheet('color: #b04445;')
                # Reject only this input operation. Keeping invalid text in
                # the editor made every later click attempt a failing commit,
                # trapping the user in the same block indefinitely.
                self.rejecting_input=True
                try:
                    if self.editor.document().isUndoAvailable():
                        self.editor.document().undo()
                    else:
                        self.editor.setPlainText(self.last_valid_text)
                finally:
                    self.rejecting_input=False
                self.preview_error=None
                self.apply.setEnabled(True)
                self.session['characters'] = previous_characters
                self.background_item.setPixmap(previous_background)
            finally:
                if textpage is not None: textpage.close()
                if page is not None: page.close()
                if candidate is not None: candidate.close()
        else:
            self.background_item.setPixmap(self.changed_background)
        self.last_valid_text=self.editor.toPlainText()
        self.last_valid_face=self.fonts.currentData();self.last_valid_size=self.size.value()
        if self.window.canvas.outline and not self.source_rect().isNull():
            bounds = self.session.get('box_bounds')
            rect = self.source_rect()
            if bounds:
                rect = rect.united(self.window.canvas.object_rect(bounds))
            self.window.canvas.outline.setRect(rect.adjusted(-2,-2,2,2))
        self.reset_caret()

    def source_cursor_points(self):
        points = [QPointF(*self.window.canvas.to_scene(*row['origin'])) for row in self.session['characters']]
        if points:
            last = self.session['characters'][-1]
            # End-of-line caret uses the final source ink edge, not Qt advances.
            end=self.session.get('end_origin') or (last['bounds'][1],last['origin'][1])
            points.append(QPointF(*self.window.canvas.to_scene(*end)))
        return points

    def source_rect(self):
        if not self.session:
            return QRectF()
        rect = QRectF()
        for row in self.session.get('characters', []):
            left, right, bottom, top = row['bounds']
            a = QPointF(*self.window.canvas.to_scene(left, top))
            b = QPointF(*self.window.canvas.to_scene(right, bottom))
            one = QRectF(a,b).normalized()
            if one.width() > 0 and one.height() > 0:
                rect = one if rect.isNull() else rect.united(one)
        if self.session.get('end_origin'):
            point=QPointF(*self.window.canvas.to_scene(*self.session['end_origin']))
            h=self.size.value()*self.window.zoom
            rect=rect.united(QRectF(point.x(),point.y()-h,max(8,h*.5),h+2))
        if self.session.get('box_bounds'):
            rect=rect.united(self.window.canvas.object_rect(self.session['box_bounds']))
        return rect

    def source_contains(self,position):
        if not self.session:return False
        for row in self.session.get('characters',[]):
            l,r,b,t=row['bounds']
            if r>l and t>b and self.window.canvas.object_rect((l,b,r,t)).adjusted(-.5,-.5,.5,.5).contains(position):return True
        return False

    def select_word(self, position):
        # A word click belongs to the glyph under the pointer, even on its
        # right half; the nearest insertion boundary could be the next space.
        rows=self.session['characters']
        if not rows: return
        def distance(row):
            left,right,bottom,top=row['bounds']
            rect=self.window.canvas.object_rect((left,bottom,right,top))
            dx=max(rect.left()-position.x(),0,position.x()-rect.right())
            dy=max(rect.top()-position.y(),0,position.y()-rect.bottom())
            return dx*dx+dy*dy
        index=min(range(len(rows)),key=lambda i:distance(rows[i]))
        cursor = self.editor.textCursor()
        cursor.setPosition(len(self.editor.toPlainText()[:index].encode('utf-16-le'))//2)
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        self.editor.setTextCursor(cursor)
        self.editor.update()

    def select_all(self):
        if self.editor:
            cursor = self.editor.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            self.editor.setTextCursor(cursor)
            self.editor.update()

    def place_source_cursor(self, scene_position, keep_anchor=False):
        points = self.source_cursor_points()
        if not points:
            return
        position = min(range(len(points)), key=lambda i: (points[i].x()-scene_position.x())**2+(points[i].y()-scene_position.y())**2)
        cursor = self.editor.textCursor()
        # QTextCursor counts UTF-16 units, whereas PDFium exposes code points.
        value=self.editor.toPlainText()
        utf16=len(value[:position].encode('utf-16-le'))//2
        cursor.setPosition(min(utf16, self.editor.document().characterCount()-1),
                           QTextCursor.MoveMode.KeepAnchor if keep_anchor else QTextCursor.MoveMode.MoveAnchor)
        self.editor.setTextCursor(cursor)
        self.reset_caret()

    def paint_source_caret(self, painter):
        cursor = self.editor.textCursor()
        painter.save()
        if cursor.hasSelection():
            value=self.editor.toPlainText().encode('utf-16-le')
            start=len(value[:cursor.selectionStart()*2].decode('utf-16-le',errors='ignore'))
            end=len(value[:cursor.selectionEnd()*2].decode('utf-16-le',errors='ignore'))
            for row in self.session['characters'][start:end]:
                left, right, bottom, top = row['bounds']
                first = self.editor.mapFromScene(QPointF(*self.window.canvas.to_scene(left, top)))
                last = self.editor.mapFromScene(QPointF(*self.window.canvas.to_scene(right, bottom)))
                painter.fillRect(QRectF(first, last).normalized().adjusted(-.5,-1,.5,1), QColor(66, 133, 244, 88))
        elif self.caret_visible and (self.editor.hasFocus() or self.window.canvas.hasFocus()):
            points = self.source_cursor_points()
            if points:
                index=len(self.editor.toPlainText().encode('utf-16-le')[:cursor.position()*2].decode('utf-16-le',errors='ignore'))
                point=points[min(index,len(points)-1)]
                _,_,c,d,e,f=self.session['info']['matrix']
                origin=QPointF(*self.window.canvas.to_scene(e,f))
                axis=QPointF(*self.window.canvas.to_scene(e+c,f+d))-origin
                length=math.hypot(axis.x(),axis.y())
                direction=axis/length if length else QPointF(0,-1)
                start=self.editor.mapFromScene(point-direction*2)
                end=self.editor.mapFromScene(point+direction*(self.size.value()*self.window.zoom*.85))
                for color,width in (('#ffffff',4),('#111111',2)):
                    pen=QPen(QColor(color),width);pen.setCosmetic(True)
                    painter.setPen(pen);painter.drawLine(start,end)
        painter.restore()

    def update_style(self, *_):
        if not self.session:
            return
        if not self.editor:
            if self.fonts.currentData():
                self._show_caret()
            return
        # Original glyphs are painted by PDFium, and caret/selection positions
        # come from PDF geometry. Qt only stores invisible editable characters;
        # loading a raw embedded CFF font into Windows is neither needed nor
        # reliable. This UI font is never written to the PDF or painted over it.
        family,bold,italic=self._family() if self.fonts.currentData() else ('Segoe UI',False,False)
        self.status.setStyleSheet('')
        if self.fonts.currentData():
            self.status.setText('Fuente elegida: '+read_face(self.fonts.currentData()).name+'. Se incrustará en el PDF.')
        else:
            self.status.setText(self.source_description(self.session['info']))
        font = QFont(family)
        dpi = self.window.screen().logicalDotsPerInch()
        font.setPointSizeF(self.raw_size()*self.window.zoom*72/dpi)
        font.setBold(bold)
        font.setItalic(italic)
        self.editor.setFont(font)
        self.editor.setDefaultTextColor(QColor(*self.session['color']))
        self.editor.setTextWidth(-1)
        info, canvas = self.session['info'], self.window.canvas
        metrics = QFontMetricsF(font)
        if info['type'] == TEXT:
            a, b, c, d, e, f = info['matrix']
            ox, oy = canvas.to_scene(e, f)
            xx, xy = canvas.to_scene(e+a*100, f+b*100)
            yx, yy = canvas.to_scene(e-c*100, f-d*100)
            basis_x = ((xx-ox)/(100*self.window.zoom), (xy-oy)/(100*self.window.zoom))
            basis_y = ((yx-ox)/(100*self.window.zoom), (yy-oy)/(100*self.window.zoom))
            transform = QTransform(*basis_x, *basis_y, 0, 0)
            self.editor.setTransform(transform)
            self.editor.setPos(ox-basis_y[0]*metrics.ascent(), oy-basis_y[1]*metrics.ascent())
        else:
            x, top = canvas.to_scene(self.session['ink_left'], self.session['ink_top'])
            first = self.editor.toPlainText().splitlines()[0] if self.editor.toPlainText() else 'Ag'
            tight = metrics.tightBoundingRect(first)
            self.editor.setPos(x, top-tight.top()-metrics.ascent())
        self.refresh_preview()

    def commit(self, force=False):
        if not self.editor:
            return not self.busy
        value = self.editor.toPlainText()
        unchanged = (value == self.session['text'] and abs(self.size.value()-self.session['start_size']) < .01
                     and self.fonts.currentData() == self.session['start_face'])
        if unchanged and not force:
            self.window.last_text_selection=self.session['index']
            self.cancel()
            return True
        if getattr(self, 'preview_error', None) and not unchanged:
            self.status.setText(self.preview_error)
            self.window.statusBar().showMessage(self.preview_error, 16000)
            return False
        info = self.session['info']
        if info['type'] == TEXT and not self.fonts.currentData() and not self.session['original_available']:
            self.status.setText('La fuente original no está disponible. Elige una alternativa o importa el TTF para aplicar.')
            return False
        try:
            if self.session.get('box_bounds') or self.session.get('layout') or self.fonts.currentData() or '\n' in value or abs(self.size.value()-self.session['start_size'])>=.01:
                key=self.window.model.apply_text_layout(self.session['indices'],value,self.raw_size(),self.fonts.currentData(),self.session['color'],self.session.get('new_layout_id'),self.session.get('box_bounds'))
                run=next((r for r in self.window.model.text_runs() if r.get('layout')==key),None)
                self.window.last_text_selection=run['indices'][0] if run else None
            elif len(self.session['indices'])>1 and self.fonts.currentData() is None:
                self.window.model.apply_native_run(self.session['indices'],self.session['text'],value)
            elif len(self.session['indices'])>1:
                raise ValueError('La sustitución de fuente en una línea fragmentada todavía no está validada. Usa Original.')
            else:
                self.window.model.apply_inline(self.session['index'], value, self.raw_size(), self.fonts.currentData(),
                                               self.session['color'], self.session.get('ink_top'), self.session.get('ink_left'))
        except Exception as error:
            self.status.setText(str(error))
            self.status.setStyleSheet('color: #b04445;')
            self.window.statusBar().showMessage(str(error), 16000)
            return False
        default_face=self.fonts.currentData()
        if not default_face:
            matches=self.catalog.matching(info['font'],'bold' in info['font'].lower() or info.get('weight',400)>=600,info.get('italic',False))
            if matches and not matches[0].restricted:default_face=matches[0].path
        self.window.text_defaults={'size':self.size.value(),'face':default_face}
        if self.session.get('newly_created') and len(self.window.model.undo_stack)>=2:
            original=self.window.model.undo_stack[-2]
            self.window.model.undo_stack[-2:]=[('Añadir texto',original[1],original[2])]
        if not (self.session.get('box_bounds') or self.session.get('layout') or self.fonts.currentData() or '\n' in value or abs(self.size.value()-self.session['start_size'])>=.01):
            self.window.last_text_selection=self.session['index']
        self._clear()
        self.window.render_page()
        self.window.statusBar().showMessage('Texto actualizado dentro del PDF. Puedes deshacer o guardar una copia.', 8000)
        return True

    def _clear(self):
        self.caret_timer.stop()
        self.generation += 1
        self.editor = None
        self.session = None
        self.busy = False
        self.panel.hide()
        self.window.text_format.hide()
        self.status.setStyleSheet('')
        self.window.set_edit_shortcuts(True)
        self.window.move_group.show()
        self.window.delete_button.show()
        self.window.edit_button.show()
        self.window.key_hint.setText('Atajos\nCtrl+O   Abrir\nCtrl+S   Guardar\nCtrl+Z   Deshacer\nSupr   Borrar selección\nCtrl+rueda   Zoom')

    def cancel(self):
        had = self.active
        discard_new=had and self.session.get('newly_created') and self.window.model.current_version==self.session['version']
        self._clear()
        if discard_new:self.window.model.undo()
        if had and self.window.model:
            self.window.render_page()

    def import_font(self):
        path, _ = QFileDialog.getOpenFileName(self.window, 'Importar fuente TrueType', str(Path.home()/'Downloads'), 'Fuente TrueType (*.ttf)')
        if not path:
            return
        try:
            face = self.catalog.add(path)
            existing = self.fonts.findData(face.path)
            if existing < 0:
                self.fonts.addItem('Importada · '+face.name, face.path)
                existing = self.fonts.count()-1
            self.fonts.setCurrentIndex(existing)
        except Exception as error:
            self.status.setText(str(error))

    def find_font(self):
        if self.session:
            name = clean_name(self.session['info'].get('font', ''))
            if not name and self.fonts.currentData():
                name = read_face(self.fonts.currentData()).family
            QDesktopServices.openUrl(QUrl('https://fonts.google.com/?query='+quote(name)))
