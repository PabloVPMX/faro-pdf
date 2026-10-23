"""Synthetic search and print checks; never use a physical printer."""
import hashlib
import time
from pathlib import Path


def fixture(path):
    from pypdf import PdfWriter
    from pypdf.generic import NameObject,DictionaryObject,DecodedStreamObject
    writer=PdfWriter()
    font=writer._add_object(DictionaryObject({NameObject('/Type'):NameObject('/Font'),
        NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica'),
        NameObject('/Encoding'):NameObject('/WinAnsiEncoding')}))
    for number,(width,height,text) in enumerate([(612,792,'Faro farola FARO'),(792,612,'Faro café'),(612,792,'FARO')]):
        page=writer.add_blank_page(width=width,height=height)
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
        stream=DecodedStreamObject()
        # Distinct colored blocks make page order, orientation and centering observable.
        rgb=['0.1 0.6 0.7','0.8 0.2 0.3','0.2 0.6 0.2'][number]
        stream.set_data((f'q {rgb} rg 45 70 170 100 re f Q\nBT /F1 24 Tf 50 {height-90} Td ({text}) Tj ET').encode('cp1252'))
        page[NameObject('/Contents')]=writer._add_object(stream)
        if number==2:page.rotate(90)
    writer.write(path)
    return Path(path).read_bytes()


def wait_for(condition):
    from PySide6.QtTest import QTest
    end=time.monotonic()+8
    while not condition():
        assert time.monotonic()<end,'Reader operation did not settle'
        QTest.qWait(15)


