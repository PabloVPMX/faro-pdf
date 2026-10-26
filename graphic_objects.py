"""Extract/move PDF painting operators without regenerating the page."""
import io
import ctypes as C
from functools import lru_cache

import pypdfium2 as pdf
from pypdf import PdfReader,PdfWriter
from pypdf.generic import ContentStream,NameObject,DictionaryObject,DecodedStreamObject
from content_patch import _operations
from insertions import writer_for,finish,compose

PATH=pdf.raw.FPDF_PAGEOBJ_PATH
IMAGE=pdf.raw.FPDF_PAGEOBJ_IMAGE
CONSTRUCT={b'm',b'l',b'c',b'v',b'y',b'h',b're'}
PAINT={b'S',b's',b'f',b'F',b'f*',b'B',b'B*',b'b',b'b*'}
TEXT_OPS={b'BT',b'ET',b'Tf',b'Tm',b'Td',b'TD',b'T*',b'Tc',b'Tw',b'Tz',b'TL',b'Ts',b'Tr',b'Tj',b'TJ',b"'",b'"'}


def selection_groups(model):
    """Group adjacent filled glyph outlines; keep borders/large shapes separate."""
    from object_transfer import union
    cached=getattr(model,'_graphic_groups',None)
    if cached is not None:return cached
    groups=[];rows=[];glyphs=[]
    for i,obj in enumerate(model.objects):
        if obj.type!=PATH:continue
        bounds=obj.get_bounds();l,b,r,t=bounds;w,h=r-l,t-b
        fill=C.c_int();stroke=C.c_int()
        filled=pdf.raw.FPDFPath_GetDrawMode(obj,C.byref(fill),C.byref(stroke)) and fill.value!=0
        if filled and .4<=h<=28 and .15<=w<=max(6,h*4):
            color=[C.c_uint() for _ in range(4)]
            style=tuple(v.value for v in color) if pdf.raw.FPDFPageObj_GetFillColor(obj,*[C.byref(v) for v in color]) else None
            glyphs.append((i,bounds,style))
        else:groups.append(((i,),bounds,PATH))
    for i,bounds,style in sorted(glyphs,key=lambda g:-(g[1][1]+g[1][3])/2):
        l,b,r,t=bounds;center=(b+t)/2;h=t-b
        candidates=[row for row in rows if row['style']==style and abs(row['center']-center)<=max(2,max(row['height'],h)*.65)]
        row=min(candidates,key=lambda row:abs(row['center']-center)) if candidates else None
        if row is None:
            row=dict(style=style,center=center,height=h,glyphs=[]);rows.append(row)
        row['glyphs'].append((i,bounds));row['height']=max(row['height'],h)
    for row in rows:
        runs=[]
        for i,bounds in sorted(row['glyphs'],key=lambda g:g[1][0]):
            if runs and bounds[0]-runs[-1]['right']<=max(2,min(5,row['height']*.6)):
                runs[-1]['indices'].append(i);runs[-1]['bounds'].append(bounds);runs[-1]['right']=max(runs[-1]['right'],bounds[2])
            else:runs.append(dict(indices=[i],bounds=[bounds],right=bounds[2]))
        groups.extend((tuple(sorted(run['indices'])),union(run['bounds']),PATH) for run in runs)
    model._graphic_groups=groups
    return groups


def hit_test(model,index,x,y,tolerance):
    """Large borders must not intercept clicks in their empty interiors."""
    from PySide6.QtCore import Qt,QPointF
    from PySide6.QtGui import QPainterPath,QPainterPathStroker
    from object_transfer import point
    cache=getattr(model,'_graphic_hit_shapes',None)
    if cache is None:cache={};model._graphic_hit_shapes=cache
    if index not in cache:
        obj=model.objects[index];matrix=obj.get_matrix().get();path=QPainterPath();curve=[]
        for n in range(pdf.raw.FPDFPath_CountSegments(obj)):
            segment=pdf.raw.FPDFPath_GetPathSegment(obj,n);sx,sy=C.c_float(),C.c_float()
            if not pdf.raw.FPDFPathSegment_GetPoint(segment,C.byref(sx),C.byref(sy)):return False
            p=QPointF(*point(matrix,sx.value,sy.value));kind=pdf.raw.FPDFPathSegment_GetType(segment)
            if kind==pdf.raw.FPDF_SEGMENT_MOVETO:path.moveTo(p)
            elif kind==pdf.raw.FPDF_SEGMENT_LINETO:path.lineTo(p)
            elif kind==pdf.raw.FPDF_SEGMENT_BEZIERTO:
                curve.append(p)
                if len(curve)==3:path.cubicTo(*curve);curve=[]
            if pdf.raw.FPDFPathSegment_GetClose(segment):path.closeSubpath()
        fill,stroke=C.c_int(),C.c_int();pdf.raw.FPDFPath_GetDrawMode(obj,C.byref(fill),C.byref(stroke))
        path.setFillRule(Qt.FillRule.WindingFill if fill.value==2 else Qt.FillRule.OddEvenFill)
        width=C.c_float();pdf.raw.FPDFPageObj_GetStrokeWidth(obj,C.byref(width))
        scale=max((matrix[0]**2+matrix[1]**2)**.5,(matrix[2]**2+matrix[3]**2)**.5)
        cache[index]=(path,bool(fill.value),bool(stroke.value),width.value*scale)
    path,fill,stroke,width=cache[index];p=QPointF(x,y)
    if fill and path.contains(p):return True
    if stroke:
        stroker=QPainterPathStroker();stroker.setWidth(max(width,tolerance*2))
        return stroker.createStroke(path).contains(p)
    return False


