"""Copy PDF objects with their font/image resources; never rasterize pasted text."""
import ctypes as C
import io
import math
import hashlib
import uuid

import pypdfium2 as pdf
from pypdf import PdfReader, PdfWriter, PageObject
from pypdf.generic import NameObject, DictionaryObject, ArrayObject, ContentStream, DecodedStreamObject
from insertions import writer_for, finish, resource, append_content, compose

TEXT, IMAGE = pdf.raw.FPDF_PAGEOBJ_TEXT, pdf.raw.FPDF_PAGEOBJ_IMAGE


def union(boxes):
    return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)


def inverse(m):
    a,b,c,d,e,f=m; det=a*d-b*c
    if abs(det)<1e-12: raise ValueError('La transformación del objeto no es válida.')
    return d/det,-b/det,-c/det,a/det,(c*f-d*e)/det,(b*e-a*f)/det


def point(m,x,y):
    a,b,c,d,e,f=m
    return a*x+c*y+e,b*x+d*y+f


def bounds_transform(bounds,m):
    points=[point(m,x,y) for x in (bounds[0],bounds[2]) for y in (bounds[1],bounds[3])]
    xs,ys=zip(*points)
    return min(xs),min(ys),max(xs),max(ys)


def display_matrix(page):
    l,b,r,t=map(float,page.cropbox)
    return {0:(1,0,0,1,l,b),90:(0,1,-1,0,r,b),
            180:(-1,0,0,-1,r,t),270:(0,-1,1,0,l,t)}[page.rotation%360]


def font_digest(font):
    """Stable across PDF object IDs; include all font programs and encodings."""
    from pypdf.generic import StreamObject
    def freeze(value):
        value=value.get_object() if hasattr(value,'get_object') else value
        if isinstance(value,dict):
            result=[(str(k),freeze(v)) for k,v in sorted(value.items()) if str(k) not in ('/Length','/Filter','/DecodeParms')]
            if isinstance(value,StreamObject):result.append(('decoded',hashlib.sha256(value.get_data()).hexdigest()))
            return result
        if isinstance(value,(list,tuple)):return [freeze(v) for v in value]
        if isinstance(value,bytes):return ('bytes',value.hex())
        return (type(value).__name__,str(value))
    return hashlib.sha256(repr(freeze(font)).encode('utf-8')).hexdigest()


def append_owned(writer,page,source,meta,transform):
    """Clone the exact embedded font and rebuild an independent editable block."""
    from owned_text import body
    font=source['/Resources']['/Font'][meta['/Font']]
    digest=font_digest(font);font_name=NameObject('/FaroCopyFont'+digest[:24])
    fonts=resource(page,'/Font')
    if font_name in fonts and font_digest(fonts[font_name])!=digest:
        font_name=NameObject(str(font_name)+uuid.uuid4().hex)
    if font_name not in fonts:fonts[font_name]=font.clone(writer)
    matrix=compose(transform,tuple(map(float,meta['/Matrix'])))
    box=bounds_transform(tuple(map(float,meta['/Box'])),transform) if '/Box' in meta else None
    key='/FaroBlock'+uuid.uuid4().hex
    payload,created=body(page,key,str(meta['/Text']),float(meta['/Size']),matrix,
                         tuple(map(int,meta['/Color'])),font_name,box)
    append_content(writer,page,payload)
    created[NameObject('/Stream')]=page['/Contents'][-1]
    values=DictionaryObject(dict(page.get('/FaroTextData',{})))
    values[NameObject(key)]=created;page[NameObject('/FaroTextData')]=values


