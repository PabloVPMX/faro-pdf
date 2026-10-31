"""Extend a CFF encoding with original glyphs from the document's same face.

No installed lookalike is selected. Missing glyphs still require the original
font if they are absent from all original subsets of that face.
"""
import io
from functools import lru_cache

from fontTools.agl import toUnicode
from fontTools.cffLib import CFFFontSet
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from pypdf.generic import (NameObject,NumberObject,FloatObject,ArrayObject,
                          DictionaryObject,DecodedStreamObject)
from insertions import writer_for,finish
from typography import clean_name


def load(font):
    descendant=font.get('/DescendantFonts',[font])[0].get_object()
    descriptor=descendant.get('/FontDescriptor',{})
    descriptor=descriptor.get_object() if hasattr(descriptor,'get_object') else descriptor
    stream=descriptor.get('/FontFile3')
    if stream is None:return None
    cff=CFFFontSet();cff.decompile(io.BytesIO(stream.get_object().get_data()),None)
    top=cff.topDictIndex[0]
    if tuple(getattr(top,'FontMatrix',(.001,0,0,.001,0,0)))!=(.001,0,0,.001,0,0):return None
    return cff,top,descendant,descriptor


def glyphs(font,top):
    if font.get('/Subtype')=='/Type1':
        return {toUnicode(name):name for name in top.charset if len(toUnicode(name))==1}
    from content_patch import _Font
    return {char:'cid'+str(int.from_bytes(code,'big')).zfill(5)
            for code,char in _Font(font).mapping.items()
            if 'cid'+str(int.from_bytes(code,'big')).zfill(5) in top.charset}


def drawing(top,name):
    pen=RecordingPen();char=top.CharStrings[name];char.draw(pen)
    return pen.value,char.width