@lru_cache(maxsize=2)
def plan(data,index):
    reader=PdfReader(io.BytesIO(data));page=reader.pages[index]
    raw=ContentStream(page.get('/Contents'),reader).get_data();ops=_operations(raw)
    resources=page['/Resources'];xobjects=resources.get('/XObject',{})
    xobjects=xobjects.get_object() if hasattr(xobjects,'get_object') else xobjects
    paths=[];images=[];construct=[];clip=False;matrix=(1,0,0,1,0,0);stack=[]
    matrices={}
    for i,op in enumerate(ops):
        operator=op.operator
        if operator==b'q':stack.append(matrix)
        elif operator==b'Q':
            if not stack:raise ValueError('La pila gráfica original está desequilibrada.')
            matrix=stack.pop()
        elif operator==b'cm':matrix=compose(matrix,tuple(map(float,op.operands)))
        elif operator in CONSTRUCT:
            construct.append(i);matrices[i]=matrix
        elif operator in (b'W',b'W*'):clip=True
        elif operator in PAINT:
            if construct:paths.append(dict(paint=i,construct=tuple(construct),clip=clip))
            construct=[];clip=False
        elif operator==b'n':construct=[];clip=False
        elif operator==b'Do' and xobjects[op.operands[0]].get_object().get('/Subtype')=='/Image':
            images.append(dict(paint=i,matrix=matrix))
    document=pdf.PdfDocument(data);target=document[index]
    try:
        objects=list(target.get_objects(max_depth=0))
        path_indices=[i for i,o in enumerate(objects) if o.type==PATH]
        image_indices=[i for i,o in enumerate(objects) if o.type==IMAGE]
        if len(paths)!=len(path_indices) or len(images)!=len(image_indices):
            raise ValueError('No se pudo verificar la correspondencia de los gráficos de esta página.')
        path_map=dict(zip(path_indices,paths));image_map=dict(zip(image_indices,images))
        for i,record in image_map.items():
            if any(abs(a-b)>max(.0001,abs(b)*1e-5) for a,b in zip(record['matrix'],objects[i].get_matrix().get())):
                raise ValueError('No coincide la transformación original de una imagen.')
    finally:target.close();document.close()
    return raw,ops,path_map,image_map,matrices


def apply_edits(raw,edits):
    parts=[];position=0
    for (start,end),value in sorted(edits.items()):
        if start<position:raise ValueError('Las operaciones gráficas seleccionadas se superponen.')
        parts.extend((raw[position:start],value));position=end
    parts.append(raw[position:])
    return b''.join(parts)


def remove_path(edits,ops,record):
    if record['clip']:
        edits[ops[record['paint']].span]=b'n'
    else:
        edits[ops[record['paint']].span]=b''
        for i in record['construct']:edits[ops[i].span]=b''


def export_graphics(data,index,selected):
    raw,ops,paths,images,_=plan(data,index);selected=set(selected);edits={}
    for i,record in paths.items():
        if i not in selected:remove_path(edits,ops,record)
    for i,record in images.items():
        if i not in selected:edits[ops[record['paint']].span]=b''
    image_ops={r['paint'] for r in images.values()}
    for number,op in enumerate(ops):
        if op.operator in TEXT_OPS or op.operator==b'sh':edits[op.span]=b''
        if op.operator==b'Do' and number not in image_ops:edits[op.span]=b''
    reader=PdfReader(io.BytesIO(data));page=reader.pages[index]
    stream=DecodedStreamObject();stream.set_data(apply_edits(raw,edits));page[NameObject('/Contents')]=stream
    for key in ('/Annots','/FaroTextData'):page.pop(NameObject(key),None)
    # Remove unneeded font/image resources before cloning the selected fragment.
    resources=DictionaryObject(dict(page['/Resources']))
    xobjects=resources.get('/XObject',{});xobjects=xobjects.get_object() if hasattr(xobjects,'get_object') else xobjects
    names={str(ops[record['paint']].operands[0]) for i,record in images.items() if i in selected}
    resources[NameObject('/XObject')]=DictionaryObject({k:v for k,v in xobjects.items() if str(k) in names})
    resources[NameObject('/Font')]=DictionaryObject();page[NameObject('/Resources')]=resources
    writer=PdfWriter();writer.add_page(page)
    return finish(writer)


def transform_paths(data,index,indices,dx=0,dy=0,delete=False):
    from object_transfer import inverse
    from text_layout import num
    raw,ops,paths,_,matrices=plan(data,index);edits={}
    for object_index in indices:
        record=paths[object_index]
        if delete:remove_path(edits,ops,record);continue
        if record['clip']:raise ValueError('Este trazo define un recorte compartido y no se puede mover por separado.')
        for number in record['construct']:
            op=ops[number]
            if op.operator==b'h':continue
            inv=inverse(matrices[number]);tx=inv[0]*dx+inv[2]*dy;ty=inv[1]*dx+inv[3]*dy
            count=2 if op.operator==b're' else len(op.operands)
            for n in range(count):
                edits[op.spans[n]]=num(float(op.operands[n])+(tx if n%2==0 else ty)).encode('ascii')
    writer=writer_for(data);page=writer.pages[index]
    stream=DecodedStreamObject();stream.set_data(apply_edits(raw,edits));page[NameObject('/Contents')]=writer._add_object(stream)
    return finish(writer)
