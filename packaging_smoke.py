"""Explicit diagnostic mode; writes only beside the requested report."""
from pathlib import Path
import json
import os
import sys
import traceback


def run(report_path):
    report_path = Path(report_path).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    results = {'version': '1.1.0', 'frozen': bool(getattr(sys, 'frozen', False)), 'checks': {}}
    checks = results['checks']
    window = None
    try:
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        from pypdf import PdfWriter
        from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
        from PIL import Image
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFont, QFontDatabase
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from app import Window, STYLE
        from engine import Document, IMAGE
        work = report_path.parent / 'prueba ejecutable con espacios y acentos'
        work.mkdir(exist_ok=True)
        source = work / 'documento.pdf'
        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        font = writer._add_object(DictionaryObject({NameObject('/Type'): NameObject('/Font'),
            NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica'),
            NameObject('/Encoding'): NameObject('/WinAnsiEncoding')}))
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        stream = DecodedStreamObject()
        stream.set_data(b'BT /F1 18 Tf 50 720 Td (Faro PDF prueba) Tj ET')
        page[NameObject('/Contents')] = writer._add_object(stream)
        with source.open('wb') as output: writer.write(output)
        original = source.read_bytes()
        app = QApplication([])
        for name in ('segoeui.ttf', 'segoeuib.ttf'):
            QFontDatabase.addApplicationFont(str(Path('C:/Windows/Fonts') / name))
        app.setFont(QFont('Segoe UI', 10))
        app.setStyle('Fusion'); app.setStyleSheet(STYLE)
        window = Window(); window.resize(1280, 850); window.show()
        window.open_file(str(source)); app.processEvents()
        assert window.model and window.model.text_runs()
        checks['open_render_native_text'] = True
        window.set_mode('text')
        window.add_text(70, 600)
        assert window.inline.active
        window.inline.editor.setPlainText('Edición áéíóú ñ p\nSegunda línea')
        window.inline.size.setValue(15)
        # The normal textChanged connection creates the real PDF preview.
        assert not window.inline.preview_error, window.inline.status.text()
        QTest.keyClick(window.canvas.viewport(), Qt.Key_Return, Qt.ControlModifier)
        QTest.qWait(50)
        assert not window.inline.active, window.inline.status.text()
        assert any('Segunda línea' in r.get('text', '') for r in window.model.text_runs())
        checks['insert_edit_multiline_accents_font_size'] = True
        image = work/'imagen.png'; Image.new('RGBA', (80, 60), (0,128,128,180)).save(image)
        model = window.model; model.add_image(image, 300, 500, 90)
        index = next(i for i,o in enumerate(model.objects) if o.type == IMAGE)
        model.move(index, 15, -10)
        l,b,r,t = model.objects[index].get_bounds()
        model.resize_image(index, (l,b,l+(r-l)*1.2,b+(t-b)*1.2))
        checks['insert_move_resize_transparent_image'] = True
        model.insert_pdfs([source], 1); assert len(model.doc) == 2
        model.move_page(0,1); model.delete_page(0); assert len(model.doc) == 1
        model.undo(); assert len(model.doc) == 2
        model.redo(); assert len(model.doc) == 1
        checks['merge_move_delete_pages_undo_redo'] = True
        output = work/'resultado.pdf'; model.save(output)
        reopened = Document(output)
        assert len(reopened.doc) == 1
        assert any('Segunda línea' in r.get('text', '') for r in reopened.text_runs())
        reopened.close()
        assert source.read_bytes() == original
        checks['save_reopen_original_unchanged'] = True
        from ui_checks import check_document_view
        checks.update(check_document_view(window, app, work))
        window.render_page(); app.processEvents()
        window.grab().save(str(report_path.with_suffix('.png')))
        results['passed'] = True
    except Exception:
        results['passed'] = False
        results['error'] = traceback.format_exc()
    finally:
        if window:
            window.inline.cancel()
            if window.model:
                window.model.saved_version = window.model.current_version
            window.close()
        report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if results['passed'] else 1
