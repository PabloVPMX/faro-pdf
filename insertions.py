"""Append content without regenerating any original page objects."""
import io,zlib
from pathlib import Path
from PIL import Image,ImageOps
from pypdf import PdfReader,PdfWriter
from pypdf.generic import DictionaryObject,NameObject,NumberObject,ArrayObject,DecodedStreamObject,EncodedStreamObject

def writer_for(data):
    r=PdfReader(io.BytesIO(data));w=PdfWriter(r,incremental=True)
    while len(w._objects)<int(r.trailer['/Size'])-1:w._objects.append(None)
    return w

def finish(w):
    out=io.BytesIO();w.write(out);return out.getvalue()

def resource(page,kind):
    # Page-local copies avoid changing resources shared by another page.
    resources=DictionaryObject(dict(page['/Resources']))
    table=DictionaryObject(dict(resources.get(kind,{}).get_object() if hasattr(resources.get(kind,{}),'get_object') else resources.get(kind,{})))
    resources[NameObject(kind)]=table;page[NameObject('/Resources')]=resources
    return table

def append_content(w,page,payload):
    old=page.get('/Contents')
    resolved=old.get_object() if old else None
    items=list(resolved) if isinstance(resolved,ArrayObject) else [old] if old else []
    new=DecodedStreamObject();new.set_data(payload)
    start=DecodedStreamObject();start.set_data(b'q\n')
    end=DecodedStreamObject();end.set_data(b'Q\n')
    page[NameObject('/Contents')]=ArrayObject([w._add_object(start)]+items+[w._add_object(end),w._add_object(new)])

def add_text(data,index,value,x,top,size,font,color):
    w=writer_for(data);page=w.pages[index];fonts=resource(page,'/Font')
    name=NameObject('/FaroText'+str(len(fonts)))
    fonts[name]=w._add_object(DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/'+font),NameObject('/Encoding'):NameObject('/WinAnsiEncoding')}))
    parts=['q',' '.join(str(c/255) for c in color)+' rg']
    for row,line in enumerate(value.splitlines()):
        try:encoded=line.encode('cp1252')
        except UnicodeEncodeError:raise ValueError('La fuente seleccionada para insertar texto admite caracteres latinos. Elige un texto compatible.')
        parts.append(f'BT {name} {size:g} Tf 1 0 0 1 {x:g} {top-size*.85-row*size*1.3:g} Tm <{encoded.hex()}> Tj ET')
    parts.append('Q');append_content(w,page,('\n'.join(parts)+'\n').encode('ascii'))
    return finish(w)

def add_image(data,index,path,x,top,width):
    w=writer_for(data);page=w.pages[index]
    with Image.open(path) as source:
        image=ImageOps.exif_transpose(source).convert('RGBA')
    height=width*image.height/image.width
    def stream(pixels,space):
        obj=EncodedStreamObject();obj._data=zlib.compress(pixels)
        for key,value in {'/Type':NameObject('/XObject'),'/Subtype':NameObject('/Image'),'/Width':NumberObject(image.width),'/Height':NumberObject(image.height),'/ColorSpace':NameObject(space),'/BitsPerComponent':NumberObject(8),'/Filter':NameObject('/FlateDecode')}.items():obj[NameObject(key)]=value
        return obj
    obj=stream(image.convert('RGB').tobytes(),'/DeviceRGB')
    alpha=image.getchannel('A')
    if alpha.getextrema()!=(255,255):obj[NameObject('/SMask')]=w._add_object(stream(alpha.tobytes(),'/DeviceGray'))
    images=resource(page,'/XObject');name=NameObject('/FaroImage'+str(len(images)))
    images[name]=w._add_object(obj)
    append_content(w,page,f'q {width:g} 0 0 {height:g} {x:g} {top-height:g} cm {name} Do Q\n'.encode('ascii'))
    return finish(w)

def insert_pdfs(data,paths,position):
    w=writer_for(data)
    for path in paths:
        reader=PdfReader(str(path))
        if reader.is_encrypted:raise ValueError('El PDF está protegido: '+Path(path).name)
        for page in reader.pages:
            w.insert_page(page,position);position+=1
    return finish(w)

def compose(a,b):
    aa,ab,ac,ad,ae,af=a;ba,bb,bc,bd,be,bf=b
    return (aa*ba+ac*bb,ab*ba+ad*bb,aa*bc+ac*bd,ab*bc+ad*bd,aa*be+ac*bf+ae,ab*be+ad*bf+af)

def transform_image(data,index,ordinal,expected,transform=None):
    """Patch one image Do; leave every original text/path operator untouched."""
    from content_patch import _operations
    from pypdf.generic import ContentStream
    import re
    w=writer_for(data);page=w.pages[index]
    raw=ContentStream(page.get('/Contents'),w).get_data()
    matrix=(1,0,0,1,0,0);stack=[];number=-1
    objects=page['/Resources'].get('/XObject',{})
    objects=objects.get_object() if hasattr(objects,'get_object') else objects
    for op in _operations(raw):
        if op.operator==b'q':stack.append(matrix)
        elif op.operator==b'Q':matrix=stack.pop()
        elif op.operator==b'cm':matrix=compose(matrix,tuple(float(v) for v in op.operands))
        elif op.operator==b'Do' and objects[op.operands[0]].get_object().get('/Subtype')=='/Image':
            number+=1
            if number!=ordinal:continue
            if any(abs(a-b)>max(1e-4,abs(b)*1e-5) for a,b in zip(matrix,expected)):
                raise ValueError('No coincide la transformación original de la imagen; el PDF se conserva.')
            start,end=op.spans[0];match=re.match(rb'\s*Do\b',raw[end:])
            if not match:raise ValueError('No se pudo localizar la imagen con seguridad.')
            stop=end+match.end()
            if transform is None:replacement=b''
            else:
                a,b,c,d,e,f=matrix;det=a*d-b*c
                if abs(det)<1e-12:raise ValueError('La imagen tiene una transformación degenerada.')
                inverse=(d/det,-b/det,-c/det,a/det,(c*f-d*e)/det,(b*e-a*f)/det)
                local=compose(compose(inverse,transform),matrix)
                # PDF numbers do not permit exponent notation. Numerical
                # cancellation during conjugation can produce 1e-14 offsets.
                numbers=[format(v,'.10f').rstrip('0').rstrip('.') or '0' for v in local]
                replacement=b'q '+(' '.join(numbers)).encode('ascii')+b' cm '+raw[start:end]+b' Do Q'
            stream=DecodedStreamObject();stream.set_data(raw[:start]+replacement+raw[stop:])
            page[NameObject('/Contents')]=w._add_object(stream)
            return finish(w)
    raise ValueError('No se encontró la aparición original de la imagen.')

def rearrange_pages(data,source,destination=None):
    w=writer_for(data)
    if destination is None:
        if len(w.pages)<=1:raise ValueError('El documento debe conservar al menos una página.')
        del w.pages[source]
    else:
        page=w.pages[source]
        del w.pages[source]
        w.insert_page(page,destination)
    return finish(w)