def export_objects(model,groups):
    indices=sorted({i for group in groups for i in group})
    if not indices: raise ValueError('Selecciona una imagen o un cuadro de texto.')
    from text_layout import block_records
    own=block_records(model._edit_data,model.index)
    ordinals=[i for i,o in enumerate(model.objects) if o.type==TEXT]
    selected_owned={key:rec for key,rec in own.items() if rec.get('owned') and
                    set(ordinals[n] for n in rec['ordinals']).issubset(indices) and rec['ordinals']}
    own_indices={ordinals[n] for rec in selected_owned.values() for n in rec['ordinals']}
    wanted=set(indices)-own_indices
    document=pdf.PdfDocument(model._edit_data)
    page=document[model.index]
    objects=list(page.get_objects(max_depth=0))
    bitmaps=[]
    try:
        if len(objects)!=len(model.objects): raise ValueError('La selección ya no coincide con el documento.')
        for i,obj in reversed(list(enumerate(objects))):
            if i not in wanted: page.remove_obj(obj);obj.close()
        # Preserve named colors when PDFium serializes the isolated fragment.
        for i in wanted:
            obj=objects[i]
            if obj.type!=TEXT: continue
            for getter,setter in ((pdf.raw.FPDFPageObj_GetFillColor,pdf.raw.FPDFPageObj_SetFillColor),
                                  (pdf.raw.FPDFPageObj_GetStrokeColor,pdf.raw.FPDFPageObj_SetStrokeColor)):
                values=[C.c_uint() for _ in range(4)]
                if getter(obj,*[C.byref(v) for v in values]): setter(obj,*[v.value for v in values])
        width,height=page.get_size();scale=min(2,math.sqrt(2_000_000/max(1,width*height)))
        before=page.render(scale=scale,draw_annots=False);bitmaps.append(before)
        page.gen_content()
        output=io.BytesIO();document.save(output)
        reader=PdfReader(io.BytesIO(output.getvalue()))
        isolated=reader.pages[model.index]
        for key in ('/Annots','/FaroTextData'):isolated.pop(NameObject(key),None)
        # Do not copy unused fonts/images from the original page. Image masks
        # and font programs remain reachable through the selected resources.
        operations=ContentStream(isolated.get_contents(),reader).operations
        # PDFium may leave ignored surplus Q operators after objects are removed.
        # Keep the private fragment balanced before appending it to other content.
        balanced=[];depth=0
        for operands,operator in operations:
            if operator==b'q':depth+=1
            elif operator==b'Q':
                if depth==0:continue
                depth-=1
            balanced.append((operands,operator))
        balanced.extend(([],b'Q') for _ in range(depth))
        stream=ContentStream(None,reader);stream.operations=balanced
        isolated[NameObject('/Contents')]=stream
        operations=balanced
        needed={'/Font':set(),'/XObject':set(),'/ExtGState':set()}
        kinds={b'Tf':'/Font',b'Do':'/XObject',b'gs':'/ExtGState'}
        for operands,operator in operations:
            if operator in kinds and operands:needed[kinds[operator]].add(str(operands[0]))
        resources=DictionaryObject(dict(isolated['/Resources']))
        for kind,names in needed.items():
            values=resources.get(kind,{})
            values=values.get_object() if hasattr(values,'get_object') else values
            resources[NameObject(kind)]=DictionaryObject({name:value for name,value in values.items() if str(name) in names})
        isolated[NameObject('/Resources')]=resources
        writer=PdfWriter();target=writer.add_page(isolated)
        native=finish(writer)
        check=pdf.PdfDocument(native);checkpage=check[0]
        try:
            after=checkpage.render(scale=scale,draw_annots=False)
            try:
                if before.to_pil().tobytes()!=after.to_pil().tobytes():
                    raise ValueError('No se pudo copiar este objeto sin cambiar su apariencia.')
            finally:after.close()
        finally:checkpage.close();check.close()
        original=PdfReader(io.BytesIO(model._edit_data)).pages[model.index]
        writer=writer_for(native);target=writer.pages[0]
        for rec in selected_owned.values(): append_owned(writer,target,original,rec['meta'],(1,0,0,1,0,0))
        return finish(writer)
    finally:
        for bitmap in bitmaps:bitmap.close()
        page.close();document.close()


def packet_bounds(data):
    document=pdf.PdfDocument(data);page=document[0]
    try:
        boxes=[o.get_bounds() for o in page.get_objects(max_depth=0) if o.type in (TEXT,IMAGE)]
        if not boxes:raise ValueError('El portapapeles no contiene objetos PDF seleccionables.')
        return union(boxes)
    finally:page.close();document.close()


def paste_objects(data,index,packet,anchor=None,offset=12):
    if not packet.startswith(b'%PDF-'):raise ValueError('El fragmento del portapapeles no es un PDF válido.')
    source_reader=PdfReader(io.BytesIO(packet))
    if len(source_reader.pages)!=1:raise ValueError('El fragmento del portapapeles no es válido.')
    source=source_reader.pages[0]
    writer=writer_for(data);target=writer.pages[index]
    source_display=display_matrix(source);target_display=display_matrix(target)
    bounds=bounds_transform(packet_bounds(packet),inverse(source_display))
    if anchor:
        x,y=point(inverse(target_display),*anchor)
    else:x,y=bounds[0]+offset,bounds[3]-offset
    crop=target.cropbox
    width,height=float(crop.width),float(crop.height)
    if target.rotation%180:width,height=height,width
    x=max(0,min(x,max(0,width-(bounds[2]-bounds[0]))))
    y=min(height,max(min(height,bounds[3]-bounds[1]),y))
    transform=compose(target_display,compose((1,0,0,1,x-bounds[0],y-bounds[3]),inverse(source_display)))
    # Remove only owned blocks from a private working copy of the packet. Their
    # separate streams/metadata are appended below with fresh block/resource IDs.
    from owned_text import records,replace
    owned={key:rec for key,rec in records(packet,0).items() if rec.get('owned')}
    native=packet
    for key,rec in owned.items():native=replace(native,0,key,'',float(rec['meta']['/Size']))[0]
    native_reader=PdfReader(io.BytesIO(native))
    # Merging directly into the target causes pypdf.replace_contents to null
    # streams still referenced by existing editable-block metadata. Rename and
    # transform on a scratch page, then append without touching original streams.
    scratch=PageObject.create_blank_page(width=float(target.mediabox.width),height=float(target.mediabox.height))
    writer._add_object(scratch)
    resources=DictionaryObject()
    for name,value in target['/Resources'].items():
        value=value.get_object()
        resources[name]=DictionaryObject(dict(value)) if isinstance(value,dict) else ArrayObject(value) if isinstance(value,list) else value
    scratch[NameObject('/Resources')]=resources
    scratch.merge_transformed_page(native_reader.pages[0],transform,over=True,expand=False)
    target[NameObject('/Resources')]=scratch['/Resources']
    contents=scratch.get_contents()
    if contents is not None:append_content(writer,target,contents.get_data())
    for rec in owned.values():append_owned(writer,target,source,rec['meta'],transform)
    result=finish(writer)
    from owned_text import records
    records(result,index)
    return result,bounds_transform(packet_bounds(packet),transform)


