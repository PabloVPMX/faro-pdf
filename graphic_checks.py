"""Regression for outlined text and images in pages with persistent transforms."""
import io
from pathlib import Path


def fixture(path):
    from PIL import Image,ImageDraw
    from pypdf import PdfWriter
    from pypdf.generic import NameObject,DictionaryObject,ArrayObject,DecodedStreamObject,NumberObject
    import zlib
    writer=PdfWriter();page=writer.add_blank_page(width=595,height=842)
    image=Image.new('RGB',(100,55),'white');draw=ImageDraw.Draw(image)
    draw.ellipse((8,3,91,31),outline='#263746',width=4)
    draw.rectangle((10,39,90,49),fill='#c5202b')
    obj=DecodedStreamObject();obj.set_data(image.tobytes())
    obj.update({NameObject('/Type'):NameObject('/XObject'),NameObject('/Subtype'):NameObject('/Image'),
                NameObject('/Width'):NumberObject(100),NameObject('/Height'):NumberObject(55),
                NameObject('/ColorSpace'):NameObject('/DeviceRGB'),NameObject('/BitsPerComponent'):NumberObject(8)})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/XObject'):DictionaryObject({NameObject('/Logo'):writer._add_object(obj.flate_encode())})})
    streams=[]
    def content(raw):
        stream=DecodedStreamObject();stream.set_data(raw);streams.append(writer._add_object(stream))
    # A global flipped coordinate system and separate streams reproduce the
    # serializer's lingering-transform failure when almost all paths are removed.
    content(b'.75 0 0 -.75 0 842 cm\n')
    for row in range(5):
        body=['1 0 0 1 9 11 cm']
        for col in range(25):
            x=55+col*13;y=220+row*28
            # Filled vector glyph outlines (no PDF text/font objects).
            body.append(f'q 1 0 0 1 {x} {y} cm 0 0 m 3 0 l 7 15 l 10 0 l 13 0 l 8 20 l 5 20 l h f Q')
        content(('\n'.join(body)+'\n').encode())
    content(b'q 160 0 0 -88 55 130 cm /Logo Do Q\n')
    content(b'q 0 0 0 RG 2 w 30 40 700 100 re S Q\n')
    page[NameObject('/Contents')]=ArrayObject(streams)
    writer.add_blank_page(width=595,height=842)
    writer.write(path)
    return Path(path).read_bytes()


def check_graphics(window,app,work):
    from engine import IMAGE,pdf
    from graphic_objects import PATH,selection_groups,hit_test
    from object_transfer import export_objects,paste_objects,mutate_objects,validate_change
    from content_patch import _operations
    from pypdf import PdfReader
    from pypdf.generic import ContentStream
    from PySide6.QtCore import QPointF,Qt
    from PySide6.QtTest import QTest
    work=Path(work)/'graficos vectoriales';work.mkdir(exist_ok=True)
    source=work/'contornos.pdf';original=fixture(source)
    if window.model:window.model.saved_version=window.model.current_version
    window.open_file(str(source));window.set_mode('objects');app.processEvents()
    model=window.model;selection=window.object_selection
    assert not any(o.type==pdf.raw.FPDF_PAGEOBJ_TEXT for o in model.objects)
    image=next(i for i,o in enumerate(model.objects) if o.type==IMAGE)
    glyphs=next(g for g,b,k in selection.candidates() if k==PATH and len(g)>=20)
    assert len(glyphs)==25
    border=next(g[0] for g,b,k in selection.candidates() if k==PATH and len(g)==1 and b[2]-b[0]>400)
    l,b,r,t=model.objects[border].get_bounds()
    assert not hit_test(model,border,(l+r)/2,(b+t)/2,2)
    assert hit_test(model,border,l,(b+t)/2,2)
    for groups in ([(image,)],[glyphs],[glyphs,(image,)]):
        packet=export_objects(model,groups)
        read=PdfReader(io.BytesIO(packet))
        assert not read.pages[0].extract_text(), 'Outlined text must remain vector paths'
        after,box=paste_objects(model._data,0,packet,anchor=(60,400))
        validate_change(model,after,[box])
        target=pdf.PdfDocument(after);page=target[0]
        try:
            assert sum(o.type==PATH for o in page.get_objects(max_depth=0))==sum(o.type==PATH for o in model.objects)+(len(glyphs) if glyphs in groups else 0)
        finally:page.close();target.close()
    # Image and outlined words cut/move together, with one history entry.
    groups=[glyphs,(image,)];snapshot=model._data;history=len(model.undo_stack)
    mutate_objects(model,groups,dx=16,dy=-12)
    assert len(model.undo_stack)==history+1
    model.undo();assert model._data==snapshot
    mutate_objects(model,groups,delete=True)
    assert not any(o.type==IMAGE for o in model.objects)
    assert sum(o.type==PATH for o in model.objects)==126-len(glyphs)
    model.undo();assert model._data==snapshot
    selection.groups=groups;selection.draw();selection.copy()
    assert app.clipboard().mimeData().hasImage(),'Vector-only graphics need an image clipboard fallback'
    # The fast numeric lexer must agree with the independent PDF parser.
    raw=b'q +1 -.25 0.75 1. 5 -7 cm 10 20 m .2 -0.0 l /F1 12 Tf [(x) -20.25 (y)] TJ Q'
    stream=ContentStream(None,None);stream.set_data(raw)
    parsed=_operations(raw)
    assert [(op.operands,op.operator) for op in parsed]==stream.operations
    assert all(op.span[0]<op.span[1] for op in parsed)
    assert source.read_bytes()==original
    window.render_page();selection.groups=groups;selection.draw();app.processEvents()
    window.grab().save(str(work/'contornos-seleccion.png'))
    return dict(graphic_image_copy_persistent_matrix_preserved=True,
                graphic_outlined_text_copy_cut_move_paste_undo=True,
                graphic_numeric_lexer_matches_independent_parser=True)
