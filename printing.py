"""Windows print/preview dialogs and bounded rendering of the current PDF."""
import math

import pypdfium2 as pdf
from PySide6.QtCore import QRectF, QSizeF, Qt
from PySide6.QtGui import QImage, QPainter, QPageSize
from PySide6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog, QAbstractPrintDialog
from PySide6.QtWidgets import QApplication, QDialog, QProgressDialog


class PrintCancelled(Exception):
    pass


def selected_pages(printer, count, current):
    mode = printer.printRange()
    if mode == QPrinter.PrintRange.CurrentPage:
        pages = [current]
    elif mode == QPrinter.PrintRange.PageRange:
        ranges = printer.pageRanges().toRangeList()
        if ranges:
            pages = [i for i in range(count) if any(r.from_ <= i+1 <= r.to for r in ranges)]
        else:
            first, last = printer.fromPage(), printer.toPage()
            pages = list(range(max(1, first)-1, min(count, last)))
    else:
        pages = list(range(count))
    if not pages or any(not 0 <= index < count for index in pages):
        raise ValueError('Selecciona al menos una página válida para imprimir.')
    if printer.pageOrder() == QPrinter.PageOrder.LastPageFirst:
        pages.reverse()
    return pages


def page_image(page, dpi):
    width, height = page.get_size()
    # Large technical sheets must not allocate unbounded bitmaps.
    scale = min(max(72, min(dpi, 300))/72, math.sqrt(24_000_000/max(1,width*height)))
    bitmap = page.render(scale=scale, force_bitmap_format=pdf.raw.FPDFBitmap_BGRA, rev_byteorder=True)
    try:
        return QImage(bitmap.buffer,bitmap.width,bitmap.height,bitmap.stride,QImage.Format.Format_RGBA8888).copy()
    finally:
        bitmap.close()


def paint_document(data, printer, pages, cancelled=None, progress=None):
    """Paint clean PDF content, without selection/search/editor overlays."""
    document = pdf.PdfDocument(data)
    painter = QPainter()
    printed = []
    try:
        if not pages or any(not 0 <= i < len(document) for i in pages):
            raise ValueError('El intervalo de páginas no es válido.')
        # Native drivers implement their own copies; do not multiply them twice.
        copies = 1 if printer.supportsMultipleCopies() else max(1, printer.copyCount())
        if printer.collateCopies():
            sequence = list(pages)*copies
        else:
            sequence = [i for i in pages for _ in range(copies)]
        if cancelled and cancelled():
            raise PrintCancelled()
        if not painter.begin(printer):
            raise ValueError('No se pudo iniciar la impresión. Revisa la impresora seleccionada.')
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for position, index in enumerate(sequence):
            if progress:
                progress(position, len(sequence))
            if cancelled and cancelled():
                printer.abort(); raise PrintCancelled()
            page = document[index]
            try:
                image = page_image(page, printer.resolution())
            finally:
                page.close()
            if position and not printer.newPage():
                raise ValueError('La impresora no aceptó la página siguiente.')
            area = printer.pageLayout().paintRectPixels(printer.resolution())
            if area.width() <= 0 or area.height() <= 0:
                raise ValueError('La impresora no tiene un área de impresión válida.')
            scale = min(area.width()/image.width(),area.height()/image.height())
            width,height=image.width()*scale,image.height()*scale
            target=QRectF((area.width()-width)/2,(area.height()-height)/2,width,height)
            painter.drawImage(target,image)
            printed.append(index)
        if progress:
            progress(len(sequence),len(sequence))
        return printed
    except Exception:
        if painter.isActive(): printer.abort()
        raise
    finally:
        if painter.isActive(): painter.end()
        document.close()


class PrintController:
    def __init__(self, window):
        self.window = window
        self.busy = False
        self.cancel_requested=False

    def cancel(self):
        self.cancel_requested=True

    def prepare(self):
        if self.busy or not self.window.model:
            return None
        if self.window.inline.active and not self.window.inline.commit():
            return None
        model = self.window.model
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setResolution(300)
        printer.setDocName(model.source.name)
        printer.setFullPage(False)
        width,height=model.page.get_size()
        printer.setPageSize(QPageSize(QSizeF(width,height),QPageSize.Unit.Point))
        printer.setFromTo(1,len(model.doc))
        printer.setPrintRange(QPrinter.PrintRange.AllPages)
        return printer,model._data,model.index,len(model.doc)

    def print_dialog(self):
        prepared=self.prepare()
        if not prepared:return
        printer,data,current,count=prepared
        dialog=QPrintDialog(printer,self.window)
        dialog.setWindowTitle('Imprimir PDF')
        dialog.setMinMax(1,count)
        dialog.setOption(QAbstractPrintDialog.PrintDialogOption.PrintPageRange,True)
        dialog.setOption(QAbstractPrintDialog.PrintDialogOption.PrintCurrentPage,True)
        dialog.setOption(QAbstractPrintDialog.PrintDialogOption.PrintSelection,False)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            try:self.paint(data,printer,selected_pages(printer,count,current))
            except Exception as error:self.window.error(error)

    def paint(self,data,printer,pages,preview=False):
        self.busy=True
        self.cancel_requested=False
        progress=QProgressDialog('Preparando páginas…','Cancelar',0,len(pages),self.window)
        progress.setWindowTitle('Imprimir PDF'); progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(400)
        try:
            def advance(done,total):
                progress.setMaximum(total);progress.setValue(done)
                QApplication.processEvents()
            printed=paint_document(data,printer,pages,lambda:self.cancel_requested or progress.wasCanceled(),advance)
            self.window.statusBar().showMessage('Vista previa actualizada.' if preview else
                f'Se enviaron {len(printed)} páginas a la impresora seleccionada.',10000)
        except PrintCancelled:
            self.window.statusBar().showMessage('Impresión cancelada.',8000)
        finally:
            progress.close();progress.deleteLater();self.busy=False

    def preview(self):
        prepared=self.prepare()
        if not prepared:return
        printer,data,current,count=prepared
        dialog=QPrintPreviewDialog(printer,self.window)
        dialog.setWindowTitle('Vista previa de impresión — Faro PDF')
        dialog.resize(1050,780)
        def render(device):
            if self.busy:return
            try:self.paint(data,device,selected_pages(device,count,current),preview=True)
            except Exception as error:self.window.error(error)
        dialog.paintRequested.connect(render)
        dialog.exec()
