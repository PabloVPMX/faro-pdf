"""Page-local text streams whose fonts are independent of original PDF text."""
import ctypes as C
import io
import uuid

import pypdfium2 as pdf
from pypdf import PdfReader
from pypdf.generic import (NameObject, DictionaryObject, ArrayObject, FloatObject,
                           NumberObject, TextStringObject, DecodedStreamObject)
from content_patch import _Font
from insertions import writer_for, finish, resource, append_content


def records(data, index):
    reader = PdfReader(io.BytesIO(data))
    page = reader.pages[index]
    metadata = page.get('/FaroTextData', {})
    if not metadata:
        return {}
    groups = {str(key): [] for key in metadata}
    document = pdf.PdfDocument(data)
    try:
        target = document[index]
        ordinal = 0
        for obj in target.get_objects(max_depth=0):
            if obj.type != pdf.raw.FPDF_PAGEOBJ_TEXT:
                continue
            for i in range(pdf.raw.FPDFPageObj_CountMarks(obj)):
                mark = pdf.raw.FPDFPageObj_GetMark(obj, i)
                length = C.c_ulong()
                if not pdf.raw.FPDFPageObjMark_GetName(mark, None, 0, C.byref(length)) or not 0 < length.value <= 4096:
                    continue
                buffer = C.create_string_buffer(length.value)
                if pdf.raw.FPDFPageObjMark_GetName(mark, C.cast(buffer,C.POINTER(C.c_ushort)), length.value, C.byref(length)):
                    key = '/'+buffer.raw.decode('utf-16-le').rstrip('\0')
                    if key in groups:
                        groups[key].append(ordinal)
            ordinal += 1
    finally:
        document.close()
    result = {}
    for key, indices in groups.items():
        meta = metadata[key].get_object()
        owned = '/Stream' in meta
        if owned:
            # Validate only this independently encoded font and stream.
            payload = meta['/Stream'].get_data()
            if not payload.startswith((key+' BMC\nq\n').encode('ascii')) or not payload.endswith(b'Q\nEMC\n'):
                raise ValueError('No se pudo verificar el cuadro de texto añadido.')
            _Font(page['/Resources']['/Font'][meta['/Font']].get_object())
        result[key] = dict(ordinals=indices, meta=meta, owned=owned)
    return result


def body(page, key, text, size, matrix, color, font_name, box):
    from text_layout import wrapped_lines, num
    import math
    text = text.replace('\r\n','\n').replace('\r','\n')
    if any(not c.isprintable() and c != '\n' for c in text):
        raise ValueError('El cuadro contiene caracteres de control no admitidos.')
    font = _Font(page['/Resources']['/Font'][font_name].get_object())
    if box:
        width = max(1,(box[2]-box[0])/max(math.hypot(matrix[0],matrix[1]),1e-8))
        lines = wrapped_lines(text,font,size,width,page['/Resources']['/Font'][font_name]['/BaseFont'])
    else:
        lines=[];start=0
        for line in text.split('\n'):
            lines.append((start,line));start+=len(line)+1
    a,b,c,d,e,f = matrix
    commands = [key+' BMC','q',' '.join(num(v/255) for v in color)+' rg','BT',
                f'{font_name} {num(size)} Tf','0 Tc 0 Tw 100 Tz 0 Ts 0 Tr']
    for row,(_,line) in enumerate(lines):
        transform=(a,b,c,d,e-c*size*1.3*row,f-d*size*1.3*row)
        commands.append(' '.join(num(v) for v in transform)+' Tm <'+font.edit(b'',line).hex()+'> Tj')
    commands += ['ET','Q','EMC']
    meta = DictionaryObject({NameObject('/Text'):TextStringObject(text),
        NameObject('/Matrix'):ArrayObject([FloatObject(v) for v in matrix]),
        NameObject('/Size'):FloatObject(size),NameObject('/Font'):NameObject(font_name),
        NameObject('/Color'):ArrayObject([NumberObject(v) for v in color])})
    if box:
        meta[NameObject('/Box')]=ArrayObject([FloatObject(v) for v in box])
        meta[NameObject('/Lines')]=ArrayObject([TextStringObject(line) for _,line in lines])
        meta[NameObject('/Starts')]=ArrayObject([NumberObject(start) for start,_ in lines])
    return ('\n'.join(commands)+'\n').encode('ascii'),meta


