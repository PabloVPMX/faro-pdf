"""Isolated, editable multiline text blocks, rendered from real PDF content."""
import io,re,uuid,hashlib,math
from functools import lru_cache
from pathlib import Path
from fontTools.ttLib import TTFont
from pypdf import PdfReader
from pypdf.generic import NameObject,DictionaryObject,DecodedStreamObject,ArrayObject,FloatObject,NumberObject,TextStringObject
from insertions import writer_for,finish,resource,append_content
from content_patch import _prepare,_operations,_Font,patch_native,patch_native_run

def num(v):return format(float(v),'.10f').rstrip('0').rstrip('.') or '0'

@lru_cache(maxsize=8)
def block_records(data,page):
    from owned_text import records
    return records(data,page)

def add_font(w,page,path):
    from typography import read_face
    face=read_face(path)
    if face.restricted:raise ValueError('Esta fuente no permite incrustación.')
    data=Path(path).read_bytes();base='/FaroFont'+hashlib.sha256(data).hexdigest()[:12];key=NameObject(base);fonts=resource(page,'/Font')
    with TTFont(io.BytesIO(data),lazy=True) as expected:
        wanted={chr(u) for u,n in expected.getBestCmap().items() if u<=65535 and chr(u).isprintable() and expected.getGlyphID(n)>0}
    suffix=0
    while key in fonts:
        try:
            current=fonts[key].get_object();validated=_Font(current)
            descendant=current['/DescendantFonts'][0].get_object()
            if (wanted.issubset(validated.reverse) and
                    descendant['/FontDescriptor']['/FontFile2'].get_data()==data):return key
        except (ValueError,KeyError,TypeError):pass
        # A resource with the same name can be an original font with a missing
        # or incomplete Unicode map. Never overwrite or adopt that resource.
        suffix+=1;key=NameObject(base+'_'+str(suffix))
    with TTFont(io.BytesIO(data)) as font:
        cmap={u:font.getGlyphID(n) for u,n in font.getBestCmap().items() if u<=65535 and chr(u).isprintable() and font.getGlyphID(n)>0}
        units=font['head'].unitsPerEm;order=font.getGlyphOrder()
        def stream(payload):
            obj=DecodedStreamObject();obj.set_data(payload);return w._add_object(obj)
        fontfile=DecodedStreamObject();fontfile.set_data(data);fontfile[NameObject('/Length1')]=NumberObject(len(data))
        name=NameObject('/'+re.sub('[^a-zA-Z0-9_-]','',font['name'].getDebugName(6) or face.name))
        descriptor=DictionaryObject({NameObject('/Type'):NameObject('/FontDescriptor'),NameObject('/FontName'):name,
            NameObject('/Flags'):NumberObject(32+(64 if face.italic else 0)),NameObject('/FontBBox'):ArrayObject([FloatObject(v*1000/units) for v in (font['head'].xMin,font['head'].yMin,font['head'].xMax,font['head'].yMax)]),
            NameObject('/ItalicAngle'):FloatObject(font['post'].italicAngle),NameObject('/Ascent'):FloatObject(font['hhea'].ascent*1000/units),NameObject('/Descent'):FloatObject(font['hhea'].descent*1000/units),NameObject('/CapHeight'):FloatObject(font['hhea'].ascent*1000/units),NameObject('/StemV'):NumberObject(80),NameObject('/FontFile2'):w._add_object(fontfile)})
        mapping=bytearray((max(cmap)+1)*2);widths=ArrayObject();lines=[]
        for code,gid in sorted(cmap.items()):
            mapping[code*2:code*2+2]=gid.to_bytes(2,'big');widths.extend([NumberObject(code),ArrayObject([FloatObject(font['hmtx'][order[gid]][0]*1000/units)])]);lines.append(f'<{code:04X}> <{code:04X}>')
        unicode=b'/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n/CMapName /FaroUnicode def\n/CMapType 2 def\n1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n'
        for start in range(0,len(lines),100):
            chunk=lines[start:start+100];unicode+=(str(len(chunk))+' beginbfchar\n'+'\n'.join(chunk)+'\nendbfchar\n').encode('ascii')
        unicode+=b'endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n'
        descendant=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/CIDFontType2'),NameObject('/BaseFont'):name,NameObject('/CIDSystemInfo'):DictionaryObject({NameObject('/Registry'):TextStringObject('Adobe'),NameObject('/Ordering'):TextStringObject('Identity'),NameObject('/Supplement'):NumberObject(0)}),NameObject('/FontDescriptor'):w._add_object(descriptor),NameObject('/CIDToGIDMap'):stream(bytes(mapping)),NameObject('/W'):widths})
        fonts[key]=w._add_object(DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type0'),NameObject('/BaseFont'):name,NameObject('/Encoding'):NameObject('/Identity-H'),NameObject('/DescendantFonts'):ArrayObject([w._add_object(descendant)]),NameObject('/ToUnicode'):stream(unicode)}))
    return key

def wrapped_lines(value,font,size,width,base_font):
    """Keep logical text intact; soft wraps only change PDF line placement."""
    if font.standard:
        from pypdf._codecs.core_font_metrics import CORE_FONT_METRICS
        widths=CORE_FONT_METRICS[str(base_font).lstrip('/')].character_widths
        advance=lambda char: widths.get(char,widths['default'])*size/1000
    else:
        advance=lambda char: font.advance(font.edit(b'',char))*size/1000
    lines=[];offset=0
    for paragraph in value.split('\n'):
        start=0
        while start<len(paragraph):
            end=start;used=0;space=None
            while end<len(paragraph):
                step=advance(paragraph[end])
                if end>start and used+step>width:break
                used+=step;end+=1
                if paragraph[end-1].isspace():space=end
            if end<len(paragraph) and space is not None and space>start:end=space
            lines.append((offset+start,paragraph[start:end]));start=end
        if not paragraph:lines.append((offset,''))
        offset+=len(paragraph)+1
    return lines


def replace_block(data,page_index,ordinals,expected,value,size,matrix,color,face=None,block_id=None,box=None):
    value=value.replace('\r\n','\n').replace('\r','\n')
    if any(not c.isprintable() and c!='\n' for c in value):raise ValueError('El bloque contiene caracteres de control no admitidos.')
    own=block_records(data,page_index);existing=next((key for key,r in own.items() if r['ordinals']==ordinals),None)
    if existing and own[existing].get('owned'):
        from owned_text import replace
        return replace(data,page_index,existing,value,size,face,color,box)
    if existing:
        if not face and ordinals:
            from font_extension import extend_for_text
            data=extend_for_text(data,page_index,ordinals[0],value.replace('\n',''))
            own=block_records(data,page_index)
        record=own[existing];matrix=tuple(map(float,record['meta']['/Matrix']))
        if box is None and '/Box' in record['meta']:box=tuple(map(float,record['meta']['/Box']))
        font_name=record['meta']['/Font'];block_id=existing
        w=writer_for(data);page=w.pages[page_index]
        from pypdf.generic import ContentStream
        raw=ContentStream(page.get('/Contents'),w).get_data()
        raw,count=re.subn(re.escape(existing.encode('ascii'))+rb'\s+BMC\b.*?\bEMC\b',b'',raw,flags=re.S)
        if count!=1:raise ValueError('No se encontró el bloque de texto editable.')
        stream=DecodedStreamObject();stream.set_data(raw);page[NameObject('/Contents')]=w._add_object(stream)
    else:
        if not face:
            from font_extension import extend_for_text
            data=extend_for_text(data,page_index,ordinals[0],value.replace('\n',''))
        reader,raw,_,shows,_,_=_prepare(data,page_index);font_name=None;stack=[]
        for op in _operations(raw)[:shows[ordinals[0]].operation]:
            if op.operator==b'q':stack.append(font_name)
            elif op.operator==b'Q':font_name=stack.pop()
            elif op.operator==b'Tf':font_name=op.operands[0]
        removed=patch_native_run(data,page_index,ordinals,expected,'') if len(ordinals)>1 else patch_native(data,page_index,ordinals[0],expected,'')
        w=writer_for(removed);page=w.pages[page_index]
        block_id=block_id or '/FaroBlock'+uuid.uuid4().hex
    if face:font_name=add_font(w,page,face)
    font=_Font(page['/Resources']['/Font'][font_name].get_object())
    a,b,c,d,e,f=matrix
    lines=[];offset=0
    if box:
        width=(box[2]-box[0])/max(math.hypot(a,b),1e-8)
        lines=wrapped_lines(value,font,size,max(1,width),page['/Resources']['/Font'][font_name]['/BaseFont'])
    else:
        for line in value.split('\n'):
            lines.append((offset,line));offset+=len(line)+1
    commands=[block_id+' BMC','q',' '.join(num(v/255) for v in color)+' rg','BT',f'{font_name} {num(size)} Tf','0 Tc 0 Tw 100 Tz 0 Ts 0 Tr']
    for row,(_,line) in enumerate(lines):
        encoded=font.edit(b'',line)
        line_matrix=(a,b,c,d,e-c*size*1.3*row,f-d*size*1.3*row)
        commands.append(' '.join(num(v) for v in line_matrix)+' Tm <'+encoded.hex()+'> Tj')
    commands+=['ET','Q','EMC']
    append_content(w,page,('\n'.join(commands)+'\n').encode('ascii'))
    metadata=DictionaryObject(dict(page.get('/FaroTextData',{})))
    metadata[NameObject(block_id)]=DictionaryObject({NameObject('/Text'):TextStringObject(value),NameObject('/Matrix'):ArrayObject([FloatObject(v) for v in matrix]),NameObject('/Size'):FloatObject(size),NameObject('/Font'):NameObject(font_name),NameObject('/Color'):ArrayObject([NumberObject(v) for v in color])})
    if box:
        metadata[NameObject(block_id)][NameObject('/Box')]=ArrayObject([FloatObject(v) for v in box])
        metadata[NameObject(block_id)][NameObject('/Lines')]=ArrayObject([TextStringObject(line) for _,line in lines])
        metadata[NameObject(block_id)][NameObject('/Starts')]=ArrayObject([NumberObject(start) for start,_ in lines])
    page[NameObject('/FaroTextData')]=metadata
    result=finish(w);_prepare(result,page_index)
    return result,block_id

def block_geometry(model,textpage,objects,record):
    import ctypes as C
    from engine import align_character_geometry
    selected=[objects[i] for i in record['ordinals']];targets={C.cast(o.raw,C.c_void_p).value for o in selected}
    geometry=model.page_character_geometry(textpage,targets);meta=record['meta'];size=float(meta['/Size']);a,b,c,d,e,f=map(float,meta['/Matrix'])
    value=str(meta['/Text']);rows=[None]*len(value);object_index=0;end=(e,f)
    lines=list(map(str,meta.get('/Lines',value.split('\n'))))
    starts=list(map(int,meta.get('/Starts',[])))
    if not starts:
        offset=0
        for line in lines:starts.append(offset);offset+=len(line)+1
    for line_index,line in enumerate(lines):
        origin=(e-c*size*1.3*line_index,f-d*size*1.3*line_index)
        glyphs=[]
        if line:
            obj=selected[object_index];object_index+=1;glyphs=geometry.get(C.cast(obj.raw,C.c_void_p).value,[])
        aligned=align_character_geometry(glyphs,line,origin)
        if aligned is None:raise ValueError('No coincide la geometría de la línea de texto.')
        start=starts[line_index]
        rows[start:start+len(line)]=aligned
        end=(aligned[-1]['bounds'][1],aligned[-1]['origin'][1]) if aligned else origin
        after=start+len(line)
        if after<len(value) and value[after]=='\n':rows[after]=dict(character='\n',origin=end,bounds=(end[0],end[0],end[1],end[1]))
    if any(row is None for row in rows):raise ValueError('No se pudo situar cada carácter del cuadro de texto.')
    return rows,end

def move_text(data,page,ordinals,dx,dy):
    from insertions import compose
    for key,record in block_records(data,page).items():
        if record['ordinals']==ordinals and record.get('owned'):
            from owned_text import move
            return move(data,page,key,dx,dy)
    if ordinals!=list(range(ordinals[0],ordinals[-1]+1)):raise ValueError('Los fragmentos del cuadro no son contiguos.')
    _,raw,_,shows,_,_=_prepare(data,page);ops=_operations(raw)
    first,last=shows[ordinals[0]].operation,shows[ordinals[-1]].operation
    matrix=(1,0,0,1,0,0);stack=[]
    for op in ops[:first]:
        if op.operator==b'q':stack.append(matrix)
        elif op.operator==b'Q':matrix=stack.pop()
        elif op.operator==b'cm':matrix=compose(matrix,tuple(map(float,op.operands)))
    a,b,c,d,e,f=matrix;det=a*d-b*c
    if abs(det)<1e-12:raise ValueError('El cuadro tiene una transformación no válida.')
    inverse=(d/det,-b/det,-c/det,a/det,(c*f-d*e)/det,(b*e-a*f)/det)
    local=compose(compose(inverse,(1,0,0,1,dx,dy)),matrix)
    start=ops[first].spans[0][0];tail=ops[last].spans[-1][1]
    match=re.match(rb'\s*T[Jj]\b',raw[tail:])
    if not match:raise ValueError('No se pudo localizar el final del cuadro.')
    end=tail+match.end()
    updated=raw[:start]+b'q '+(' '.join(num(v) for v in local)).encode('ascii')+b' cm '+raw[start:end]+b' Q '+raw[end:]
    w=writer_for(data);target=w.pages[page];stream=DecodedStreamObject();stream.set_data(updated);target[NameObject('/Contents')]=w._add_object(stream)
    for key,record in block_records(data,page).items():
        if record['ordinals']==ordinals:
            metadata=target['/FaroTextData'][key]
            values=list(map(float,metadata['/Matrix']));values[4]+=dx;values[5]+=dy
            metadata[NameObject('/Matrix')]=ArrayObject([FloatObject(v) for v in values])
            if '/Box' in metadata:
                l,b,r,t=map(float,metadata['/Box'])
                metadata[NameObject('/Box')]=ArrayObject([FloatObject(v) for v in (l+dx,b+dy,r+dx,t+dy)])
    result=finish(w);_prepare(result,page);return result
