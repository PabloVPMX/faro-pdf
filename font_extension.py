"""Extend sparse CID TrueType fonts with verified glyphs from the same font.

Existing glyph IDs, outlines, metrics, hint programs and PDF codes stay intact.
No family approximation or replacement of the text object is performed.
"""
import copy,io,re
from functools import lru_cache
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib.tables._g_l_y_f import Glyph
from pypdf import PdfWriter
from pypdf.generic import NameObject,NumberObject,ArrayObject,DecodedStreamObject
from typography import Catalog,clean_name


def _drawing(font,name):
    glyphs=font.getGlyphSet();pen=DecomposingRecordingPen(glyphs)
    glyphs[name].draw(pen)
    return pen.value


def extend_for_text(data,page_index,ordinal,value):
    from content_patch import _prepare
    show=_prepare(data,page_index)[3][ordinal]
    missing=tuple(sorted(set(value)-set(show.font.reverse)))
    return _extend_missing(data,page_index,ordinal,missing) if missing else data


@lru_cache(maxsize=8)
def _extend_missing(data,page_index,ordinal,missing):
    from content_patch import _prepare,_operations,UnsupportedNativePatch
    reader,raw,_,shows,_,_=_prepare(data,page_index)
    show=shows[ordinal]
    name=None;names=[]
    for op in _operations(raw)[:show.operation]:
        if op.operator==b'q':names.append(name)
        elif op.operator==b'Q':name=names.pop()
        elif op.operator==b'Tf':name=op.operands[0]
    font=reader.pages[page_index]['/Resources']['/Font'][name].get_object()
    if font.get('/Subtype')!='/Type0' or font.get('/Encoding')!='/Identity-H':
        raise UnsupportedNativePatch('Ampliar esta fuente requiere un mapa CID TrueType Identity-H.')
    descendant=font['/DescendantFonts'][0].get_object()
    descriptor=descendant['/FontDescriptor'].get_object()
    source=TTFont(io.BytesIO(descriptor['/FontFile2'].get_data()))
    base=clean_name(str(font['/BaseFont']).lstrip('/'))
    bold='bold' in base.lower() or source['OS/2'].usWeightClass>=600
    italic=bool(source['OS/2'].fsSelection & 1)
    candidates=[f for f in Catalog().matching(base,bold,italic)
                if f.bold==bold and f.italic==italic and not f.restricted]
    full=None
    for candidate in candidates:
        trial=TTFont(candidate.path)
        try:
            if trial['head'].unitsPerEm!=source['head'].unitsPerEm:continue
            if any(source[t].compile(source)!=trial[t].compile(trial) for t in ('cvt ','fpgm','prep')):continue
            order=source.getGlyphOrder();other=trial.getGlyphOrder()
            if len(order)>len(other):continue
            # Check every retained visible glyph, not just a family-name match.
            if any((_drawing(source,n)!=_drawing(trial,other[i])
                    or source['hmtx'][n]!=trial['hmtx'][other[i]])
                   for i,n in enumerate(order) if source['glyf'][n].numberOfContours):continue
            if any(ord(c) not in trial.getBestCmap() for c in missing):continue
            full=trial;break
        finally:
            if full is not trial:trial.close()
    if full is None:
        raise UnsupportedNativePatch('No se encontró una fuente completa con los mismos glifos, métricas e instrucciones que la original. Importa la versión original completa.')
    try:
        original_order=source.getGlyphOrder();full_order=full.getGlyphOrder()
        order=list(original_order);cmap=full.getBestCmap()
        added={};visiting=set()
        def copy_gid(gid):
            if gid in visiting:return
            visiting.add(gid)
            while len(order)<=gid:
                new='faro_gid_'+str(len(order));order.append(new)
                source['glyf'][new]=Glyph();source['hmtx'][new]=(0,0)
            name=order[gid]
            if source['glyf'][name].numberOfContours:return
            incoming=copy.deepcopy(full['glyf'][full_order[gid]])
            if incoming.isComposite():
                for component in incoming.components:
                    child=full.getGlyphID(component.glyphName);copy_gid(child)
                    component.glyphName=order[child]
            source['glyf'][name]=incoming
            source['hmtx'][name]=full['hmtx'][full_order[gid]]
        for char in missing:
            gid=full.getGlyphID(cmap[ord(char)]);copy_gid(gid);added[char]=gid
        source.setGlyphOrder(order)
        source['maxp'].numGlyphs=len(order)
        program=io.BytesIO();source.save(program)
        writer=PdfWriter(reader,incremental=True)
        while len(writer._objects)<int(reader.trailer['/Size'])-1:writer._objects.append(None)
        font=writer.pages[page_index]['/Resources']['/Font'][name].get_object()
        descendant=font['/DescendantFonts'][0].get_object()
        descriptor=descendant['/FontDescriptor'].get_object()
        def stream(payload):
            obj=DecodedStreamObject();obj.set_data(payload);return writer._add_object(obj)
        replacement=DecodedStreamObject();replacement.set_data(program.getvalue())
        replacement[NameObject('/Length1')]=NumberObject(len(program.getvalue()))
        descriptor[NameObject('/FontFile2')]=writer._add_object(replacement)
        original_map=descendant.get('/CIDToGIDMap','/Identity')
        if original_map=='/Identity':
            gids={int.from_bytes(c,'big'):int.from_bytes(c,'big') for c in show.font.mapping}
        else:
            old=original_map.get_object().get_data()
            gids={i:int.from_bytes(old[2*i:2*i+2],'big') for i in range(len(old)//2)}
        cid=max(max(gids,default=0),max(int.from_bytes(c,'big') for c in show.font.mapping))+1
        extra=[];widths=ArrayObject(list(descendant.get('/W',[])))
        for char,gid in added.items():
            if cid>65535:raise UnsupportedNativePatch('La fuente agotó su espacio CID.')
            gids[cid]=gid
            extra.append(f'<{cid:04X}> <{char.encode("utf-16-be").hex()}>')
            from pypdf.generic import FloatObject
            widths.extend([NumberObject(cid),ArrayObject([FloatObject(full['hmtx'][full_order[gid]][0]*1000/full['head'].unitsPerEm)])])
            cid+=1
        mapping=bytearray((max(gids)+1)*2)
        for code,gid in gids.items():mapping[code*2:code*2+2]=gid.to_bytes(2,'big')
        descendant[NameObject('/CIDToGIDMap')]=stream(bytes(mapping))
        descendant[NameObject('/W')]=widths
        unicode=font['/ToUnicode'].get_data()
        block=('\n'+str(len(extra))+' beginbfchar\n'+'\n'.join(extra)+'\nendbfchar\n').encode('ascii')
        if unicode.count(b'endcmap')!=1:raise UnsupportedNativePatch('El mapa Unicode no tiene un cierre único.')
        font[NameObject('/ToUnicode')]=stream(unicode.replace(b'endcmap',block+b'endcmap'))
        output=io.BytesIO();writer.write(output);result=output.getvalue()
        if not result.startswith(data):raise UnsupportedNativePatch('No se conservó la revisión original de la fuente.')
        _prepare(result,page_index,allow_cache=False)
        return result
    finally:
        source.close();full.close()