def add(data,index,text,x,top,size=12,font='Helvetica',color=(13,43,49),face=None,box=None):
    from text_layout import add_font
    writer = writer_for(data);page=writer.pages[index]
    if face:
        name=add_font(writer,page,face)
    else:
        fonts=resource(page,'/Font');name=NameObject('/FaroText'+uuid.uuid4().hex)
        fonts[name]=writer._add_object(DictionaryObject({NameObject('/Type'):NameObject('/Font'),
            NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/'+font),
            NameObject('/Encoding'):NameObject('/WinAnsiEncoding')}))
    key='/FaroBlock'+uuid.uuid4().hex
    payload,meta=body(page,key,text,size,(1,0,0,1,x,top-size*.85),color,name,box)
    append_content(writer,page,payload)
    meta[NameObject('/Stream')]=page['/Contents'][-1]
    values=DictionaryObject(dict(page.get('/FaroTextData',{})));values[NameObject(key)]=meta
    page[NameObject('/FaroTextData')]=values
    return finish(writer),key


def replace(data,index,key,value,size,face=None,color=None,box=None,matrix=None):
    from text_layout import add_font
    writer=writer_for(data);page=writer.pages[index]
    old=page['/FaroTextData'][key].get_object()
    reference=old.raw_get('/Stream')
    contents=page.raw_get('/Contents');resolved=contents.get_object()
    items=list(resolved) if isinstance(resolved,ArrayObject) else [contents]
    matching=[i for i,ref in enumerate(items) if getattr(ref,'idnum',None)==reference.idnum
              and getattr(ref,'generation',None)==reference.generation]
    combined=None
    if not matching:
        # Image/native-operator edits can consolidate the page's content array.
        # Recover only our exact, previously generated bytes, leaving all other
        # operators byte-for-byte unchanged; never parse/rewrite foreign fonts.
        previous=reference.get_object().get_data()
        locations=[]
        for i,ref in enumerate(items):
            raw=ref.get_object().get_data()
            if raw.count(previous):locations.extend((i,raw) for _ in range(raw.count(previous)))
        if len(locations)==1:
            matching=[locations[0][0]];combined=locations[0][1].split(previous,1)
    if len(matching)!=1:raise ValueError('No se encontró un único contenido verificable del cuadro de texto.')
    name=add_font(writer,page,face) if face else old['/Font']
    matrix=matrix or tuple(map(float,old['/Matrix']))
    box=box or (tuple(map(float,old['/Box'])) if '/Box' in old else None)
    color=color or tuple(map(int,old['/Color']))
    payload,meta=body(page,key,value,size,matrix,color,name,box)
    stream=DecodedStreamObject();stream.set_data(payload)
    meta[NameObject('/Stream')]=writer._add_object(stream)
    if combined is None:
        items[matching[0]]=meta.raw_get('/Stream')
    else:
        fragments=[]
        for data in combined:
            fragment=DecodedStreamObject();fragment.set_data(data);fragments.append(writer._add_object(fragment))
        items[matching[0]:matching[0]+1]=[fragments[0],meta.raw_get('/Stream'),fragments[1]]
    page[NameObject('/Contents')]=ArrayObject(items)
    values=DictionaryObject(dict(page['/FaroTextData']));values[NameObject(key)]=meta
    page[NameObject('/FaroTextData')]=values
    return finish(writer),key


def move(data,index,key,dx,dy):
    meta=records(data,index)[key]['meta']
    matrix=list(map(float,meta['/Matrix']));matrix[4]+=dx;matrix[5]+=dy
    box=None
    if '/Box' in meta:
        l,b,r,t=map(float,meta['/Box']);box=(l+dx,b+dy,r+dx,t+dy)
    return replace(data,index,key,str(meta['/Text']),float(meta['/Size']),box=box,matrix=matrix)[0]