def mutate_objects(model,groups,dx=0,dy=0,delete=False):
    """Build changes privately and commit all selected objects as one undo step."""
    from owned_text import records,move,replace
    from content_patch import patch_native
    from text_layout import move_text
    from insertions import transform_image
    data=model._edit_data
    text_indices=[i for i,o in enumerate(model.objects) if o.type==TEXT]
    own=records(data,model.index)
    tasks=[]
    for group in groups:
        ordinals=[text_indices.index(i) for i in group if model.objects[i].type==TEXT]
        if any(rec.get('owned') and rec['ordinals']==ordinals and ordinals for rec in own.values()):tasks.append(group)
        else:tasks.extend((i,) for i in group)
    all_indices=sorted({i for g in groups for i in g})
    pending=set(all_indices)
    for group in sorted(tasks,key=max,reverse=True):
        group=sorted(set(group)&pending)
        if not group:continue
        obj=model.objects[group[0]]
        if obj.type==IMAGE:
            ordinal=sum(o.type==IMAGE for o in model.objects[:group[0]])
            data=transform_image(data,model.index,ordinal,obj.get_matrix().get(),None if delete else (1,0,0,1,dx,dy))
        else:
            ordinals=[text_indices.index(i) for i in group]
            owned=next(((key,rec) for key,rec in own.items() if rec.get('owned') and rec['ordinals']==ordinals),None)
            if owned:
                key,rec=owned
                data=replace(data,model.index,key,'',float(rec['meta']['/Size']))[0] if delete else move(data,model.index,key,dx,dy)
            elif delete:
                for i,ordinal in reversed(list(zip(group,ordinals))):
                    data=patch_native(data,model.index,ordinal,model.info(i)['text'],'')
            else:
                # Move each line separately so intervening paths/table borders
                # are never included in the transformed text range.
                for ordinal in ordinals:data=move_text(data,model.index,[ordinal],dx,dy)
        pending.difference_update(group)
    old=[model.objects[i].get_bounds() for i in all_indices]
    boxes=old if delete else old+[bounds_transform(b,(1,0,0,1,dx,dy)) for b in old]
    validate_change(model,data,boxes)
    model.install_bytes('Borrar selección' if delete else 'Mover selección',data)


def validate_change(model,data,boxes):
    import numpy as np
    candidate=pdf.PdfDocument(data);page=candidate[model.index]
    bitmaps=[]
    try:
        if len(candidate)!=len(model.doc) or page.get_size()!=model.page.get_size():
            raise ValueError('El cambio alteró la estructura de páginas.')
        w,h=page.get_size();scale=min(2,math.sqrt(4_000_000/max(1,w*h)))
        bitmaps=[model.page.render(scale=scale),page.render(scale=scale)]
        arrays=[np.asarray(b.to_pil().convert('RGB')).copy() for b in bitmaps]
        changed=np.any(arrays[0]!=arrays[1],axis=2)
        for l,b,r,t in boxes:
            points=[]
            for x in (l-2,r+2):
                for y in (b-2,t+2):
                    sx,sy=C.c_int(),C.c_int()
                    pdf.raw.FPDF_PageToDevice(model.page,0,0,bitmaps[0].width,bitmaps[0].height,0,x,y,C.byref(sx),C.byref(sy))
                    points.append((sx.value,sy.value))
            xs,ys=zip(*points)
            changed[max(0,min(ys)):max(0,max(ys)+1),max(0,min(xs)):max(0,max(xs)+1)]=False
        if changed.any():raise ValueError('El cambio alteraba contenido fuera de la selección; el PDF se conserva.')
    finally:
        for bitmap in bitmaps:bitmap.close()
        page.close();candidate.close()
