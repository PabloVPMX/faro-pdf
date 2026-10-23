"""Regression: add editable text over a PDF whose original font has no ToUnicode."""
from pathlib import Path
from unittest.mock import patch


def fixture(path):
    from pypdf import PdfWriter
    from pypdf.generic import NameObject,DictionaryObject,DecodedStreamObject
    from text_layout import add_font
    writer=PdfWriter();page=writer.add_blank_page(width=612,height=792)
    page[NameObject('/Resources')]=DictionaryObject()
    name=add_font(writer,page,'C:/Windows/Fonts/arial.ttf')
    page['/Resources']['/Font'][name].pop(NameObject('/ToUnicode'))
    stream=DecodedStreamObject()
    stream.set_data((f'BT {name} 20 Tf 1 0 0 1 50 710 Tm <'+
                     'ORIGINAL'.encode('utf-16-be').hex()+'> Tj ET\n0.3 G 50 680 400 1 re S\n').encode('ascii'))
    page[NameObject('/Contents')]=writer._add_object(stream)
    second=writer.add_blank_page(width=612,height=792)
    second[NameObject('/Resources')]=DictionaryObject()
    ink=DecodedStreamObject();ink.set_data(b'0.2 0.5 0.7 rg 60 100 130 170 re f')
    second[NameObject('/Contents')]=writer._add_object(ink)
    writer.write(path)
    return Path(path).read_bytes()


def check_owned_text(window,app,work):
    from engine import Document,TEXT
    from pypdf import PdfReader
    from content_patch import _resource_digest
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    import io,numpy as np,pypdfium2 as pdf
    work=Path(work);source=work/'fuente sin mapa unicode.pdf';original=fixture(source)
    before=PdfReader(io.BytesIO(original));resource_hash=_resource_digest(before.pages[0]['/Resources'])
    original_font=next(iter(before.pages[0]['/Resources']['/Font']))
    font_hash=_resource_digest(before.pages[0]['/Resources']['/Font'][original_font].get_object())
    raw=before.pages[0].get_contents().get_data()
    if window.model:window.model.saved_version=window.model.current_version
    window.open_file(str(source));app.processEvents()
    assert 'ToUnicode' in window.model.native_preflight[0]['error']
    window.text_defaults={'size':12,'face':None}
    window.add_text(100,500,(100,400,370,500))
    assert window.inline.active,window.inline.status.text()
    value='Prueba áéíóú ñ p\nSegunda línea'
    window.inline.editor.setPlainText(value)
    assert window.inline.editor.toPlainText()==value,window.inline.status.text()
    face=window.inline.fonts.findData('C:\\Windows\\Fonts\\arial.ttf')
    if face<0:
        face=next(i for i in range(window.inline.fonts.count())
                  if str(window.inline.fonts.itemData(i)).lower().replace('\\','/')=='c:/windows/fonts/arial.ttf')
    window.inline.fonts.setCurrentIndex(face);window.inline.size.setValue(18)
    assert window.inline.fonts.currentIndex()==face,window.inline.status.text()
    assert window.inline.editor.toPlainText()==value and not window.inline.preview_error,window.inline.status.text()
    assert window.inline.commit(),window.inline.status.text()
    run=next(r for r in window.model.text_runs() if r.get('owned'))
    assert run['text']==value
    window.model.move_text(run['indices'],11,-7);window.render_page()
    # Moving an image consolidates page streams; the box must remain editable.
    from PIL import Image
    from engine import IMAGE
    image=work/'imagen junto al cuadro.png';Image.new('RGB',(20,20),'navy').save(image)
    window.model.add_image(image,450,320,35)
    image_index=next(i for i,o in enumerate(window.model.objects) if o.type==IMAGE)
    window.model.move(image_index,6,-4)
    run=next(r for r in window.model.text_runs() if r.get('owned'))
    window.model.apply_text_layout(run['indices'],value+' p',18,box=run.get('box_bounds'))
    window.model.undo();window.model.undo();window.model.undo()
    assert next(r for r in window.model.text_runs() if r.get('owned'))['text']==value
    output=work/'texto independiente guardado.pdf';window.model.save(output)
    reopened=Document(output)
    try:
        assert next(r for r in reopened.text_runs() if r.get('owned'))['text']==value
        assert 'ToUnicode' in reopened.native_preflight[0]['error']
    finally:reopened.close()
    window.open_file(str(output));app.processEvents()
    run=next(r for r in window.model.text_runs() if r.get('owned'))
    window.inline.begin(run['indices'][0]);assert window.inline.active
    value='Edición posterior con acentos y p'
    window.inline.editor.setPlainText(value)
    assert window.inline.editor.toPlainText()==value,window.inline.status.text()
    assert window.inline.commit(),window.inline.status.text()
    run=next(r for r in window.model.text_runs() if r.get('owned'))
    window.model.delete(run['indices'][0])
    assert not any(r.get('owned') for r in window.model.text_runs())
    window.model.undo();assert next(r for r in window.model.text_runs() if r.get('owned'))['text']==value
    window.model.redo();window.model.undo();window.render_page()
    previous=window.model._data
    window.add_text(100,300);assert window.inline.active
    window.inline.cancel();assert window.model._data==previous
    with patch.object(window.inline,'begin',return_value=None):
        window.add_text(100,300)
    assert window.model._data==previous,'A failed insertion must not leave a placeholder'
    assert not window.inline.active
    # The independent route must not weaken native-font validation.
    original_index=next(i for i,o in enumerate(window.model.objects) if o.type==TEXT)
    try:window.model.native_text_bytes(original_index,'No debe aplicarse')
    except ValueError:pass
    else:raise AssertionError('Unsupported original font was silently replaced')
    after=PdfReader(io.BytesIO(window.model._data))
    assert _resource_digest(after.pages[0]['/Resources']['/Font'][original_font].get_object())==font_hash
    assert raw in after.pages[0].get_contents().get_data()
    documents=[pdf.PdfDocument(original),pdf.PdfDocument(window.model._data)]
    try:
        for index in range(2):
            images=[]
            for doc in documents:
                page=doc[index];bitmap=page.render(scale=1)
                try:images.append(np.asarray(bitmap.to_pil().convert('RGB')).copy())
                finally:bitmap.close();page.close()
            changed=np.any(images[0]!=images[1],axis=2)
            if index==0:changed[792-540:792-350,70:440]=False
            assert not changed.any(),'Insertion changed content outside the new text'
    finally:
        for doc in documents:doc.close()
    assert source.read_bytes()==original
    window.grab().save(str(work/'texto independiente.png'))
    return {'add_text_without_original_tounicode_accents_font_size_move_save_reopen':True,
            'independent_text_delete_undo_cancel_and_failed_insertion_rollback':True,
            'original_font_stream_and_other_page_pixel_identical':True}