@lru_cache(maxsize=8)
def extend_cff(data,page_index,ordinal,missing):
    from content_patch import _prepare,_operations,UnsupportedNativePatch
    reader,raw,_,shows,_,_=_prepare(data,page_index);show=shows[ordinal]
    resource=None;stack=[]
    for op in _operations(raw)[:show.operation]:
        if op.operator==b'q':stack.append(resource)
        elif op.operator==b'Q':resource=stack.pop()
        elif op.operator==b'Tf':resource=op.operands[0]
    target_font=reader.pages[page_index]['/Resources']['/Font'][resource].get_object()
    loaded=load(target_font)
    if loaded is None:raise UnsupportedNativePatch('Esta fuente CFF no tiene una matriz compatible.')
    cff,top,descendant,descriptor=loaded
    base=clean_name(str(target_font['/BaseFont']).lstrip('/'))
    face_name=clean_name(str(cff.fontNames[0]));available={}
    target_glyphs=glyphs(target_font,top)
    for char,name in target_glyphs.items():available[char]=(top,name)
    visited=set()
    def scan(resources):
        resources=resources.get_object();fonts=resources.get('/Font',{})
        fonts=fonts.get_object() if hasattr(fonts,'get_object') else fonts
        for ref in fonts.values():
            font=ref.get_object()
            identity=id(font)
            if identity in visited:continue
            visited.add(identity)
            if clean_name(str(font.get('/BaseFont','')).lstrip('/'))!=base:continue
            other=load(font)
            if other is None:continue
            other_cff,other_top,_,_=other
            if clean_name(str(other_cff.fontNames[0]))!=face_name:continue
            mapping=glyphs(font,other_top)
            # Reject contradictory definitions from a similarly named subset.
            overlap=set(mapping)&set(target_glyphs)
            if any(drawing(top,target_glyphs[c])!=drawing(other_top,mapping[c]) for c in overlap):continue
            for char,name in mapping.items():available.setdefault(char,(other_top,name))
        objects=resources.get('/XObject',{})
        objects=objects.get_object() if hasattr(objects,'get_object') else objects
        for ref in objects.values():
            obj=ref.get_object()
            if obj.get('/Subtype')=='/Form' and '/Resources' in obj:
                identity=id(obj)
                if identity not in visited:visited.add(identity);scan(obj['/Resources'])
    for page in reader.pages:scan(page['/Resources'])
    absent=[c for c in missing if c not in available]
    if absent:
        raise UnsupportedNativePatch('La fuente original no incluye estos caracteres en sus subconjuntos: '+
                                     ', '.join(absent)+'. Importa la fuente original completa o elige otra explícitamente.')
    cid=target_font.get('/Subtype')=='/Type0'
    if not cid and target_font.get('/Subtype')!='/Type1':raise UnsupportedNativePatch('Tipo de fuente CFF no compatible.')
    codes={int.from_bytes(k,'big') for k in show.font.mapping};new_codes={};new_names={}
    if cid:
        next_code=max([int(n[3:]) for n in top.charset if n.startswith('cid')]+[0])+1
        free=iter(range(next_code,65536))
    else:free=iter(i for i in range(1,256) if i not in codes)
    old_drawings={name:drawing(top,name) for name in top.charset}
    for char in missing:
        code=next(free,None)
        if code is None:raise UnsupportedNativePatch('La fuente agotó sus códigos disponibles.')
        donor,name=available[char];new_codes[char]=code
        if char in target_glyphs and not cid:
            new_names[char]=target_glyphs[char];continue
        new_name='cid'+str(code).zfill(5) if cid else 'uni'+char.encode('utf-16-be').hex().upper()
        records,width=drawing(donor,name)
        if cid:
            fd=0;private=top.FDArray[fd].Private
        else:private=top.Private
        pen=T2CharStringPen(width-getattr(private,'nominalWidthX',0),None)
        # Draw the exact original contours; resolve subroutines in the donor.
        donor.CharStrings[name].draw(pen)
        charstring=pen.getCharString(private=private,globalSubrs=cff.GlobalSubrs)
        charstrings=top.CharStrings
        if charstrings.charStringsAreIndexed:
            index=charstrings.charStringsIndex;index.append(charstring)
            charstrings.charStrings[new_name]=len(index)-1
        else:charstrings.charStrings[new_name]=charstring
        top.charset.append(new_name)
        if cid and hasattr(top,'FDSelect'):top.FDSelect.gidArray.append(fd)
        new_names[char]=new_name
        if drawing(top,new_name)!=(records,width):raise UnsupportedNativePatch('No se conservó el contorno original del carácter añadido.')
    if cid:top.CIDCount=max(int(getattr(top,'CIDCount',0)),max(new_codes.values())+1)
    from fontTools.ttLib import TTFont
    container=TTFont();container.recalcBBoxes=False
    program=io.BytesIO();cff.compile(program,container)
    container.close()
    check=CFFFontSet();check.decompile(io.BytesIO(program.getvalue()),None);checked=check.topDictIndex[0]
    if any(drawing(checked,name)!=value for name,value in old_drawings.items()):
        raise UnsupportedNativePatch('La ampliación modificó un glifo original; el PDF se conserva.')
    writer=writer_for(data);font=writer.pages[page_index]['/Resources']['/Font'][resource].get_object()
    desc=font.get('/DescendantFonts',[font])[0].get_object();definition=desc['/FontDescriptor'].get_object()
    stream=DecodedStreamObject();stream.set_data(program.getvalue())
    stream[NameObject('/Subtype')]=NameObject('/CIDFontType0C' if cid else '/Type1C')
    definition[NameObject('/FontFile3')]=writer._add_object(stream)
    if cid:
        widths=ArrayObject(list(desc.get('/W',[])))
        for char,code in new_codes.items():
            donor,name=available[char];width=drawing(donor,name)[1]
            widths.extend([NumberObject(code),ArrayObject([FloatObject(width)])])
        desc[NameObject('/W')]=widths
    else:
        old_encoding=font.get('/Encoding')
        if isinstance(old_encoding,DictionaryObject):encoding=DictionaryObject(dict(old_encoding))
        else:encoding=DictionaryObject({NameObject('/BaseEncoding'):NameObject(str(old_encoding or '/StandardEncoding'))})
        differences=ArrayObject(list(encoding.get('/Differences',[])))
        for char,code in new_codes.items():differences.extend([NumberObject(code),NameObject('/'+new_names[char])])
        encoding[NameObject('/Differences')]=differences;font[NameObject('/Encoding')]=encoding
        first=int(font.get('/FirstChar',0));old_widths=list(font.get('/Widths',[]))
        values={first+i:float(v) for i,v in enumerate(old_widths)}
        values.update({code:drawing(*available[char])[1] for char,code in new_codes.items()})
        first=min(first,min(new_codes.values()));last=max(int(font.get('/LastChar',255)),max(new_codes.values()))
        font[NameObject('/FirstChar')]=NumberObject(first);font[NameObject('/LastChar')]=NumberObject(last)
        font[NameObject('/Widths')]=ArrayObject([FloatObject(values.get(code,0)) for code in range(first,last+1)])
    mapping={int.from_bytes(code,'big'):char for code,char in show.font.mapping.items()}
    mapping.update({code:char for char,code in new_codes.items()});width=4 if cid else 2
    lines=[]
    for start in range(0,len(mapping),100):
        entries=list(sorted(mapping.items()))[start:start+100]
        lines.append(str(len(entries))+' beginbfchar\n'+'\n'.join(f'<{code:0{width}X}> <{char.encode("utf-16-be").hex()}>' for code,char in entries)+'\nendbfchar')
    payload=('/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n/CMapType 2 def\n'
             '/CMapName /FaroCFF def\n/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n'
             '1 begincodespacerange\n<'+('0000' if cid else '00')+'> <'+('FFFF' if cid else 'FF')+'>\nendcodespacerange\n'+
             '\n'.join(lines)+'\nendcmap CMapName currentdict /CMap defineresource pop end end').encode('ascii')
    stream=DecodedStreamObject();stream.set_data(payload);font[NameObject('/ToUnicode')]=writer._add_object(stream)
    result=finish(writer);_prepare(result,page_index,allow_cache=False)
    # The encoding/program can be shared by several pages. Adding unused codes
    # must leave every existing page pixel-identical before the actual edit.
    import pypdfium2 as pdf
    import math
    before=pdf.PdfDocument(data);after=pdf.PdfDocument(result)
    try:
        for index in range(len(before)):
            old,new=before[index],after[index];w,h=old.get_size();scale=min(2,math.sqrt(2_000_000/max(1,w*h)))
            a,b=old.render(scale=scale),new.render(scale=scale)
            try:
                if a.to_pil().tobytes()!=b.to_pil().tobytes():raise UnsupportedNativePatch('La ampliación CFF alteraba el documento original.')
            finally:a.close();b.close();old.close();new.close()
    finally:before.close();after.close()
    return result
