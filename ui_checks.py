"""Synthetic interaction checks shared by source and packaged diagnostics."""
import hashlib
from pathlib import Path


def check_document_view(window, app, work):
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
    from PySide6.QtCore import Qt, QPointF
    from PySide6.QtTest import QTest
    from engine import pdf

    path=Path(work)/'tres paginas.pdf'
    writer=PdfWriter()
    font=writer._add_object(DictionaryObject({NameObject('/Type'):NameObject('/Font'),
        NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica'),
        NameObject('/Encoding'):NameObject('/WinAnsiEncoding')}))
    for i in range(3):
        page=writer.add_blank_page(width=612 if i!=2 else 700,height=792)
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
        content=DecodedStreamObject()
        content.set_data(f'BT /F1 18 Tf 50 720 Td (Pagina {i+1} original) Tj ET'.encode())
        page[NameObject('/Contents')]=writer._add_object(content)
    with path.open('wb') as output:writer.write(output)
    original=path.read_bytes()
    if window.model:window.model.saved_version=window.model.current_version
    window.open_file(str(path));app.processEvents();QTest.qWait(80)
    view=window.document_view
    assert len(view.slots)==3 and view.verticalScrollBar().maximum()>1000
    assert all(view.slots[i].y()<view.slots[i+1].y() for i in range(2))
    checks={'continuous_pages_layout':True}
    before=[]
    for i in range(3):
        page=window.model.doc[i];bitmap=page.render(scale=1)
        before.append(hashlib.sha256(bytes(bitmap.buffer)).hexdigest())
        bitmap.close();page.close()
    view.scroll_to_page(1);QTest.qWait(90)
    assert window.model.index==1 and window.page_number.value()==2
    assert view.horizontalScrollBar().maximum()==0, 'Fit width must include page margins.'
    checks['scroll_activates_correct_page']=True
    window.set_mode('add')
    canvas=window.canvas
    start=canvas.mapFromScene(QPointF(*canvas.to_scene(70,650)))
    end=canvas.mapFromScene(QPointF(*canvas.to_scene(235,540)))
    QTest.mousePress(canvas.viewport(),Qt.LeftButton,pos=start)
    QTest.mouseMove(canvas.viewport(),end)
    QTest.mouseRelease(canvas.viewport(),Qt.LeftButton,pos=end)
    app.processEvents()
    assert window.inline.active and window.inline.session['page']==1
    assert not window.properties_dialog.isVisible() and window.text_format.isVisible()
    value='Texto en un cuadro con acentos: áéíóú ñ. Se ajusta al ancho sin perder caracteres.\nOtra línea.'
    window.inline.editor.setPlainText(value)
    window.inline.size.setValue(15)
    assert window.inline.editor.toPlainText()==value,window.inline.status.text()
    assert len(set(round(r['origin'][1],1) for r in window.inline.session['characters']))>2
    # Wheel scrolling during an edit must leave the draft on its original page.
    view.scroll_to_page(2);QTest.qWait(90)
    assert window.inline.active and window.model.index==1
    view.scroll_to_page(1)
    assert window.inline.commit(),window.inline.status.text()
    run=next(r for r in window.model.text_runs() if r.get('text')==value)
    assert run['box_bounds'] and len(run['characters'])==len(value)
    checks['draw_inline_box_wrap_accents_separate_format']=True
    window.model.undo();assert not any(r.get('text')==value for r in window.model.text_runs())
    assert all(window.model.info(i)['text']!='Texto' for i,o in enumerate(window.model.objects) if o.type==1)
    window.model.redo();window.render_page()
    run=next(r for r in window.model.text_runs() if r.get('text')==value)
    checks['new_text_single_undo_without_placeholder']=True
    box=run['box_bounds']
    window.model.move_text(run['indices'],12,-8);window.render_page()
    run=next(r for r in window.model.text_runs() if r.get('text')==value)
    assert all(abs(a-b)<.01 for a,b in zip(run['box_bounds'],(box[0]+12,box[1]-8,box[2]+12,box[3]-8)))
    checks['move_wrapped_box_preserves_layout']=True
    window.inline.begin(run['indices'][0])
    face=next((i for i in range(window.inline.fonts.count())
               if str(window.inline.fonts.itemData(i)).lower().endswith('segoeui.ttf')),None)
    assert face is not None
    window.inline.fonts.setCurrentIndex(face)
    window.inline.size.setValue(17)
    assert window.inline.editor.toPlainText()==value,window.inline.status.text()
    assert window.inline.commit(),window.inline.status.text()
    checks['format_change_keeps_editable_box']=True
    output=Path(work)/'tres paginas editadas.pdf'
    window.model.save(output)
    reopened=pdf.PdfDocument(str(output))
    for i in (0,2):
        page=reopened[i];bitmap=page.render(scale=1)
        assert hashlib.sha256(bytes(bitmap.buffer)).hexdigest()==before[i],f'Unexpected change on page {i+1}'
        bitmap.close();page.close()
    reopened.close()
    assert path.read_bytes()==original
    window.open_file(str(output));window.navigate(1);QTest.qWait(60)
    run=next(r for r in window.model.text_runs() if r.get('text')==value)
    window.inline.begin(run['indices'][0]);assert window.inline.active
    assert window.inline.editor.toPlainText()==value
    window.inline.cancel()
    checks['reopen_box_other_pages_pixel_identical']=True
    # Click on a passive page and draw there without a second activation click.
    window.navigate(0);window.set_mode('add');app.processEvents()
    window.inline.generation+=1
    slot=view.slots[1]
    point=slot.rect().topLeft()+window.canvas.mapFromScene(QPointF(*window.canvas.to_scene(100,500)))
    QTest.mousePress(slot,Qt.LeftButton,pos=point)
    QTest.mouseRelease(slot,Qt.LeftButton,pos=point)
    assert window.model.index==1 and window.inline.active
    window.inline.cancel()
    checks['passive_page_click_starts_edit']=True
    window.set_continuous(False);app.processEvents()
    assert sum(slot.isVisible() for slot in view.slots)==1
    window.set_continuous(True);app.processEvents()
    assert all(slot.isVisible() for slot in view.slots)
    checks['single_page_toggle']=True
    window.navigate(1);window.document_view.scroll_to_page(1);QTest.qWait(70)
    run=next(r for r in window.model.text_runs() if r.get('text')==value)
    window.inline.begin(run['indices'][0]);app.processEvents()
    window.grab().save(str(Path(work)/'vista-cuadro-texto.png'))
    window.inline.cancel()
    # Show two neighboring pages in a useful overview after the checks.
    window.fit=False;window.zoom=.7;window.render_page();app.processEvents()
    window.document_view.scroll_to_page(1);QTest.qWait(70)
    return checks