def check_reader(window,app,work):
    from PySide6.QtCore import Qt,QSizeF,QMarginsF
    from PySide6.QtGui import QPageSize,QPageLayout,QPageRanges
    from PySide6.QtPrintSupport import QPrinter
    from PySide6.QtTest import QTest
    from search import SearchSession
    from printing import paint_document,selected_pages,PrintCancelled,page_image
    from PIL import Image,ImageChops,ImageStat
    import pypdfium2 as pdf

    work=Path(work);source=work/'lectura y busqueda.pdf'
    data=fixture(source)
    def search(query,**options):
        session=SearchSession(data,query,**options);hits=[]
        try:
            while not session.done:hits.extend(session.step(batch=2))
            return hits,session.truncated
        finally:session.close()
    hits,_=search('faro');assert len(hits)==5
    assert len(search('Faro',match_case=True)[0])==2
    assert len(search('faro',whole_word=True)[0])==4
    assert len(search('café')[0])==1
    assert not search('inexistente')[0]
    assert search('faro',limit=2)[1]
    assert all(h.rects and all(r[2]>r[0] and r[3]>r[1] for r in h.rects) for h in hits)
    if window.model:window.model.saved_version=window.model.current_version
    window.open_file(str(source));app.processEvents()
    controller=window.search
    window.activateWindow();window.canvas.viewport().setFocus();app.processEvents();QTest.qWait(30)
    QTest.keyClick(window.canvas.viewport(),Qt.Key.Key_F,Qt.KeyboardModifier.ControlModifier)
    assert controller.bar.isVisible()
    controller.query.setText('faro')
    controller.whole_word.setChecked(True)
    wait_for(lambda:not controller.running and not controller.debounce.isActive() and len(controller.hits)==4)
    assert controller.items
    for _ in range(len(controller.hits)):
        controller.move(1);app.processEvents();QTest.qWait(60)
        assert window.model.index==controller.hits[controller.current].page
    assert controller.current==0,'Find next must wrap around'
    controller.move(-1);assert controller.current==3
    window.change_zoom(1.1);app.processEvents()
    assert controller.items,'Search highlights must survive zoom and rotated pages'
    before=window.model._data
    controller.query.setFocus();controller.query.selectAll();app.processEvents()
    QTest.keyClick(controller.query,Qt.Key.Key_Delete)
    assert window.model._data==before and not window.model.dirty,'Delete in search must not delete PDF objects'
    controller.query.setText('faro');controller.start()
    wait_for(lambda:not controller.running)
    window.grab().save(str(work/'busqueda.png'))
    controller.hide();controller.show()
    wait_for(lambda:not controller.running and not controller.debounce.isActive() and bool(controller.hits))
    # Editing invalidates matches, and undo causes a new search of the current bytes.
    window.model.add_text('Faro',80,300)
    window.render_page()
    wait_for(lambda:not controller.running and not controller.debounce.isActive() and len(controller.hits)==5)
    window.model.undo();window.render_page()
    wait_for(lambda:not controller.running and not controller.debounce.isActive() and len(controller.hits)==4)
    controller.hide()

    def printer(path):
        device=QPrinter(QPrinter.PrinterMode.HighResolution)
        device.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        device.setOutputFileName(str(path));device.setResolution(144)
        device.setPageSize(QPageSize(QSizeF(612,792),QPageSize.Unit.Point))
        device.setPageMargins(QMarginsF(18,18,18,18),QPageLayout.Unit.Point)
        device.setFullPage(False)
        return device
    output=work/'impresion de prueba.pdf';device=printer(output)
    assert selected_pages(device,3,1)==[0,1,2]
    device.setPrintRange(QPrinter.PrintRange.CurrentPage);assert selected_pages(device,3,1)==[1]
    ranges=QPageRanges();ranges.addPage(1);ranges.addPage(3)
    device.setPageRanges(ranges);device.setPrintRange(QPrinter.PrintRange.PageRange)
    assert selected_pages(device,3,0)==[0,2]
    device.setPageOrder(QPrinter.PageOrder.LastPageFirst)
    assert selected_pages(device,3,0)==[2,0]
    assert paint_document(data,device,[2,1,0])==[2,1,0]
    printed=pdf.PdfDocument(output);original=pdf.PdfDocument(data)
    try:
        assert len(printed)==3
        for number,index in enumerate([2,1,0]):
            page=printed[number];bitmap=page.render(scale=1)
            try:image=bitmap.to_pil().convert('RGB')
            finally:bitmap.close()
            # Dominant saturated ink proves that the requested source page was printed.
            colors=image.getdata()
            count=[sum(1 for r,g,b in colors if predicate(r,g,b)) for predicate in
                   (lambda r,g,b:g>r*1.3 and b>r*1.3,lambda r,g,b:r>g*1.7 and r>b*1.3,
                    lambda r,g,b:g>r*1.5 and g>b*1.5)]
            assert count[index]>1000,(index,count)
            original_page=original[index];bitmap=original_page.render(scale=1)
            try:reference=bitmap.to_pil().convert('RGB')
            finally:bitmap.close();original_page.close()
            scale=min(576/reference.width,756/reference.height)
            reference=reference.resize((round(reference.width*scale),round(reference.height*scale)),Image.Resampling.LANCZOS)
            expected=Image.new('RGB',(612,792),'white')
            expected.paste(reference,((612-reference.width)//2,(792-reference.height)//2))
            assert max(ImageStat.Stat(ImageChops.difference(expected,image)).mean)<4,'Printed orientation or margins changed'
            page.close()
        # Explicitly check the raster bound for oversized pages without allocating a giant image.
        p=original[0];image=page_image(p,1200)
        assert image.width()*image.height()<=24_100_000;p.close()
    finally:printed.close();original.close()
    cancelled=printer(work/'cancelada.pdf')
    try:paint_document(data,cancelled,[0],cancelled=lambda:True)
    except PrintCancelled:pass
    else:raise AssertionError('Print cancellation ignored')
    assert source.read_bytes()==data and window.model._data==data
    assert not window.model.dirty
    return {'search_all_pages_case_word_accents_and_rotated_geometry':True,
            'search_navigation_wrap_zoom_delete_safety_and_edit_invalidation':True,
            'print_pdf_output_page_ranges_order_orientation_and_source_unchanged':True,
            'print_cancel_and_bounded_rendering':True}
