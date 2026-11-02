"""Real mouse resizing: pending text, wrapping, persistence and faithful undo."""
import hashlib
import io
from pathlib import Path
from unittest.mock import patch


def check_text_resize(window,app,work):
    from PySide6.QtCore import Qt,QPointF
    from PySide6.QtTest import QTest
    from pypdf import PdfReader
    from content_patch import _resource_digest
    from owned_text_checks import fixture
    from engine import Document,TEXT
    work=Path(work)/'cuadros redimensionables';work.mkdir(exist_ok=True)
    source=work/'original.pdf';original=fixture(source)
    if window.model:window.model.saved_version=window.model.current_version
    window.open_file(str(source));window.fit=False;window.zoom=.9;window.render_page()
    window.set_mode('text');model=window.model
    value='dame una coca y café con azúcar\nLínea manual'
    model.add_text(value,100,510,14,box=(100,370,185,510))
    window.render_page();app.processEvents()

    def run():return next(r for r in model.text_runs() if r.get('owned'))
    def meta():
        page=PdfReader(io.BytesIO(model._data)).pages[0]
        return page['/FaroTextData'][run()['layout']].get_object(),page
    def select():window.select(run()['indices'][0]);app.processEvents()
    def drag(key,delta):
        item=dict(window.canvas.resize_handles)[key]
        point=item.rect().center();end=point+QPointF(*delta)
        start=window.canvas.mapFromScene(point);finish=window.canvas.mapFromScene(end)
        QTest.mouseMove(window.canvas.viewport(),start)
        QTest.mousePress(window.canvas.viewport(),Qt.MouseButton.LeftButton,pos=start)
        QTest.mouseMove(window.canvas.viewport(),finish)
        QTest.mouseRelease(window.canvas.viewport(),Qt.MouseButton.LeftButton,pos=finish)
        app.processEvents()
        assert window.canvas.resize_start is None
    select();assert len(window.canvas.resize_handles)==8
    before=model._data;old,old_page=meta();old=dict(old)
    font_hash=_resource_digest(old_page['/Resources']['/Font'][old['/Font']].get_object())
    history=len(model.undo_stack);old_lines=len(old['/Lines'])
    drag('r',(150,0))
    grown,page=meta()
    assert run()['text']==value and run()['box_bounds'][2]-run()['box_bounds'][0]>200
    assert len(grown['/Lines'])<old_lines,'Widening must reflow automatic wraps'
    assert '\n' in run()['text'],'Explicit line breaks must be retained'
    assert float(grown['/Size'])==float(old['/Size']) and list(grown['/Color'])==list(old['/Color'])
    assert _resource_digest(page['/Resources']['/Font'][grown['/Font']].get_object())==font_hash
    assert len(model.undo_stack)==history+1
    resized=model._data;model.undo();assert model._data==before
    model.redo();assert model._data==resized
    window.render_page();select()
    # Corner drags change width and height independently, unlike image scaling.
    old_box=run()['box_bounds'];drag('rb',(45,18));new_box=run()['box_bounds']
    assert abs((new_box[2]-old_box[2])-50)<2
    assert abs((old_box[1]-new_box[1])-20)<2
    # Top/left drag preserves the text inset from that corner and its font size.
    old_matrix=tuple(map(float,meta()[0]['/Matrix']));old_box=new_box
    drag('lt',(-27,-18));new_box=run()['box_bounds'];new_matrix=tuple(map(float,meta()[0]['/Matrix']))
    assert abs((new_matrix[4]-old_matrix[4])-(new_box[0]-old_box[0]))<.01
    assert abs((new_matrix[5]-old_matrix[5])-(new_box[3]-old_box[3]))<.01
    select();old_box=run()['box_bounds']
    point=window.canvas.text_grip.rect().center();end=point+QPointF(9,9)
    QTest.mousePress(window.canvas.viewport(),Qt.MouseButton.LeftButton,pos=window.canvas.mapFromScene(point))
    assert window.canvas.text_drag_start and not window.canvas.resize_start
    QTest.mouseMove(window.canvas.viewport(),window.canvas.mapFromScene(end))
    QTest.mouseRelease(window.canvas.viewport(),Qt.MouseButton.LeftButton,pos=window.canvas.mapFromScene(end))
    app.processEvents();new_box=run()['box_bounds']
    assert abs(new_box[0]-old_box[0]-10)<2 and abs(new_box[3]-old_box[3]+10)<2
    # Resize while a caret edit has not yet been applied. The letters survive.
    select()
    with patch.object(window.inline,'_add_all_faces',return_value=None):
        window.inline.begin(run()['indices'][0])
    assert window.inline.active
    changed=value+' y más letras'
    window.inline.editor.setPlainText(changed);app.processEvents()
    assert len(window.canvas.resize_handles)==8
    drag('b',(0,25))
    assert not window.inline.active and run()['text']==changed
    # Save/reopen keeps the frame and exposes handles again.
    saved=work/'redimensionado.pdf';box=run()['box_bounds'];model.save(saved)
    reopened=Document(saved)
    try:
        own=next(r for r in reopened.text_runs() if r.get('owned'))
        assert own['text']==changed and all(abs(a-b)<.01 for a,b in zip(own['box_bounds'],box))
    finally:reopened.close()
    window.open_file(str(saved));model=window.model;window.set_mode('text');select()
    assert len(window.canvas.resize_handles)==8
    drag('l',(-18,0));assert run()['text']==changed
    for _ in range(4):
        model.rotate_page(0,90);window.render_page();select()
        old_rect=window.canvas.object_rect(run()['box_bounds'])
        drag('rb',(18,9));new_rect=window.canvas.object_rect(run()['box_bounds'])
        assert abs(new_rect.width()-old_rect.width()-18)<2
        assert abs(new_rect.height()-old_rect.height()-9)<2
        assert run()['text']==changed
    # Original text is never offered these reflow controls.
    original_index=next(i for i,o in enumerate(model.objects) if o.type==TEXT and i not in run()['indices'])
    window.select(original_index);assert not window.canvas.resize_handles
    try:model.resize_text_box(original_index,(20,20,100,100))
    except ValueError:pass
    else:raise AssertionError('Native PDF text was silently reconstructed')
    # Original streams/font and the other page are untouched by all resizing.
    old_reader=PdfReader(io.BytesIO(original));after=PdfReader(io.BytesIO(model._data))
    assert old_reader.pages[0].get_contents().get_data() in after.pages[0].get_contents().get_data()
    import pypdfium2 as pdf
    docs=[pdf.PdfDocument(original),pdf.PdfDocument(model._data)]
    hashes=[]
    try:
        for doc in docs:
            page=doc[1];bitmap=page.render(scale=1)
            hashes.append(hashlib.sha256(bitmap.to_pil().tobytes()).digest());bitmap.close();page.close()
        assert hashes[0]==hashes[1]
    finally:
        for doc in docs:doc.close()
    assert source.read_bytes()==original
    window.select(run()['indices'][0]);window.grab().save(str(work/'tiradores-texto.png'))
    model.saved_version=model.current_version
    return dict(text_box_edges_corners_reflow_font_size_undo=True,
                text_box_pending_edit_resize_save_reopen=True,
                text_box_original_content_other_page_unchanged=True)
