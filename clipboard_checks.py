"""Synthetic object clipboard, group dragging and collateral-change regressions."""
import io
import hashlib
from pathlib import Path


def check_clipboard(window,app,work):
    from pypdf import PdfReader,PdfWriter
    from pypdf.generic import NameObject,DecodedStreamObject
    from PIL import Image,ImageDraw
    from PySide6.QtCore import Qt,QPointF,QMimeData,QByteArray
    from PySide6.QtGui import QImage
    from PySide6.QtTest import QTest
    from reader_checks import fixture
    from object_selection import MIME
    from object_transfer import union,mutate_objects
    from engine import Document,IMAGE,TEXT,pdf
    work=Path(work)/'portapapeles';work.mkdir(exist_ok=True)
    source=work/'seleccion.pdf';fixture(source)
    reader=PdfReader(source);writer=PdfWriter();writer.clone_document_from_reader(reader)
    stream=DecodedStreamObject();stream.set_data(b'BT /F1 18 Tf 50 700 Td (Parrafo nativo primera linea) Tj 0 -23 Td (Segunda linea del mismo cuadro) Tj ET')
    writer.pages[0][NameObject('/Contents')]=writer._add_object(stream)
    writer.write(source);original=source.read_bytes()
    if window.model:window.model.saved_version=window.model.current_version
    window.open_file(str(source));app.processEvents()
    model=window.model
    model.add_text('Cuadro completo con acentos: áéíóú ñ.\nOtra línea editable.',80,560,16,
                   face='C:/Windows/Fonts/arial.ttf',box=(80,440,330,560))
    image=Image.new('RGBA',(110,75),(0,0,0,0));draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((5,5,105,70),radius=16,fill=(0,140,130,190))
    image_path=work/'imagen.png';image.save(image_path)
    model.add_image(image_path,380,530,110)
    window.set_mode('objects');window.render_page();app.processEvents()
    objects=window.object_selection
    own=next(run for run in model.text_runs() if run.get('owned'))
    value=own['text'];own_group=tuple(own['indices'])
    image_index=next(i for i,o in enumerate(model.objects) if o.type==IMAGE)
    # The fixture's original colored rectangle is a path, never selected/copied.
    image_index=max(i for i,o in enumerate(model.objects) if o.type==IMAGE)
    initial=model._data
    def page_digest(data,index):
        document=pdf.PdfDocument(data);page=document[index];bitmap=page.render(scale=1)
        try:return hashlib.sha256(bitmap.to_pil().tobytes()).digest()
        finally:bitmap.close();page.close();document.close()
    untouched=page_digest(initial,1)
    # Rubber-band selection and Ctrl-click operate on whole objects.
    candidates=objects.candidates()
    boxes=[window.canvas.object_rect(b) for g,b,_ in candidates if g in (own_group,(image_index,))]
    rect=boxes[0].united(boxes[1]).adjusted(-8,-8,8,8)
    QTest.mousePress(window.canvas.viewport(),Qt.MouseButton.LeftButton,pos=window.canvas.mapFromScene(rect.topLeft()))
    QTest.mouseMove(window.canvas.viewport(),window.canvas.mapFromScene(rect.bottomRight()))
    QTest.mouseRelease(window.canvas.viewport(),Qt.MouseButton.LeftButton,pos=window.canvas.mapFromScene(rect.bottomRight()))
    assert own_group in objects.groups and (image_index,) in objects.groups
    image_point=window.canvas.object_rect(model.objects[image_index].get_bounds()).center()
    for expected in (False,True):
        QTest.mouseClick(window.canvas.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ControlModifier,pos=window.canvas.mapFromScene(image_point))
        assert ((image_index,) in objects.groups)==expected
    objects.groups=[own_group];objects.draw();objects.copy()
    mime=app.clipboard().mimeData();assert mime.hasFormat(MIME)
    packet=bytes(mime.data(MIME));packet_reader=PdfReader(io.BytesIO(packet))
    assert len(packet_reader.pages)==1 and len(packet_reader.pages[0]['/FaroTextData'])==1
    assert 'Parrafo nativo' not in packet_reader.pages[0].extract_text()
    source_reader=PdfReader(io.BytesIO(initial));meta=next(iter(source_reader.pages[0]['/FaroTextData'].values()))
    # Paste into a rotated page with colliding /F1 resources; preserve the font.
    window.navigate(2);window.set_mode('objects');app.processEvents()
    objects.paste(window.canvas.to_page(QPointF(80,100)))
    pasted=next(run for run in model.text_runs() if run.get('owned'))
    assert pasted['text']==value
    after_reader=PdfReader(io.BytesIO(model._data));meta=next(iter(after_reader.pages[2]['/FaroTextData'].values()))
    # Digest only the font's decoded program; indirect reference IDs may change.
    def program(page,meta):
        font=page['/Resources']['/Font'][meta['/Font']]
        if '/DescendantFonts' in font:font=font['/DescendantFonts'][0].get_object()
        descriptor=font['/FontDescriptor']
        return next(descriptor[k].get_data() for k in ('/FontFile2','/FontFile3','/FontFile') if k in descriptor)
    source_meta=next(iter(source_reader.pages[0]['/FaroTextData'].values()))
    assert program(source_reader.pages[0],source_meta)==program(after_reader.pages[2],meta)
    window.inline.begin(pasted['indices'][0]);assert window.inline.active
    window.inline.editor.setPlainText(value+' Editado tras pegar.')
    assert window.inline.commit(),window.inline.status.text()
    assert any('Editado tras pegar' in run.get('text','') for run in model.text_runs())
    window.model.saved_version=window.model.current_version
    saved=work/'resultado.pdf';model.save(saved)
    reopened=Document(saved);reopened.set_page(2)
    assert any('Editado tras pegar' in r.get('text','') for r in reopened.text_runs());reopened.close()
    # Return to source, select an image and the whole multiline box, drag both.
    window.navigate(0);window.set_mode('objects');window.render_page();app.processEvents()
    own=next(run for run in model.text_runs() if run.get('owned'));own_group=tuple(own['indices'])
    image_index=max(i for i,o in enumerate(model.objects) if o.type==IMAGE)
    objects.groups=[own_group,(image_index,)];objects.draw()
    before=model._data;undo_count=len(model.undo_stack)
    old_boxes=[model.objects[i].get_bounds() for i in own_group+(image_index,)]
    point=QPointF(*window.canvas.to_scene(110,520));end=QPointF(*window.canvas.to_scene(135,500))
    QTest.mousePress(window.canvas.viewport(),Qt.MouseButton.LeftButton,pos=window.canvas.mapFromScene(point))
    QTest.mouseMove(window.canvas.viewport(),window.canvas.mapFromScene(end))
    QTest.mouseRelease(window.canvas.viewport(),Qt.MouseButton.LeftButton,pos=window.canvas.mapFromScene(end))
    assert len(model.undo_stack)==undo_count+1,'A group move must be a single undo'
    for old,i in zip(old_boxes,own_group+(image_index,)):
        new=model.objects[i].get_bounds()
        assert abs(new[0]-old[0]-25)<1 and abs(new[1]-old[1]+20)<1,(old,new)
    moved=model._data;window.undo();assert model._data==before
    window.redo();assert model._data==moved
    objects.groups=[own_group,(image_index,)];objects.draw()
    window.activateWindow();window.canvas.setFocus();app.processEvents();QTest.qWait(40)
    QTest.keyClick(window.canvas.viewport(),Qt.Key.Key_C,Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert app.clipboard().mimeData().hasImage() and app.clipboard().mimeData().hasFormat(MIME)
    copied=model._data;undo_count=len(model.undo_stack)
    QTest.keyClick(window.canvas.viewport(),Qt.Key.Key_X,Qt.KeyboardModifier.ControlModifier)
    assert len(model.undo_stack)==undo_count+1 and not any(r.get('owned') for r in model.text_runs())
    assert not any(o.type==IMAGE for o in model.objects)
    window.undo();assert model._data==copied
    # Paste twice: unique editable block IDs, no stale clipboard source handles.
    old_count=len(model.objects)
    QTest.keyClick(window.canvas.viewport(),Qt.Key.Key_V,Qt.KeyboardModifier.ControlModifier)
    assert len(model.objects)>old_count
    objects.paste()
    assert len([r for r in model.text_runs() if r.get('owned')])==3
    current_reader=PdfReader(io.BytesIO(model._data))
    original_image=next(v.get_object() for v in source_reader.pages[0]['/Resources']['/XObject'].values() if v.get_object().get('/Subtype')=='/Image')
    for ref in current_reader.pages[0]['/Resources']['/XObject'].values():
        image_object=ref.get_object()
        if image_object.get('/Subtype')=='/Image':
            assert image_object.get_data()==original_image.get_data()
            assert image_object['/SMask'].get_data()==original_image['/SMask'].get_data()
    # Native paragraph selection/cut includes both lines and remains undoable.
    native=next(g for g,b,k in objects.candidates() if k==TEXT and len(g)==2 and not model.text_run(g[0]).get('owned'))
    objects.groups=[native];objects.draw();native_before=model._data
    (work/'antes-cortar-nativo.pdf').write_bytes(native_before)
    objects.copy(True);assert 'Parrafo nativo' not in model.textpage.get_text_bounded()
    window.undo();assert model._data==native_before
    objects.paste(window.canvas.to_page(QPointF(70,420)))
    assert model.textpage.get_text_bounded().count('Parrafo nativo')==2
    window.undo();assert model._data==native_before
    # External clipboard formats continue to work and text can be pasted into a caret.
    external=QMimeData();external.setImageData(QImage(str(image_path)));app.clipboard().setMimeData(external)
    images_before=sum(o.type==IMAGE for o in model.objects);objects.paste()
    assert sum(o.type==IMAGE for o in model.objects)==images_before+1
    app.clipboard().setText('Texto externo con ñ y á.');objects.paste()
    assert window.inline.active and window.inline.editor.toPlainText()=='Texto externo con ñ y á.'
    window.inline.select_all();objects.copy(True);assert not window.inline.editor.toPlainText()
    objects.paste();assert window.inline.editor.toPlainText()=='Texto externo con ñ y á.'
    window.inline.cancel()
    invalid=QMimeData();invalid.setData(MIME,QByteArray(b'not a PDF'))
    app.clipboard().setMimeData(invalid);snapshot=model._data;errors=[];handler=window.error
    window.error=errors.append
    try:objects.paste()
    finally:window.error=handler
    assert errors and model._data==snapshot
    assert source.read_bytes()==original
    assert page_digest(model._data,1)==untouched,'Clipboard operations changed another page'
    window.set_mode('objects');objects.all();app.processEvents()
    window.grab().save(str(work/'seleccionar-objetos.png'))
    return dict(clipboard_whole_text_embedded_font_rotated_page_edit_save_reopen=True,
                clipboard_group_drag_cut_copy_paste_undo_redo=True,
                clipboard_native_paragraph_and_external_image_text=True,
                clipboard_invalid_payload_rejected_original_unchanged=True)
