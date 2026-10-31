"""Synthetic Standard-14/CFF subsets and real process-lifetime regression."""
import io,json,os,subprocess,sys,time
from pathlib import Path


def fixture(path):
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    from fontTools.agl import UV2AGL
    from pypdf import PdfWriter
    from pypdf.generic import NameObject,DictionaryObject,NumberObject,ArrayObject,DecodedStreamObject,FloatObject
    writer=PdfWriter()
    def cff(chars):
        order=['.notdef']+[UV2AGL[ord(c)] for c in chars]
        fb=FontBuilder(1000,isTTF=False);fb.setupGlyphOrder(order)
        fb.setupCharacterMap({ord(c):UV2AGL[ord(c)] for c in chars})
        metrics={name:(500,0) for name in order};metrics['space']=(250,0)
        fb.setupHorizontalMetrics(metrics);fb.setupHorizontalHeader(ascent=800,descent=-200)
        fb.setupNameTable({'familyName':'Faro CFF','styleName':'Regular','uniqueFontIdentifier':'FaroCFF-Regular','fullName':'Faro CFF Regular','psName':'FaroCFF-Regular'})
        fb.setupOS2();fb.setupPost();strings={}
        for n,name in enumerate(order):
            pen=T2CharStringPen(metrics[name][0],None)
            if name not in ('.notdef','space'):
                pen.moveTo((30,0));pen.lineTo((250,600+n));pen.lineTo((470,0));pen.closePath()
            strings[name]=pen.getCharString()
        fb.setupCFF('FaroCFF-Regular',{'FullName':'Faro CFF Regular','FamilyName':'Faro CFF','Weight':'Regular'},strings,{})
        program=io.BytesIO();fb.font['CFF '].cff.compile(program,fb.font)
        stream=DecodedStreamObject();stream.set_data(program.getvalue());stream[NameObject('/Subtype')]=NameObject('/Type1C')
        desc=DictionaryObject({NameObject('/Type'):NameObject('/FontDescriptor'),NameObject('/FontName'):NameObject('/FaroCFF-Regular'),
            NameObject('/Flags'):NumberObject(32),NameObject('/FontBBox'):ArrayObject([NumberObject(0),NumberObject(-200),NumberObject(500),NumberObject(800)]),
            NameObject('/ItalicAngle'):NumberObject(0),NameObject('/Ascent'):NumberObject(800),NameObject('/Descent'):NumberObject(-200),
            NameObject('/CapHeight'):NumberObject(700),NameObject('/StemV'):NumberObject(80),NameObject('/FontFile3'):writer._add_object(stream)})
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/FaroCFF-Regular'),
            NameObject('/FontDescriptor'):writer._add_object(desc),NameObject('/FirstChar'):NumberObject(32),NameObject('/LastChar'):NumberObject(255),
            NameObject('/Widths'):ArrayObject([NumberObject(250 if i==32 else 500) for i in range(32,256)])})
        fb.font.close();return writer._add_object(font)
    main=cff(' AB')
    # Keep A in the same glyph position so overlap is demonstrably identical.
    other=cff(' ABprueba\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1')
    standard=writer._add_object(DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Times-Bold'),NameObject('/Encoding'):NameObject('/WinAnsiEncoding')}))
    for n in range(2):
        p=writer.add_blank_page(width=600,height=400)
        p[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):main,NameObject('/F2'):other,NameObject('/Times'):standard})})
        stream=DecodedStreamObject();stream.set_data(b'BT /Times 18 Tf 40 340 Td (Standard bold) Tj ET\nBT /F1 16 Tf 40 280 Td (ABA) Tj ET' if n==0 else b'BT /F2 16 Tf 40 280 Td (prueba) Tj ET')
        p[NameObject('/Contents')]=writer._add_object(stream)
    writer.write(path);return Path(path).read_bytes()


