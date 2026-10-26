"""Whole-object selection, group dragging and the Windows clipboard."""
import io
from pathlib import Path
import tempfile

from PySide6.QtCore import Qt, QPointF, QRectF, QMimeData, QByteArray
from PySide6.QtGui import QPen, QColor, QImage
from PySide6.QtWidgets import QApplication, QMenu
from engine import TEXT, IMAGE, pdf
from object_transfer import export_objects,paste_objects,mutate_objects,union,validate_change,PATH

MIME='application/x-faropdf-objects'
MAX_CLIPBOARD=100*1024*1024


class ObjectSelection:
    def __init__(self,window):
        self.window=window;self.groups=[];self.items=[]
        self.start=None;self.dragging=False;self.rubber=None;self.additive=False;self.paste_count=0

    def clear(self):
        scene=self.window.canvas.scene()
        for item in self.items:scene.removeItem(item)
        if self.rubber:scene.removeItem(self.rubber)
        self.items=[];self.groups=[];self.rubber=None;self.start=None;self.dragging=False

    def candidates(self):
        model=self.window.model
        if not model:return []
        result=[]
        for block in model.text_blocks():
            indices=tuple(sorted({i for run in block['runs'] for i in run['indices']}))
            result.append((indices,block['bounds'],TEXT))
        for i,obj in enumerate(model.objects):
            if obj.type==IMAGE:result.append(((i,),obj.get_bounds(),IMAGE))
        from graphic_objects import selection_groups
        result.extend(selection_groups(model))
        return result

    def hit(self,pos):
        canvas=self.window.canvas
        options=[]
        for indices,bounds,kind in self.candidates():
            rect=canvas.object_rect(bounds)
            if not rect.adjusted(-3,-3,3,3).contains(pos):continue
            if kind==PATH and len(indices)==1 and rect.width()>40 and rect.height()>40:
                from graphic_objects import hit_test
                if not hit_test(self.window.model,indices[0],*canvas.to_page(pos),3/self.window.zoom):continue
            options.append((kind!=TEXT,rect.width()*rect.height(),indices))
        return min(options)[2] if options else None

    def draw(self):
        scene=self.window.canvas.scene()
        for item in self.items:scene.removeItem(item)
        self.items=[]
        model=self.window.model
        candidate_bounds={g:b for g,b,_ in self.candidates()}
        for group in self.groups:
            bounds=candidate_bounds.get(tuple(group)) or union([model.objects[i].get_bounds() for i in group])
            pen=QPen(QColor('#087f7b'),1.5,Qt.PenStyle.DashLine);pen.setCosmetic(True)
            item=scene.addRect(self.window.canvas.object_rect(bounds).adjusted(-3,-3,3,3),pen,QColor(8,127,123,15))
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton);item.setZValue(24);self.items.append(item)
        self.window.selection_title.setText('Objeto seleccionado' if len(self.groups)==1 else f'{len(self.groups)} objetos seleccionados')
        self.window.delete_button.setEnabled(bool(self.groups))
        self.window.details.setText('Arrastra para mover; Ctrl+C copia, Ctrl+X corta y Ctrl+V pega.\nCtrl+clic añade o quita objetos.' if self.groups else
                                    'Haz clic en una imagen o un cuadro completo, o rodea varios objetos con un recuadro.')

    def press(self,pos,modifiers):
        window=self.window
        if window.inline.active and not window.inline.commit():return
        window.canvas.setFocus(Qt.FocusReason.MouseFocusReason)
        window.select(None)
        hit=self.hit(pos);self.start=pos;self.additive=bool(modifiers&Qt.KeyboardModifier.ControlModifier)
        if hit:
            if self.additive:
                if hit in self.groups:self.groups.remove(hit)
                else:self.groups.append(hit)
            elif hit not in self.groups:self.groups=[hit]
            self.dragging=hit in self.groups;self.draw()
        else:
            if not self.additive:self.groups=[]
            self.dragging=False;self.draw()
            self.rubber=window.canvas.scene().addRect(QRectF(pos,pos),QPen(QColor('#087f7b'),1,Qt.PenStyle.DashLine),QColor(8,127,123,20))
            self.rubber.setZValue(25)

    def move(self,pos):
        if self.start is None:return
        if self.dragging:
            for item in self.items:item.setPos(pos-self.start)
        elif self.rubber:self.rubber.setRect(QRectF(self.start,pos).normalized())

    def release(self,pos):
        if self.start is None:return
        start=self.start;self.start=None
        if self.dragging:
            self.dragging=False
            a=self.window.canvas.to_page(start);b=self.window.canvas.to_page(pos)
            if abs(a[0]-b[0])+abs(a[1]-b[1])>.5:
                groups=list(self.groups)
                try:
                    mutate_objects(self.window.model,groups,b[0]-a[0],b[1]-a[1])
                    self.window.render_page();self.groups=groups;self.draw()
                except Exception as error:self.draw();self.window.error(error)
            else:self.draw()
        elif self.rubber:
            rect=QRectF(start,pos).normalized()
            self.window.canvas.scene().removeItem(self.rubber);self.rubber=None
            for indices,bounds,_ in self.candidates():
                if rect.contains(self.window.canvas.object_rect(bounds)) and indices not in self.groups:self.groups.append(indices)
            self.draw()

    def all(self):
        self.groups=[indices for indices,_,_ in self.candidates()];self.draw()

    def selected_groups(self):
        if self.window.mode=='objects':return list(self.groups)
        i=self.window.selected
        if i is None:return []
        if self.window.model.objects[i].type==IMAGE:return [(i,)]
        run=self.window.model.text_run(i)
        return [tuple(run['indices'])] if run else []

    def copy(self,cut=False):
        window=self.window
        if window.inline.active:
            cursor=window.inline.editor.textCursor()
            if cursor.hasSelection():
                QApplication.clipboard().setText(cursor.selectedText().replace('\u2029','\n'))
                if cut:cursor.removeSelectedText();window.inline.editor.setTextCursor(cursor)
            return
        if window.mode=='select':
            if cut:window.statusBar().showMessage('Para cortar cuadros completos, elige Seleccionar objetos.',6000)
            else:window.text_selection.copy()
            return
        groups=self.selected_groups()
        if not groups:return
        try:
            data=export_objects(window.model,groups)
            if len(data)>MAX_CLIPBOARD:raise ValueError('La selección es demasiado grande para el portapapeles. Selecciona menos objetos.')
            mime=QMimeData();mime.setData(MIME,QByteArray(data));mime.setData('application/pdf',QByteArray(data))
            document=pdf.PdfDocument(data);page=document[0];text=page.get_textpage()
            try:
                value=text.get_text_bounded()
                if value:mime.setText(value)
                if any(window.model.objects[i].type in (IMAGE,PATH) for group in groups for i in group):
                    from object_transfer import packet_bounds
                    import math
                    width,height=page.get_size()
                    scale=min(1.5,math.sqrt(4_000_000/max(1,width*height)))
                    bounds=packet_bounds(data);bitmap=page.render(scale=scale,fill_color=(255,255,255,0))
                    try:
                        # Convert user-space bounds through PDFium (crop/rotation aware).
                        import ctypes as C
                        points=[]
                        for x in (bounds[0],bounds[2]):
                            for y in (bounds[1],bounds[3]):
                                sx,sy=C.c_int(),C.c_int()
                                pdf.raw.FPDF_PageToDevice(page,0,0,bitmap.width,bitmap.height,0,x,y,C.byref(sx),C.byref(sy))
                                points.append((sx.value,sy.value))
                        xs,ys=zip(*points)
                        image=bitmap.to_pil().crop((max(0,min(xs)),max(0,min(ys)),min(bitmap.width,max(xs)+1),min(bitmap.height,max(ys)+1)))
                        output=io.BytesIO();image.save(output,format='PNG');mime.setImageData(QImage.fromData(output.getvalue()))
                    finally:bitmap.close()
            finally:text.close();page.close();document.close()
            if cut:
                mutate_objects(window.model,groups,delete=True)
                window.model.undo_stack[-1]=('Cortar selección',*window.model.undo_stack[-1][1:])
                window.render_page()
            QApplication.clipboard().setMimeData(mime);self.paste_count=0
            window.statusBar().showMessage('Selección cortada.' if cut else 'Selección copiada.',6000)
        except Exception as error:window.error(error)

    def delete(self):
        groups=self.selected_groups()
        if not groups:return
        try:mutate_objects(self.window.model,groups,delete=True);self.window.render_page()
        except Exception as error:self.window.error(error)

    def paste(self,anchor=None):
        window=self.window;mime=QApplication.clipboard().mimeData()
        if not window.model or mime is None:return
        if window.inline.active and mime.hasText():
            cursor=window.inline.editor.textCursor();cursor.insertText(mime.text());window.inline.editor.setTextCursor(cursor);return
        if window.inline.active and not window.inline.commit():return
        try:
            if mime.hasFormat(MIME):
                packet=bytes(mime.data(MIME))
                if len(packet)>MAX_CLIPBOARD:raise ValueError('El fragmento del portapapeles es demasiado grande.')
                before=len(window.model.objects)
                data,bounds=paste_objects(window.model._edit_data,window.model.index,packet,anchor,12*(self.paste_count+1))
                validate_change(window.model,data,[bounds])
                window.model.install_bytes('Pegar selección',data);self.paste_count+=1
                window.set_mode('objects');window.render_page()
                self.groups=[g for g,_,_ in self.candidates() if all(i>=before for i in g)];self.draw()
            elif mime.hasImage():
                image=QImage(mime.imageData())
                if image.isNull():raise ValueError('La imagen del portapapeles no es válida.')
                x,y=anchor or window.canvas.to_page(QPointF(45,45))
                with tempfile.TemporaryDirectory(prefix='faro-paste-') as temp:
                    path=Path(temp)/'clipboard.png'
                    if not image.save(str(path)):raise ValueError('No se pudo leer la imagen del portapapeles.')
                    width=min(image.width()*72/96,window.model.page.get_width()*.6)
                    window.model.add_image(path,x,y,max(12,width))
                window.set_mode('objects');window.render_page()
                self.groups=[(i,) for i in range(len(window.model.objects)-1,len(window.model.objects))];self.draw()
            elif mime.hasText() and mime.text():
                x,y=anchor or window.canvas.to_page(QPointF(45,45))
                window.set_mode('text');window.add_text(x,y)
                if window.inline.active:window.inline.editor.setPlainText(mime.text())
        except Exception as error:window.error(error)

    def context(self,global_pos,scene_pos):
        hit=self.hit(scene_pos)
        if hit and hit not in self.groups:self.groups=[hit];self.draw()
        menu=QMenu(self.window)
        for label,callback in [('Cortar\tCtrl+X',lambda:self.copy(True)),('Copiar\tCtrl+C',self.copy),('Borrar selección\tSupr',self.delete)]:
            action=menu.addAction(label,callback);action.setEnabled(bool(self.groups))
        menu.addSeparator();menu.addAction('Pegar aquí\tCtrl+V',lambda:self.paste(self.window.canvas.to_page(scene_pos)))
        menu.addAction('Seleccionar todos los objetos\tCtrl+A',self.all)
        menu.exec(global_pos)
