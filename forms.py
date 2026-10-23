"""Resolve ordinary Form XObjects to editable page operators without rasterizing.

The original PDF revision stays intact. Every affected page must render exactly
the same before this representation is used. Transparency groups are excluded.
"""
import io
from functools import lru_cache
import numpy as np
import pypdfium2 as pdf
from pypdf.generic import NameObject,DictionaryObject,DecodedStreamObject,ContentStream
from insertions import writer_for,finish
from content_patch import _operations

@lru_cache(maxsize=2)
def editable_forms(data):
    w=writer_for(data);affected=[]
    for page_index,page in enumerate(w.pages):
        resources=page['/Resources'];counter=[0];changed=[False]
        merged=DictionaryObject(dict(resources))
        for kind in ('/Font','/XObject','/ExtGState','/ColorSpace','/Pattern','/Shading','/Properties'):
            table=resources.get(kind,{})
            table=table.get_object() if hasattr(table,'get_object') else table
            merged[NameObject(kind)]=DictionaryObject(dict(table))
        def expand(raw,res,depth=0):
            if depth>16:raise ValueError('El documento contiene grupos Form recursivos.')
            edits=[]
            for op in _operations(raw):
                if op.operator!=b'Do':continue
                xobjects=res.get('/XObject',{});xobjects=xobjects.get_object() if hasattr(xobjects,'get_object') else xobjects
                obj=xobjects[op.operands[0]].get_object()
                if obj.get('/Subtype')!='/Form':continue
                if obj.get('/Group'):raise ValueError('El grupo Form usa transparencia agrupada que requiere otra ruta de edición.')
                changed[0]=True;counter[0]+=1;tag=f'/FaroForm{counter[0]}_'
                child=obj.get('/Resources',res);child=child.get_object()
                mappings={};childres=DictionaryObject(dict(child))
                for kind in merged:
                    if kind not in ('/Font','/XObject','/ExtGState','/ColorSpace','/Pattern','/Shading','/Properties'):continue
                    values=child.get(kind,{})
                    values=values.get_object() if hasattr(values,'get_object') else values
                    table=DictionaryObject()
                    for name,ref in values.items():
                        new=NameObject(tag+name[1:]);mappings[(kind,str(name))]=new
                        table[new]=ref;merged[kind][new]=ref
                    childres[kind]=table
                payload=obj.get_data();renames=[]
                kinds={b'Tf':'/Font',b'Do':'/XObject',b'gs':'/ExtGState',b'CS':'/ColorSpace',b'cs':'/ColorSpace',b'sh':'/Shading',b'SCN':'/Pattern',b'scn':'/Pattern',b'BDC':'/Properties'}
                for item in _operations(payload):
                    kind=kinds.get(item.operator)
                    if kind:
                        for arg,span in zip(item.operands,item.spans):
                            if isinstance(arg,NameObject) and (kind,str(arg)) in mappings:
                                renames.append((*span,str(mappings[(kind,str(arg))]).encode('ascii')))
                for start,end,new in sorted(renames,reverse=True):payload=payload[:start]+new+payload[end:]
                payload=expand(payload,childres,depth+1)
                matrix=obj.get('/Matrix',[1,0,0,1,0,0]);l,b,r,t=map(float,obj['/BBox'])
                number=lambda v:format(float(v),'.10f').rstrip('0').rstrip('.') or '0'
                prefix=('q '+' '.join(number(v) for v in matrix)+' cm\n'+' '.join(number(v) for v in (l,b,r-l,t-b))+' re W n\n').encode('ascii')
                start,end=op.spans[0]
                import re
                match=re.match(rb'\s*Do\b',raw[end:])
                if not match:raise ValueError('No se pudo resolver una aparición Form.')
                edits.append((start,end+match.end(),prefix+payload+b'\nQ\n'))
            for start,end,new in sorted(edits,reverse=True):raw=raw[:start]+new+raw[end:]
            return raw
        raw=ContentStream(page.get('/Contents'),w).get_data()
        resolved=expand(raw,resources)
        if changed[0]:
            stream=DecodedStreamObject();stream.set_data(resolved)
            page[NameObject('/Contents')]=w._add_object(stream);page[NameObject('/Resources')]=merged
            affected.append(page_index)
    if not affected:return data
    result=finish(w)
    before=pdf.PdfDocument(data);after=pdf.PdfDocument(result)
    try:
        for index in affected:
            pages=[before[index],after[index]];bitmaps=[p.render(scale=2) for p in pages]
            try:
                arrays=[np.asarray(b.to_pil().convert('RGB')) for b in bitmaps]
                if not np.array_equal(*arrays):raise ValueError('La preparación del grupo Form cambió su apariencia. Se conserva el original.')
            finally:
                for bitmap in bitmaps:bitmap.close()
                for page in pages:page.close()
    finally:before.close();after.close()
    return result