def close_probe(mode,report):
    """A separate real event loop must terminate, including its child OCR."""
    from PySide6.QtWidgets import QApplication,QDialog
    from PySide6.QtCore import QTimer,Qt,QSettings
    from app import Window
    app=QApplication([]);w=Window(updates_enabled=False);w.show()
    w.closed.connect(app.quit,Qt.ConnectionType.QueuedConnection)
    report=Path(report);source=report.with_suffix('.pdf');fixture(source);w.open_file(str(source))
    w.updates.settings=QSettings(str(report.with_suffix('.ini')),QSettings.Format.IniFormat)
    w.updates.root=report.parent/('probe-updates-'+mode)
    w.updates.ready=False;w.updates.candidate=None
    state={'mode':mode,'closed':False,'cancelled':False}
    w.closed.connect(lambda:state.update(closed=True))
    if mode=='dialogs':
        w.show_properties();w.show_pages();w.ocr.show_result(dict(changed=[],skipped=[0],empty=[]))
    elif mode=='ocr':
        assert w.ocr.start([0]);state['cancelled']=True
    elif mode=='updates':
        from update_checks import FixtureTransport
        transport=FixtureTransport();transport.delay=.3
        w.updates.transport=transport;w.updates.installed=False;w.updates.check()
    QTimer.singleShot(20,w.close)
    QTimer.singleShot(20000,lambda:app.exit(9))
    code=app.exec()
    state['exit_code']=code
    state['passed']=code==0 and state['closed'] and w.model is None and not w.ocr.busy and w.updates.worker is None
    report.write_text(json.dumps(state),encoding='utf-8')
    app.clipboard().clear()
    return 0 if state['passed'] else 1


def check_font_lifecycle(window,app,work):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox
    from PySide6.QtTest import QTest
    from unittest.mock import patch
    from engine import TEXT,IMAGE,Document
    from typography import Catalog,font_style
    work=Path(work)/'fuentes y cierre';work.mkdir(parents=True,exist_ok=True)
    source=work/'fuentes.pdf';original=fixture(source)
    catalog=Catalog()
    assert catalog.matching('Times-Bold')[0].bold
    assert catalog.matching('Times-Italic')[0].italic
    assert catalog.matching('TimesNewRomanPS-BoldMT')[0].bold
    if window.model:window.model.saved_version=window.model.current_version
    window.open_file(str(source));window.set_mode('text');app.processEvents()
    model=window.model
    standard=next(i for i,o in enumerate(model.objects) if o.type==TEXT and model.info(i)['font']=='Times-Bold')
    assert model.info(standard)['weight']>=600
    window.select(standard);window.inline.begin(standard);assert window.inline.active,window.inline.status.text()
    window.inline.cancel()
    from PIL import Image
    image=work/'objeto.png';Image.new('RGB',(40,30),'teal').save(image)
    model.add_image(image,440,340,60);window.render_page();window.set_mode('images')
    image_index=next(i for i,o in enumerate(model.objects) if o.type==IMAGE)
    model.move(image_index,4,-3);window.render_page();window.set_mode('text')
    window.select(standard);window.inline.begin(standard);assert window.inline.active
    window.inline.editor.setPlainText('Standard bold prueba');assert window.inline.commit(),window.inline.status.text()
    model.undo();window.render_page()
    cff_index=next(i for i,o in enumerate(model.objects) if o.type==TEXT and model.info(i)['font']=='FaroCFF-Regular')
    value='prueba \u00e1\u00e9\u00ed\u00f3\u00fa\u00f1'
    before=model._data;old_page=model.doc[1];bm=old_page.render(scale=1);pixels=bm.to_pil().tobytes();bm.close();old_page.close()
    model.apply_inline(cff_index,value,16)
    assert value in model.textpage.get_text_bounded()
    other=model.doc[1];bm=other.render(scale=1)
    assert bm.to_pil().tobytes()==pixels;bm.close();other.close()
    model.save(work/'ampliado.pdf');reopen=Document(work/'ampliado.pdf')
    assert value in reopen.textpage.get_text_bounded();reopen.close();model.undo();assert model._data==before
    # A pending invalid edit must offer an explicit discard rather than trap
    # the user in a window that refuses every close attempt.
    window.render_page();window.set_mode('text');window.select(standard);window.inline.begin(standard)
    with patch.object(window.inline,'commit',return_value=False),patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Discard):
        assert window.confirm_discard() and not window.inline.active
    # Public/frozen executable must exit as an OS process, not just hide its UI.
    for mode in ('dialogs','ocr','updates'):
        report=work/('close-'+mode+'.json')
        command=[sys.executable]
        if not getattr(sys,'frozen',False):command.append(str(Path(__file__).with_name('app.py')))
        command.extend(['--close-probe',mode,str(report)])
        result=subprocess.run(command,env={**os.environ,'QT_QPA_PLATFORM':'offscreen'},
                              stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=60,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert result.returncode==0,(mode,result.returncode,report.read_text() if report.exists() else '',result.stderr.decode('utf-8','replace')[-2500:])
        assert json.loads(report.read_text())['passed']
    assert source.read_bytes()==original
    return dict(font_standard14_styles_image_to_text=True,cff_original_subsets_new_words_accents_save_undo=True,
                close_invalid_edit_explicit_discard=True,close_process_with_dialogs_ocr_updates=True)
