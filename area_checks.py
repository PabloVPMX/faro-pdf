"""Synthetic grouped headers and arbitrary partial-object rectangular crops."""
import io
from pathlib import Path


def fixture(path):
    from pypdf import PdfWriter
    from pypdf.generic import (NameObject,DictionaryObject,DecodedStreamObject,
                              RectangleObject,BooleanObject)
    writer=PdfWriter()
    font=writer._add_object(DictionaryObject({NameObject('/Type'):NameObject('/Font'),
        NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica-Bold')}))
    form=DecodedStreamObject();form.set_data(b'0.1 0.25 0.3 rg 0 0 320 65 re f 1 1 1 rg BT /F1 22 Tf 12 24 Td (GROUPED HEADER) Tj ET')
    form.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Form'),
        NameObject('/BBox'):RectangleObject((0,0,320,65)),
        NameObject('/Resources'):DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})}),
        NameObject('/Group'):DictionaryObject({NameObject('/S'):NameObject('/Transparency'),NameObject('/I'):BooleanObject(True)})})
    ref=writer._add_object(form)
    for rotation in (0,90,180,270):
        page=writer.add_blank_page(width=480,height=360)
        page[NameObject('/CropBox')]=RectangleObject((10,15,470,345))
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/XObject'):DictionaryObject({NameObject('/Header'):ref}),
            NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
        stream=DecodedStreamObject();stream.set_data(b'q 1 0 0 1 35 250 cm /Header Do Q\n0 0 0 rg BT /F1 16 Tf 35 160 Td (Body remains editable) Tj ET\n0 0 1 RG 2 w 30 30 390 180 re S')
        page[NameObject('/Contents')]=writer._add_object(stream)
        if rotation:page.rotate(rotation)
    writer.write(path)
    return Path(path).read_bytes()


def check_areas(window,app,work):
    from PySide6.QtCore import QPointF,Qt
    from PySide6.QtTest import QTest
    from pypdf import PdfReader
    import pypdfium2 as pdf
    from object_transfer import FORM,export_objects,paste_objects,mutate_objects,validate_change
    from area_selection import area_packet,cut_area
    work=Path(work)/'areas y grupos';work.mkdir(parents=True,exist_ok=True)
    source=work/'encabezados.pdf';original=fixture(source)
    if window.model:window.model.saved_version=window.model.current_version
    window.open_file(str(source));window.set_mode('objects');app.processEvents()
    model=window.model
    form=next(i for i,o in enumerate(model.objects) if o.type==FORM)
    assert any(g==(form,) for g,b,k in window.object_selection.candidates())
    packet=export_objects(model,[(form,)])
    assert 'GROUPED HEADER' in PdfReader(io.BytesIO(packet)).pages[0].extract_text()
    data,box=paste_objects(model._edit_data,0,packet,anchor=(35,235));validate_change(model,data,[box])
    snapshot=model._data
    for delete in (False,True):
        mutate_objects(model,[(form,)],dx=12,dy=-7,delete=delete)
        model.undo();assert model._data==snapshot
    # Select a rectangle that slices through the middle of the Form: it cannot
    # be expressed as a set of complete native objects.
    window.set_mode('area');app.processEvents();canvas=window.canvas
    a=QPointF(*canvas.to_scene(85,307));b=QPointF(*canvas.to_scene(250,260))
    window.activateWindow();canvas.setFocus();app.processEvents();QTest.qWait(40)
    QTest.mousePress(canvas.viewport(),Qt.MouseButton.LeftButton,pos=canvas.mapFromScene(a))
    QTest.mouseMove(canvas.viewport(),canvas.mapFromScene(b))
    QTest.mouseRelease(canvas.viewport(),Qt.MouseButton.LeftButton,pos=canvas.mapFromScene(b))
    assert window.area_selection.bounds
    QTest.keyClick(canvas.viewport(),Qt.Key.Key_C,Qt.KeyboardModifier.ControlModifier)
    assert app.clipboard().mimeData().hasImage()
    packet=bytes(app.clipboard().mimeData().data('application/x-faropdf-objects'))
    read=PdfReader(io.BytesIO(packet))
    assert not read.pages[0].extract_text() and len(read.pages[0]['/Resources']['/XObject'])==1
    # The snapshot carries no hidden original text or original resource graph.
    QTest.keyClick(canvas.viewport(),Qt.Key.Key_X,Qt.KeyboardModifier.ControlModifier)
    assert len(model.undo_stack)==1
    cut=model._data
    # A cut leaves white pixels where the selected Form used to be.
    old=pdf.PdfDocument(original);new=pdf.PdfDocument(cut)
    oldpage=old[0];newpage=new[0];bitmaps=[p.render(scale=1) for p in (oldpage,newpage)]
    try:assert bitmaps[0].to_pil().tobytes()!=bitmaps[1].to_pil().tobytes()
    finally:
        for bm in bitmaps:bm.close()
        oldpage.close();newpage.close();old.close();new.close()
    window.object_selection.paste(anchor=(85,307))
    assert len(model.undo_stack)==2
    assert any(o.type==pdf.raw.FPDF_PAGEOBJ_IMAGE for o in model.objects)
    model.undo();model.undo();assert model._data==snapshot
    # CropBox/rotation must affect both image orientation and paste placement.
    for index in range(4):
        window.navigate(index);bounds=(85,260,250,307)
        packet,png=area_packet(model,bounds)
        data,box=paste_objects(model._edit_data,index,packet,anchor=(85,245));validate_change(model,data,[box])
        before=model._data;cut_area(model,bounds);model.undo();assert model._data==before
    window.navigate(0);window.set_mode('area');app.processEvents()
    window.area_selection.press(a);window.area_selection.release(b)
    window.refresh_menus();assert window.clipboard_actions['Copiar'].isEnabled()
    app.processEvents();window.grab().save(str(work/'seleccion-area.png'))
    # OCR's result explicitly explains the unchanged appearance and exposes
    # already-selectable native text when the page was skipped.
    window.ocr.show_result(dict(changed=[],skipped=[0],empty=[]));app.processEvents()
    assert window.ocr.result_dialog.isVisible()
    window.ocr.result_dialog.close()
    # Rotate through the actual UI action; preserve other pages, original
    # streams, CropBox and one-step undo, including save/reopen persistence.
    before=model._data;old_reader=PdfReader(io.BytesIO(before))
    for degrees in (90,-90,180):
        window.rotate_page(degrees)
        reader=PdfReader(io.BytesIO(model._data))
        assert reader.pages[0].rotation==(old_reader.pages[0].rotation+degrees)%360
        assert reader.pages[0].get_contents().get_data()==old_reader.pages[0].get_contents().get_data()
        assert reader.pages[0].cropbox==old_reader.pages[0].cropbox
        assert all(reader.pages[i].rotation==old_reader.pages[i].rotation for i in range(1,4))
        model.save(work/'girado.pdf')
        assert PdfReader(work/'girado.pdf').pages[0].rotation==reader.pages[0].rotation
        model.undo();assert model._data==before
    assert source.read_bytes()==original
    return dict(grouped_form_header_copy_cut_paste_move_undo=True,
                area_partial_object_copy_cut_paste_image=True,
                area_cropbox_rotations_outside_pixels_undo=True,
                ocr_visible_result_explains_skipped_pages=True,
                rotate_page_left_right_180_save_undo=True)
