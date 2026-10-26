"""Visual rectangular snippets, independent of the PDF's object boundaries."""
import ctypes as C
import io
import math

import pypdfium2 as pdf
from pypdf import PdfReader,PdfWriter
from pypdf.generic import (NameObject,DictionaryObject,DecodedStreamObject,
                          ArrayObject,NumberObject)
from PySide6.QtCore import Qt,QRectF,QByteArray,QMimeData
from PySide6.QtGui import QColor,QPen,QImage
from PySide6.QtWidgets import QApplication,QMenu
from insertions import writer_for,finish
from object_transfer import display_matrix,inverse,point,validate_change


def area_packet(model,bounds):
    """Render just the chosen visible pixels to one independent image packet.

    Other content/resources are not copied into the clipboard. Ordinary object
    copy remains vector-based; this explicit tool is a snapshot at 300 dpi.
    """
    page=model.page;w,h=page.get_size()
    scale=min(300/72,math.sqrt(20_000_000/max(1,w*h)))
    bitmap=page.render(scale=scale,draw_annots=True,fill_color=(255,255,255,255))
    try:
        positions=[]
        for x in (bounds[0],bounds[2]):
            for y in (bounds[1],bounds[3]):
                sx,sy=C.c_int(),C.c_int()
                pdf.raw.FPDF_PageToDevice(page,0,0,bitmap.width,bitmap.height,0,x,y,C.byref(sx),C.byref(sy))
                positions.append((sx.value,sy.value))
        xs,ys=zip(*positions)
        rect=(max(0,min(xs)),max(0,min(ys)),min(bitmap.width,max(xs)),min(bitmap.height,max(ys)))
        if rect[2]-rect[0]<2 or rect[3]-rect[1]<2:raise ValueError('Selecciona un área más grande.')
        image=bitmap.to_pil().convert('RGB').crop(rect)
    finally:bitmap.close()
    reader=PdfReader(io.BytesIO(model._edit_data));source=reader.pages[model.index]
    matrix=display_matrix(source);corners=[point(inverse(matrix),x,y) for x in (bounds[0],bounds[2]) for y in (bounds[1],bounds[3])]
    px,py=zip(*corners);l,b,r,t=min(px),min(py),max(px),max(py)
    writer=PdfWriter();target=writer.add_blank_page(width=w,height=h)
    obj=DecodedStreamObject();obj.set_data(image.tobytes())
    obj.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Image'),
                NameObject('/Width'):NumberObject(image.width),NameObject('/Height'):NumberObject(image.height),
                NameObject('/BitsPerComponent'):NumberObject(8),NameObject('/ColorSpace'):NameObject('/DeviceRGB')})
    target[NameObject('/Resources')]=DictionaryObject({NameObject('/XObject'):DictionaryObject({NameObject('/Area'):writer._add_object(obj.flate_encode())})})
    stream=DecodedStreamObject();stream.set_data(f'q {r-l:.9f} 0 0 {t-b:.9f} {l:.9f} {b:.9f} cm /Area Do Q'.encode('ascii'))
    target[NameObject('/Contents')]=writer._add_object(stream)
    png=io.BytesIO();image.save(png,format='PNG')
    return finish(writer),png.getvalue()


def cut_area(model,bounds):
    """Clip out the area without painting over it or rasterizing the rest.

    This is a reversible visual crop, not a secure redaction operation.
    """
    writer=writer_for(model._edit_data);page=writer.pages[model.index]
    l,b,r,t=bounds
    # Annotations are outside the content clipping state. Do not claim to cut
    # them while silently leaving a widget or link appearance visible.
    for ref in page.get('/Annots',[]):
        annot=ref.get_object();box=list(map(float,annot.get('/Rect',(0,0,0,0))))
        if box[0]<r and box[2]>l and box[1]<t and box[3]>b:
            raise ValueError('El área incluye una anotación o campo de formulario. Selecciona un área sin estos elementos.')
    ml,mb,mr,mt=map(float,page.mediabox)
    prefix=DecodedStreamObject()
    prefix.set_data(f'q {ml:.9f} {mb:.9f} {mr-ml:.9f} {mt-mb:.9f} re {l:.9f} {b:.9f} {r-l:.9f} {t-b:.9f} re W* n\n'.encode('ascii'))
    suffix=DecodedStreamObject();suffix.set_data(b'\nQ\n')
    old=page.get('/Contents');resolved=old.get_object() if old else None
    parts=list(resolved) if isinstance(resolved,ArrayObject) else [old] if old else []
    page[NameObject('/Contents')]=ArrayObject([writer._add_object(prefix)]+parts+[writer._add_object(suffix)])
    result=finish(writer);validate_change(model,result,[bounds])
    model.install_bytes('Cortar área',result)


class AreaSelection:
    def __init__(self,window):
        self.window=window;self.start=None;self.item=None;self.bounds=None

    def clear(self):
        if self.item:self.window.canvas.scene().removeItem(self.item)
        self.item=None;self.start=None;self.bounds=None

    def press(self,pos):
        self.clear();self.window.select(None);canvas=self.window.canvas
        canvas.setFocus();self.start=canvas.bounded_position(pos)
        pen=QPen(QColor('#087f7b'),1.5,Qt.PenStyle.DashLine);pen.setCosmetic(True)
        self.item=canvas.scene().addRect(QRectF(self.start,self.start),pen,QColor(8,127,123,20));self.item.setZValue(26)

    def move(self,pos):
        if self.start is not None:self.item.setRect(QRectF(self.start,self.window.canvas.bounded_position(pos)).normalized())

    def release(self,pos):
        if self.start is None:return
        self.move(pos);self.start=None;rect=self.item.rect()
        if rect.width()<4 or rect.height()<4:self.clear();return
        a=self.window.canvas.to_page(rect.topLeft());b=self.window.canvas.to_page(rect.bottomRight())
        self.bounds=(min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1]))
        self.window.selection_title.setText('Área seleccionada como imagen')
        self.window.details.setText('Ctrl+C copia; Ctrl+X corta; Ctrl+V pega como imagen que puedes mover y redimensionar.\nEl recorte es visual; no es una herramienta de censura de datos.')
        self.window.statusBar().showMessage('Área lista: Ctrl+C para copiar o Ctrl+X para cortar. Ctrl+V pega como imagen.',15000)

    def copy(self,cut=False):
        if not self.bounds:return
        try:
            from object_selection import MIME,MAX_CLIPBOARD
            data,png=area_packet(self.window.model,self.bounds)
            if len(data)>MAX_CLIPBOARD:raise ValueError('Selecciona un área más pequeña.')
            mime=QMimeData();mime.setData(MIME,QByteArray(data));mime.setData('application/pdf',QByteArray(data));mime.setImageData(QImage.fromData(png))
            if cut:cut_area(self.window.model,self.bounds);self.window.render_page()
            QApplication.clipboard().setMimeData(mime);self.window.object_selection.paste_count=0
            self.window.statusBar().showMessage('Área cortada. Puedes pegarla o deshacer.' if cut else 'Área copiada como imagen.',10000)
        except Exception as error:self.window.error(error)

    def context(self,global_pos,scene_pos):
        menu=QMenu(self.window)
        for label,callback in [('Copiar área\tCtrl+C',self.copy),('Cortar área\tCtrl+X',lambda:self.copy(True))]:
            action=menu.addAction(label,callback);action.setEnabled(self.bounds is not None)
        menu.addAction('Pegar aquí\tCtrl+V',lambda:self.window.object_selection.paste(self.window.canvas.to_page(scene_pos)))
        menu.exec(global_pos)
