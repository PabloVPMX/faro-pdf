"""Real local OCR regression, synthetic scans only, including the frozen worker."""
import hashlib
import io
import time
from pathlib import Path


def fixture(path):
    from PIL import Image, ImageDraw, ImageFont
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject, NumberObject, RectangleObject
    image = Image.new('RGB', (1500, 1000), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 58)
    draw.text((120, 160), 'Faro PDF reconoce documentos', fill='#122d40', font=font)
    draw.text((120, 300), 'Cotización en México', fill='black', font=font)
    draw.text((120, 450), 'Importe: 1,234.56 pesos', fill='black', font=font)
    draw.rectangle((100, 100, 1400, 115), fill='#008d81')
    writer = PdfWriter()
    for rotation in (0, 90, 180, 270):
        # Compensate page rotation so the displayed scan is upright.
        scan = image.rotate(rotation, expand=True)
        width, height = scan.width/3, scan.height/3
        left, bottom = (17, 23) if rotation in (90, 270) else (0, 0)
        page = writer.add_blank_page(width=width+left*2, height=height+bottom*2)
        page[NameObject('/CropBox')] = RectangleObject((left, bottom, width+left, height+bottom))
        stream = DecodedStreamObject(); stream.set_data(scan.tobytes())
        stream.update({NameObject('/Type'):NameObject('/XObject'), NameObject('/Subtype'):NameObject('/Image'),
                       NameObject('/Width'):NumberObject(scan.width), NameObject('/Height'):NumberObject(scan.height),
                       NameObject('/ColorSpace'):NameObject('/DeviceRGB'), NameObject('/BitsPerComponent'):NumberObject(8)})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/XObject'):DictionaryObject({NameObject('/Im'):writer._add_object(stream.flate_encode())})})
        contents = DecodedStreamObject(); contents.set_data(f'q {width} 0 0 {height} {left} {bottom} cm /Im Do Q'.encode())
        page[NameObject('/Contents')] = writer._add_object(contents)
        if rotation: page.rotate(rotation)
    page = writer.add_blank_page(width=500, height=333)
    font = writer._add_object(DictionaryObject({NameObject('/Type'):NameObject('/Font'),
        NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')}))
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
    stream = DecodedStreamObject(); stream.set_data(b'BT /F1 18 Tf 40 250 Td (Texto nativo Faro) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream)
    writer.add_blank_page(width=500, height=333)
    writer.write(path)
    return Path(path).read_bytes()


def check_ocr(window, app, work):
    import pypdfium2 as pdf
    from pypdf import PdfReader
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt, QPointF
    from engine import Document
    from search import SearchSession
    from ocr_engine import page_range
    work = Path(work) / 'ocr local'; work.mkdir(exist_ok=True)
    source = work / 'escaneos.pdf'; original = fixture(source)
    digest = hashlib.sha256(original).digest()
    assert page_range('1-3, 5, 2', 6) == [0,1,2,4]
    for bad in ('0', '7', '4-2', '', '1,,2', 'x'):
        try: page_range(bad, 6)
        except ValueError: pass
        else: raise AssertionError('Invalid OCR range accepted')
    if window.model: window.model.saved_version = window.model.current_version
    window.open_file(str(source)); app.processEvents()
    assert window.ocr.start(list(range(6)))
    deadline = time.monotonic() + 300
    ticks = 0
    while window.ocr.busy:
        assert time.monotonic() < deadline, 'OCR worker timeout'
        QTest.qWait(30); ticks += 1
    result = window.ocr.last_summary
    assert result and result['changed'] == [0,1,2,3], result
    assert result['skipped'] == [4] and result['empty'] == [5], result
    assert ticks > 1 and window.model.dirty and window.mode == 'select'
    data = window.model._data
    reader = PdfReader(io.BytesIO(data)); old_reader = PdfReader(io.BytesIO(original))
    for i in range(6):
        before, after = old_reader.pages[i], reader.pages[i]
        assert before.cropbox == after.cropbox and before.rotation == after.rotation
        for name, reference in before.get('/Resources', {}).get('/XObject', {}).items():
            assert reference.get_object().get_data() == after['/Resources']['/XObject'][name].get_object().get_data()
    doc = pdf.PdfDocument(data)
    try:
        for i in range(4):
            page = doc[i]; text = page.get_textpage()
            try:
                extracted = text.get_text_bounded()
                assert 'Faro' in extracted and 'México' in extracted, extracted
            finally: text.close(); page.close()
    finally: doc.close()
    session = SearchSession(data, 'Faro'); hits = []
    try:
        while not session.done: hits.extend(session.step())
    finally: session.close()
    assert len(hits) == 5 and all(h.rects for h in hits)
    window.navigate(0); window.set_mode('select'); app.processEvents()
    assert not window.model.text_runs(), 'Invisible OCR must not become an editable visible text block'
    # Hit-test and drag the actual OCR glyphs in displayed page coordinates.
    hit = hits[0]; bounds = hit.rects[0]
    canvas = window.canvas
    start = canvas.to_scene(bounds[0]+1, (bounds[1]+bounds[3])/2)
    end = canvas.to_scene(bounds[2]-1, (bounds[1]+bounds[3])/2)
    window.text_selection.press(QPointF(*start)); window.text_selection.move(QPointF(*end))
    assert 'Faro' in window.text_selection.value, window.text_selection.value
    window.text_selection.copy(); assert 'Faro' in app.clipboard().text()
    window.activateWindow(); canvas.setFocus(); app.processEvents()
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(QPointF(*start)))
    QTest.mouseMove(canvas.viewport(), canvas.mapFromScene(QPointF(*end)))
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=canvas.mapFromScene(QPointF(*end)))
    assert 'Faro' in window.text_selection.value
    app.clipboard().clear()
    QTest.keyClick(canvas.viewport(), Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert 'Faro' in app.clipboard().text(), 'Ctrl+C must copy the selected OCR text'
    QTest.keyClick(canvas.viewport(), Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert 'México' in window.text_selection.value, 'Ctrl+A must select the current page'
    window.text_selection.all(); assert 'México' in window.text_selection.value
    window.model.save(work / 'reconocido.pdf')
    reopened = Document(work / 'reconocido.pdf')
    assert 'Faro' in reopened.textpage.get_text_bounded(); reopened.close()
    window.undo(); assert window.model._data == original
    window.redo(); assert window.model._data == data
    # Text added by Faro remains independently editable after hidden OCR text.
    window.set_mode('text'); window.add_text(50, 100)
    assert window.inline.active
    window.inline.editor.setPlainText('Añadido después del OCR')
    assert window.inline.commit(), window.inline.status.text()
    assert any('Añadido' in run.get('text', '') for run in window.model.text_runs())
    window.model.undo(); window.render_page()
    snapshot = window.model._data; version = window.model.current_version
    assert window.ocr.start([0]); window.ocr.cancel()
    deadline = time.monotonic()+30
    while window.ocr.busy:
        assert time.monotonic()<deadline; QTest.qWait(30)
    assert window.model._data == snapshot and window.model.current_version == version
    assert hashlib.sha256(source.read_bytes()).digest() == digest
    window.set_mode('select'); window.text_selection.all(); app.processEvents()
    window.grab().save(str(work / 'ocr.png'))
    return dict(ocr_local_real_worker_accents=True, ocr_rotations_cropbox_images_preserved=True,
                ocr_mixed_pages_skip_existing_text=True, ocr_select_copy_search_save_reopen=True,
                ocr_undo_redo_cancel_atomic=True, ocr_added_text_remains_editable=True)
