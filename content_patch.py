"""Conservative native-text edits using existing CID bytes and incremental PDF updates.

No PDFium mutation/content generation, OCR, new fonts, reflow or font substitution.
Supported fonts are explicit Type0/Identity-H or simple embedded TrueType with
one-to-one ToUnicode maps, and Latin Standard-14 fonts with named encodings.
An exact root-page text-show/object mapping is required for every text object.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from collections import OrderedDict
from functools import lru_cache
import ctypes as C
import hashlib
import io
import re
from types import MappingProxyType

from fontTools.ttLib import TTFont
from pypdf import PdfReader, PdfWriter
from pypdf._utils import read_non_whitespace, read_until_regex
from pypdf.generic import (
    ArrayObject, ByteStringObject, ContentStream, DecodedStreamObject,
    IndirectObject, NameObject, StreamObject, TextStringObject, read_object,
)
import pypdfium2 as pdfium


class UnsupportedNativePatch(ValueError):
    """The edit cannot be proven to retain the original content/font mapping."""


def _fail(message):
    raise UnsupportedNativePatch(message)


def _source_matches(glyphs,source):
    # PDFium can suppress actual leading/repeated spaces from its text page.
    # Only omitted ASCII spaces are allowed; every visible source character
    # and every text-object ordinal must still match exactly.
    return all(tag=='equal' or (tag=='insert' and set(source[c:d])<={' '})
               for tag,a,b,c,d in SequenceMatcher(a=glyphs,b=source,autojunk=False).get_opcodes())


def _raw_string(value):
    if isinstance(value, ByteStringObject):
        return bytes(value)
    if isinstance(value, TextStringObject):
        return value.original_bytes
    _fail('El operando de texto no es una cadena PDF compatible.')


def _hex(token):
    value = re.sub(rb'\s', b'', token[1:-1])
    if len(value) % 2:
        _fail('El mapa ToUnicode contiene códigos hexadecimales incompletos.')
    return bytes.fromhex(value.decode('ascii'))


def _unicode_map(font, width):
    if '/ToUnicode' not in font or not isinstance(font['/ToUnicode'], StreamObject):
        _fail('La fuente no contiene un mapa ToUnicode explícito verificable.')
    return _cached_unicode_map(font['/ToUnicode'].get_data(),width)


@lru_cache(maxsize=24)
def _cached_unicode_map(data,width):
    source = re.sub(rb'%[^\r\n]*', b'', data)
    if re.search(rb'\busecmap\b', source):
        _fail('El mapa de la fuente depende de otro CMap no resuelto.')
    spaces = re.findall(rb'\d+\s+begincodespacerange(.*?)endcodespacerange', source, re.S)
    if len(spaces) != 1:
        _fail('No se puede determinar de forma única el espacio de códigos de la fuente.')
    space_codes = re.findall(rb'<[0-9a-fA-F\s]+>', spaces[0])
    if not space_codes or any(len(_hex(t)) != width for t in space_codes):
        _fail('La longitud de códigos de esta fuente no es compatible.')
    result = {}

    def put(code, destination):
        if len(code) != width:
            _fail('El mapa contiene códigos CID de longitud no compatible.')
        try:
            char = destination.decode('utf-16-be')
        except UnicodeDecodeError:
            _fail('El mapa ToUnicode contiene una secuencia Unicode inválida.')
        if len(char) != 1:
            _fail('La fuente contiene ligaduras que requieren otro editor.')
        if code in result and result[code] != char:
            _fail('Hay un código CID con más de una traducción Unicode.')
        result[code] = char

    blocks = list(re.finditer(rb'(\d+)\s+begin(bfchar|bfrange)\b(.*?)end\2\b', source, re.S))
    if not blocks:
        _fail('El mapa ToUnicode no incluye correspondencias compatibles.')
    for block in blocks:
        count, kind, body = int(block[1]), block[2], block[3]
        if count > 65536:
            _fail('El mapa ToUnicode excede el límite de esta edición.')
        tokens = re.findall(rb'<[0-9a-fA-F\s]*>|\[|\]', body)
        if re.sub(rb'<[0-9a-fA-F\s]*>|\[|\]|\s+', b'', body):
            _fail('El mapa ToUnicode contiene instrucciones no compatibles.')
        index = 0
        try:
            for _ in range(count):
                first = _hex(tokens[index]); index += 1
                if kind == b'bfchar':
                    put(first, _hex(tokens[index])); index += 1
                    continue
                last = _hex(tokens[index]); index += 1
                start, stop = int.from_bytes(first, 'big'), int.from_bytes(last, 'big')
                if len(first) != width or len(last) != width or not 0 <= stop-start < 65536:
                    _fail('El mapa ToUnicode contiene un rango CID inválido.')
                if tokens[index] == b'[':
                    index += 1
                    for code in range(start, stop+1):
                        put(code.to_bytes(width, 'big'), _hex(tokens[index])); index += 1
                    if tokens[index] != b']':
                        _fail('La longitud de un rango ToUnicode no coincide con sus valores.')
                    index += 1
                else:
                    destination = _hex(tokens[index]); index += 1
                    number = int.from_bytes(destination, 'big')
                    for code in range(start, stop+1):
                        put(code.to_bytes(width, 'big'), number.to_bytes(len(destination), 'big'))
                        number += 1
            if index != len(tokens):
                _fail('El mapa ToUnicode contiene valores sobrantes no verificables.')
        except (IndexError, ValueError, OverflowError):
            _fail('No se pudo validar completamente el mapa ToUnicode de la fuente.')
    return MappingProxyType(result)


class _Font:
    def __init__(self, font):
        subtype = font.get('/Subtype')
        self.advances, self.default_advance = {}, None
        self.width, self.simple_glyphs, self.gidmap = 2, None, None
        self.cff_codes=None
        descriptor_font=font.get('/DescendantFonts',[font])[0].get_object()
        descriptor=descriptor_font.get('/FontDescriptor',{})
        descriptor=descriptor.get_object() if hasattr(descriptor,'get_object') else descriptor
        cff_stream=descriptor.get('/FontFile3')
        if cff_stream is not None:
            from fontTools.cffLib import CFFFontSet
            from fontTools.agl import toUnicode
            from fontTools.encodings.StandardEncoding import StandardEncoding
            cff=CFFFontSet();cff.decompile(io.BytesIO(cff_stream.get_object().get_data()),None)
            top=cff.topDictIndex[0];self.glyph_count=len(top.charset)
            if subtype=='/Type1' and '/ToUnicode' not in font:
                encoding=getattr(top,'Encoding','StandardEncoding')
                if encoding=='StandardEncoding':encoding=StandardEncoding
                if '/Encoding' in font:
                    from pypdf._codecs import charset_encoding
                    supplied=font['/Encoding']
                    if not isinstance(supplied,str) or supplied not in charset_encoding:_fail('Codificación CFF personalizada no compatible.')
                    decoded=charset_encoding[supplied]
                    self.mapping={bytes([i]):c for i,c in enumerate(decoded) if len(c)==1 and c.isprintable()}
                else:
                    self.mapping={bytes([i]):toUnicode(n) for i,n in enumerate(encoding) if n in top.charset and len(toUnicode(n))==1}
                self.width=1;self.cff_codes={int.from_bytes(c,'big') for c in self.mapping}
                self.advances={int(font.get('/FirstChar',0))+i:float(v) for i,v in enumerate(font.get('/Widths',[]))}
            elif subtype=='/Type0' and descriptor_font.get('/Subtype')=='/CIDFontType0' and font.get('/Encoding')=='/Identity-H':
                self.mapping=_unicode_map(font,2)
                self.cff_codes={int(n[3:]) for n in top.charset if n.startswith('cid')}
                self.default_advance=float(descriptor_font.get('/DW',1000))
                widths=descriptor_font.get('/W',[]);cursor=0
                while cursor<len(widths):
                    first=int(widths[cursor]);following=widths[cursor+1];cursor+=2
                    if isinstance(following,ArrayObject):
                        for offset,v in enumerate(following):self.advances[first+offset]=float(v)
                    else:
                        last=int(following);v=float(widths[cursor]);cursor+=1
                        if not 0<=last-first<65536:_fail('Rango de anchuras CFF inválido.')
                        for code in range(first,last+1):self.advances[code]=v
            else:_fail('Este mapa de fuente CFF todavía no es compatible.')
        self.standard = subtype == '/Type1' and str(font.get('/BaseFont', '')).lstrip('/') in pdfium.PdfFont.STANDARD_FONTS[:12]
        if self.cff_codes is not None:
            pass
        elif self.standard:
            from pypdf._codecs import charset_encoding
            encoding = font.get('/Encoding', '/StandardEncoding')
            if not isinstance(encoding, str) or encoding not in ('/StandardEncoding', '/WinAnsiEncoding', '/MacRomanEncoding') or '/ToUnicode' in font:
                _fail('La fuente estándar usa un mapa personalizado no compatible.')
            self.width = 1
            self.mapping = {bytes([i]): c for i, c in enumerate(charset_encoding[encoding]) if len(c) == 1 and c.isprintable()}
        else:
            if subtype == '/Type0':
                if font.get('/Encoding') != '/Identity-H':
                    _fail('La fuente compuesta no utiliza Identity-H.')
                descendants = font.get('/DescendantFonts', [])
                if len(descendants) != 1:
                    _fail('La fuente tiene una estructura descendiente no compatible.')
                descendant = descendants[0].get_object()
                if descendant.get('/Subtype') != '/CIDFontType2':
                    _fail('Esta edición fiel requiere un programa TrueType CIDFontType2.')
                self.default_advance=float(descendant.get('/DW',1000))
                widths=descendant.get('/W',[])
                cursor=0
                while cursor<len(widths):
                    first=int(widths[cursor]); following=widths[cursor+1]; cursor+=2
                    if isinstance(following,ArrayObject):
                        for offset,value in enumerate(following):
                            self.advances[first+offset]=float(value)
                    else:
                        last=int(following); value=float(widths[cursor]); cursor+=1
                        if not 0<=last-first<65536:
                            _fail('El rango de anchuras CID no es compatible.')
                        for code in range(first,last+1): self.advances[code]=value
            elif subtype == '/TrueType':
                self.width, descendant = 1, font
                self.advances={int(font.get('/FirstChar',0))+i:float(v) for i,v in enumerate(font.get('/Widths',[]))}
            else:
                _fail('Este tipo de fuente aún no tiene una ruta de edición fiel validada.')
            self.mapping = _unicode_map(font, self.width)
            descriptor = descendant.get('/FontDescriptor')
            descriptor = descriptor.get_object() if descriptor else {}
            if '/FontFile2' not in descriptor:
                _fail('El programa de la fuente original no está incrustado como TrueType.')
            with TTFont(io.BytesIO(descriptor['/FontFile2'].get_data()), lazy=True) as program:
                self.glyph_count = int(program['maxp'].numGlyphs)
                if self.width == 1:
                    internal = program.getBestCmap() or {}
                    if not internal and '/Encoding' not in font:
                        # ReportLab subsets commonly retain only their built-in
                        # Macintosh format-6 cmap. getBestCmap() intentionally
                        # ignores it because it is not a Unicode cmap. Here the
                        # PDF uses that built-in code map; ToUnicode separately
                        # supplies the exact Unicode correspondence.
                        builtin = [table.cmap for table in program['cmap'].tables
                                   if (table.platformID, table.platEncID, table.format) == (1, 0, 6)]
                        if len(builtin) == 1:
                            internal = builtin[0]
                    self.simple_glyphs = {code: program.getGlyphID(name) for code, name in internal.items()}
            if self.width == 2:
                cidmap = descendant.get('/CIDToGIDMap', '/Identity')
                cidmap = cidmap.get_object() if hasattr(cidmap, 'get_object') else cidmap
                self.gidmap = None if cidmap == '/Identity' else cidmap.get_data() if isinstance(cidmap, StreamObject) else None
                if cidmap != '/Identity' and self.gidmap is None:
                    _fail('No se pudo verificar el mapa CID a glifo de la fuente.')
        self.reverse = {}
        for code, char in self.mapping.items():
            self.reverse.setdefault(char, set()).add(code)
        self.mapping = MappingProxyType(self.mapping)
        self.reverse = MappingProxyType({char: frozenset(codes) for char, codes in self.reverse.items()})
        if self.simple_glyphs is not None:
            self.simple_glyphs = MappingProxyType(self.simple_glyphs)

    def decode(self, data):
        if len(data) % self.width:
            _fail('El texto contiene un código CID incompleto.')
        try:
            return ''.join(self.mapping[data[i:i+self.width]] for i in range(0, len(data), self.width))
        except KeyError:
            _fail('El texto utiliza un CID sin traducción Unicode verificable.')

    def advance(self, encoded):
        total=0
        for offset in range(0,len(encoded),self.width):
            code=int.from_bytes(encoded[offset:offset+self.width],'big')
            value=self.advances.get(code,self.default_advance)
            if value is None:
                _fail('No se pudo verificar el avance original de un fragmento de texto.')
            total+=value
        return total

    def valid_glyph(self, code):
        cid = int.from_bytes(code, 'big')
        if self.cff_codes is not None:
            if cid not in self.cff_codes:_fail('El glifo no está incluido en la fuente CFF original.')
            return
        if self.standard:
            return
        if self.simple_glyphs is not None:
            gid = self.simple_glyphs.get(cid, 0)
            if not 0 < gid < self.glyph_count:
                _fail('No se pudo demostrar la presencia de ese glifo en la fuente simple incrustada.')
            return
        if self.gidmap is None:
            gid = cid
        else:
            if 2*cid+2 > len(self.gidmap):
                _fail('El carácter no tiene glifo en el mapa de la fuente original.')
            gid = int.from_bytes(self.gidmap[2*cid:2*cid+2], 'big')
        if not 0 < gid < self.glyph_count:
            _fail('La fuente original no incluye un glifo verificable para ese carácter.')

    def edit(self, original, new_text):
        old = self.decode(original)
        pieces = []
        for tag, a, b, c, d in SequenceMatcher(a=old, b=new_text, autojunk=False).get_opcodes():
            if tag == 'equal':
                pieces.append(original[self.width*a:self.width*b])
            elif tag in ('insert', 'replace'):
                for char in new_text[c:d]:
                    codes = self.reverse.get(char, set())
                    if not codes:
                        _fail(f'La fuente incrustada no incluye {char!r}. Para escribirlo hace falta una fuente completa; no se sustituyó la tipografía.')
                    if len(codes) != 1:
                        _fail(f'La fuente original no tiene un código único para {char!r}. El documento no se ha cambiado.')
                    code = next(iter(codes))
                    self.valid_glyph(code)
                    pieces.append(code)
        encoded = b''.join(pieces)
        if self.decode(encoded) != new_text:
            _fail('La verificación de codificación del texto no coincide.')
        return encoded


@dataclass(frozen=True)
class _Operation:
    operator: bytes
    operands: list
    spans: list


def _operations(raw):
    """Use pypdf's token reader while retaining exact byte spans for operands."""
    stream = io.BytesIO(raw)
    result, operands, spans = [], [], []
    while True:
        peek = read_non_whitespace(stream)
        if not peek:
            break
        stream.seek(-1, 1)
        start = stream.tell()
        if peek.isalpha() or peek in (b"'", b'"'):
            operator = read_until_regex(stream=stream, regex=NameObject.delimiter_pattern, length=256)
            if operator == b'BI':
                _fail('La página contiene una imagen inline; la edición de texto se mantiene bloqueada.')
            result.append(_Operation(operator, operands, spans))
            operands, spans = [], []
        elif peek == b'%':
            while stream.read(1) not in (b'\r', b'\n', b''):
                pass
        else:
            value = read_object(stream, None)
            operands.append(value)
            spans.append((start, stream.tell()))
    if operands:
        _fail('El stream de contenido termina con operandos incompletos.')
    return result


def _array_parts(raw, span):
    stream = io.BytesIO(raw)
    stream.seek(span[0])
    if stream.read(1) != b'[':
        _fail('No se pudo localizar el operando TJ original.')
    parts = []
    while True:
        peek = read_non_whitespace(stream)
        if peek == b']':
            return parts
        if not peek:
            _fail('El operando TJ está incompleto.')
        stream.seek(-1, 1)
        start = stream.tell()
        value = read_object(stream, None)
        if isinstance(value, (ByteStringObject, TextStringObject)):
            parts.append((_raw_string(value), start, stream.tell()))
        elif not isinstance(value, (int, float)):
            _fail('El operando TJ contiene un elemento no compatible.')


def _resource_digest(resources):
    seen = set()
    def freeze(value):
        if isinstance(value, IndirectObject):
            key = (value.idnum, value.generation)
            if key in seen:
                return ['ref', *key]
            seen.add(key)
            return ['ref', *key, freeze(value.get_object())]
        if isinstance(value, dict):
            result = {str(k): freeze(v) for k, v in sorted(value.items())}
            if isinstance(value, StreamObject):
                result['__decoded_stream_sha256__'] = hashlib.sha256(value.get_data()).hexdigest()
            return result
        if isinstance(value, (list, tuple)):
            return [freeze(v) for v in value]
        if isinstance(value, bytes):
            return ['bytes', value.hex()]
        return [type(value).__name__, str(value)]
    import json
    return hashlib.sha256(json.dumps(freeze(resources), sort_keys=True).encode()).hexdigest()


def _pdfium_strings(data, page_index):
    document = pdfium.PdfDocument(data)
    try:
        page = document[page_index]
        textpage = page.get_textpage()
        objects = list(page.get_objects(max_depth=0, textpage=textpage))
        if any(o.type == pdfium.raw.FPDF_PAGEOBJ_FORM for o in objects):
            _fail('La página contiene Forms anidados; no se puede garantizar la correspondencia de texto.')
        text_objects = [o for o in objects if o.type == pdfium.raw.FPDF_PAGEOBJ_TEXT]
        handles = {C.cast(o.raw, C.c_void_p).value: [] for o in text_objects}
        for i in range(textpage.count_chars()):
            owner = pdfium.raw.FPDFText_GetTextObject(textpage, i)
            address = C.cast(owner, C.c_void_p).value
            if address in handles and not pdfium.raw.FPDFText_IsGenerated(textpage, i):
                code = pdfium.raw.FPDFText_GetUnicode(textpage, i)
                if not code:
                    _fail('PDFium detectó un carácter sin Unicode; la correspondencia no es segura.')
                handles[address].append(chr(code))
        return [(o.extract(), ''.join(handles[C.cast(o.raw, C.c_void_p).value])) for o in text_objects]
    finally:
        document.close()


@dataclass(frozen=True)
class _Show:
    operation: int
    font: _Font
    parts: list
    text: str


_PLAN_CACHE = OrderedDict()
_CACHE_SOURCE_BYTES = 16 * 1024 * 1024


def _prepare(data, page_index, allow_cache=True):
    reader = PdfReader(io.BytesIO(data), strict=True)
    if reader.is_encrypted:
        _fail('La edición incremental de documentos cifrados no está habilitada.')
    key = (hashlib.sha256(data).digest(), page_index)
    if allow_cache and key in _PLAN_CACHE:
        _, plan = _PLAN_CACHE[key]
        _PLAN_CACHE.move_to_end(key)
        return (reader, *plan)
    if not 0 <= page_index < len(reader.pages):
        _fail('La página solicitada no existe.')
    page = reader.pages[page_index]
    contents = page.get('/Contents')
    contents = contents.get_object() if contents is not None else None
    if isinstance(contents,ArrayObject):
        combined=DecodedStreamObject()
        combined.set_data(b'\n'.join(s.get_object().get_data() for s in contents))
        contents=combined
    if not isinstance(contents, StreamObject):
        _fail('La página debe tener un único stream de contenido para esta edición fiel.')
    raw = contents.get_data()
    parsed = ContentStream(contents, reader).operations
    operations = _operations(raw)
    if [o.operator for o in operations] != [op for _, op in parsed]:
        _fail('Los analizadores no coinciden en los operadores originales.')
    resources = page['/Resources']
    fonts, shows, stack = {}, [], []
    current_font, render_mode, in_text = None, 0, False
    for index, operation in enumerate(operations):
        op, args = operation.operator, operation.operands
        if op == b'q':
            stack.append((current_font, render_mode))
        elif op == b'Q':
            if not stack:
                _fail('La pila gráfica original está desequilibrada.')
            current_font, render_mode = stack.pop()
        elif op == b'BT':
            if in_text:
                _fail('La página contiene objetos de texto anidados.')
            in_text = True
        elif op == b'ET':
            in_text = False
        elif op == b'Tf':
            if len(args) != 2:
                _fail('El selector de fuente original no es compatible.')
            current_font = str(args[0])
        elif op == b'Tr':
            render_mode = int(args[0])
        elif op == b'gs':
            states = resources.get('/ExtGState', {})
            states = states.get_object() if hasattr(states, 'get_object') else states
            state = states.get(args[0], {})
            state = state.get_object() if hasattr(state, 'get_object') else state
            if '/Font' in state:
                _fail('La fuente se establece mediante un estado gráfico no compatible.')
        elif op == b'Do':
            xobjects = resources.get('/XObject', {})
            xobjects = xobjects.get_object() if hasattr(xobjects, 'get_object') else xobjects
            xobject = xobjects.get(args[0], {})
            xobject = xobject.get_object() if hasattr(xobject, 'get_object') else xobject
            if xobject.get('/Subtype') == '/Form':
                _fail('La página invoca contenido Form anidado; la edición se mantiene bloqueada.')
        elif op in (b"'", b'"'):
            _fail('Esta página utiliza operadores de texto con saltos implícitos no compatibles.')
        elif op in (b'Tj', b'TJ'):
            if not in_text or current_font is None or render_mode > 3:
                _fail('El estado de texto o recorte de esta página no permite una edición segura.')
            if current_font not in fonts:
                fonts[current_font] = _Font(resources['/Font'][current_font].get_object())
            font = fonts[current_font]
            if len(args) != 1:
                _fail('El operador de texto tiene un número de operandos inesperado.')
            if op == b'Tj':
                parts = [(_raw_string(args[0]), *operation.spans[0])]
            else:
                if not isinstance(args[0], ArrayObject):
                    _fail('El operando TJ no es un arreglo PDF.')
                parts = _array_parts(raw, operation.spans[0])
            text=''.join(font.decode(p[0]) for p in parts)
            if text:  # An empty Tj has no PDFium text object.
                shows.append(_Show(index, font, tuple(parts), text))
    if stack or in_text:
        _fail('El estado gráfico o de texto original está incompleto.')
    native = _pdfium_strings(data, page_index)
    if len(native) != len(shows) or any(not _source_matches(t[1],s.text) for t, s in zip(native, shows)):
        _fail('No hay correspondencia exacta entre todos los objetos PDFium y los operadores de texto.')
    # Cached plans contain no PdfReader, PDF objects, live handles or mutable
    # operand objects. The incremental writer always receives a fresh reader.
    plan = (raw, tuple(_Operation(o.operator, (), ()) for o in operations),
            tuple(shows), tuple(native), _resource_digest(page['/Resources']))
    if len(data) <= _CACHE_SOURCE_BYTES:
        _PLAN_CACHE[key] = (len(data), plan)
        _PLAN_CACHE.move_to_end(key)
        while len(_PLAN_CACHE) > 2 or sum(size for size, _ in _PLAN_CACHE.values()) > _CACHE_SOURCE_BYTES:
            _PLAN_CACHE.popitem(last=False)
    return reader, *plan


def _patch_native(data: bytes, page_index: int, text_ordinal: int,
                 expected_text: str, new_text: str) -> bytes:
    """Replace CID bytes in one existing Tj/TJ string; append a PDF revision.

    text_ordinal counts root TEXT objects, not every page object. expected_text
    is the exact PDFium object extraction. A generated trailing separator is
    stripped from the edited UI value; it is never inserted into PDF content.
    Font size/style edits, nested Forms and uncertain mappings are unsupported.
    """
    reader, raw, operations, shows, native, resource_hash = _prepare(data, page_index)
    if not 0 <= text_ordinal < len(shows):
        _fail('El objeto de texto seleccionado no existe.')
    extracted, original_text = native[text_ordinal]
    if expected_text not in (extracted,original_text):
        _fail('El texto seleccionado cambió desde su análisis. Vuelve a seleccionarlo.')
    if new_text == expected_text:
        return data
    show = shows[text_ordinal]
    if extracted != original_text and expected_text==extracted:
        if not extracted.startswith(original_text) or extracted[len(original_text):].strip(' '):
            _fail('La selección incluye separadores generados que no se pueden editar con seguridad.')
        suffix = extracted[len(original_text):]
        if suffix and new_text.endswith(suffix):
            new_text = new_text[:-len(suffix)]
    if new_text and not new_text.isprintable():
        _fail('Esta operación admite texto de una línea sin caracteres de control.')
    if new_text == original_text:
        return data
    # A following show without a text-line/matrix reset would move when advances
    # change. Do not silently alter another object to compensate for that.
    dependent=False
    parsed_ops=_operations(raw)
    for following in parsed_ops[show.operation+1:]:
        if following.operator in (b'ET', b'Tm', b'Td', b'TD', b'T*'):
            break
        if following.operator in (b'Tj', b'TJ', b"'", b'"'):
            if following.operator==b'TJ' and all(isinstance(v,(int,float)) or type(v).__name__ in ('NumberObject','FloatObject') for v in following.operands[0]):continue
            dependent=True;break
    # Keep every TJ number and every other string byte-for-byte. A change that
    # crosses fragments or falls on an ambiguous fragment boundary is rejected.
    prefix = 0
    while prefix < min(len(original_text), len(new_text)) and original_text[prefix] == new_text[prefix]:
        prefix += 1
    suffix = 0
    while suffix < min(len(original_text)-prefix, len(new_text)-prefix) and original_text[-suffix-1] == new_text[-suffix-1]:
        suffix += 1
    old_end = len(original_text)-suffix
    position, candidates = 0, []
    for part in show.parts:
        part_text = show.font.decode(part[0])
        end = position+len(part_text)
        if position <= prefix and old_end <= end:
            candidates.append((part, part_text, position))
        position = end
    if len(candidates) != 1:
        _fail('El cambio cruza fragmentos TJ o una frontera ambigua; el documento no se ha cambiado.')
    part, part_text, start = candidates[0]
    replacement = (part_text[:prefix-start] +
                   new_text[prefix:len(new_text)-suffix if suffix else None] +
                   part_text[old_end-start:])
    encoded = show.font.edit(part[0], replacement)
    token = b'<' + encoded.hex().encode('ascii') + b'>'
    edits=[(part[1],part[2],token)]
    if dependent:
        if parsed_ops[show.operation].operator!=b'Tj' or len(show.parts)!=1:_fail('Este ajuste dependiente necesita una secuencia Tj simple.')
        size=tc=tw=0.;states=[]
        for op in parsed_ops[:show.operation]:
            if op.operator==b'q':states.append((size,tc,tw))
            elif op.operator==b'Q':size,tc,tw=states.pop()
            elif op.operator==b'Tf':size=float(op.operands[1])
            elif op.operator==b'Tc':tc=float(op.operands[0])
            elif op.operator==b'Tw':tw=float(op.operands[0])
        if not size:_fail('Tamaño de fuente inválido para conservar el avance.')
        delta=show.font.advance(encoded)-show.font.advance(part[0])+(len(replacement)-len(part_text))*tc*1000/size
        if show.font.width==1:delta+=(encoded.count(b' ')-part[0].count(b' '))*tw*1000/size
        match=re.match(rb'\s*Tj\b',raw[part[2]:])
        if not match:_fail('No se pudo situar el ajuste de avance.')
        position=part[2]+match.end()
        number=format(delta,'.10f').rstrip('0').rstrip('.') or '0'
        edits.append((position,position,(' ['+number+'] TJ ').encode('ascii')))
    updated=raw
    for start,end,value in sorted(edits,reverse=True):updated=updated[:start]+value+updated[end:]
    writer = PdfWriter(reader, incremental=True)
    # pypdf does not clone an unreferenced previous xref-stream object into
    # _objects. Never reuse its ID: a reader can retain that old xref object in
    # its cache while resolving the /Prev chain of the next revision.
    while len(writer._objects) < int(reader.trailer['/Size'])-1:
        writer._objects.append(None)
    replacement_stream = DecodedStreamObject()
    replacement_stream.set_data(updated)
    writer.pages[page_index][NameObject('/Contents')] = writer._add_object(replacement_stream)
    allowed_ids = {writer.pages[page_index].indirect_reference.idnum,
                   replacement_stream.indirect_reference.idnum}
    if any(ref.idnum not in allowed_ids for ref in writer.list_objects_in_increment()):
        _fail('El guardado intentó modificar objetos adicionales; la operación se bloqueó.')
    output = io.BytesIO()
    writer.write(output)
    result = output.getvalue()
    if not result.startswith(data):
        _fail('El guardado no conservó íntegra la revisión original.')
    check = _prepare(result, page_index, allow_cache=False)
    if check[5] != resource_hash:
        _fail('La verificación detectó cambios en los recursos originales.')
    wanted=[s.text for s in shows]
    wanted[text_ordinal:text_ordinal+1]=[new_text] if new_text else []
    if [s.text for s in check[3]]!=wanted:
        _fail('La verificación del texto guardado no coincide con la edición solicitada.')
    return result


def patch_native(data: bytes, page_index: int, text_ordinal: int,
                 expected_text: str, new_text: str) -> bytes:
    """Return an incrementally patched PDF, or fail without modifying input.

    See _patch_native for the supported native-text subset and separator rules.
    """
    try:
        return _patch_native(data, page_index, text_ordinal, expected_text, new_text)
    except UnsupportedNativePatch:
        raise
    except Exception as error:
        raise UnsupportedNativePatch('No se pudo verificar esta edición de texto con la fuente original. El documento no se ha cambiado.') from error


def prepare_native(data: bytes, page_index: int) -> int:
    """Prepare/cache the immutable native-text plan for a page; return show count."""
    try:
        return len(_prepare(data, page_index)[3])
    except UnsupportedNativePatch:
        raise
    except Exception as error:
        raise UnsupportedNativePatch('No se pudo preparar una correspondencia fiel del texto de esta página.') from error


def source_texts(data,page_index):
    return tuple(s.text for s in _prepare(data,page_index)[3])


def patch_native_run(data, page_index, ordinals, expected_text, new_text):
    """Edit a collinear run fragmented into independently positioned Tj's.

    Equal characters keep their exact source CID bytes and owner. Inserted
    characters belong to the fragment at the edit. Td advances compensate for
    changed glyph widths, retaining the original kerning between fragments.
    No font, color, matrix scale or content outside the run is regenerated.
    """
    reader,raw,_,shows,native,resource_hash=_prepare(data,page_index)
    if not ordinals or ordinals!=list(range(ordinals[0],ordinals[-1]+1)):
        _fail('El bloque no tiene una secuencia contigua de fragmentos verificables.')
    selected=[shows[i] for i in ordinals]
    original=''.join(s.text for s in selected)
    if original!=expected_text:
        _fail('Los fragmentos de esta línea no coinciden con el texto analizado.')
    if new_text==original: return data
    if new_text and not new_text.isprintable():
        _fail('Los saltos de línea todavía no se recomponen con la fuente original.')
    if any(s.font is not selected[0].font or len(s.parts)!=1 for s in selected):
        _fail('Este bloque combina fuentes o ajustes TJ que requieren edición por separado.')
    operations=_operations(raw)
    size=char_space=word_space=0.; horizontal=1.; states={}; stack=[]
    for k,o in enumerate(operations):
        if o.operator==b'q': stack.append((size,char_space,word_space,horizontal))
        elif o.operator==b'Q': size,char_space,word_space,horizontal=stack.pop()
        elif o.operator==b'Tf': size=float(o.operands[1])
        elif o.operator==b'Tc': char_space=float(o.operands[0])
        elif o.operator==b'Tw': word_space=float(o.operands[0])
        elif o.operator==b'Tz': horizontal=float(o.operands[0])/100
        elif o.operator in (b'Tj',b'TJ'): states[k]=(size,char_space,word_space,horizontal)
    # Reject uncertain layout dependencies before changing any operands.
    moves=[]
    for left,right in zip(selected,selected[1:]):
        between=operations[left.operation+1:right.operation]
        td=[o for o in between if o.operator==b'Td']
        if len(td)!=1 or len(td[0].operands)!=2 or float(td[0].operands[1])!=0 or any(
            o.operator in (b'BT',b'ET',b'Tm',b'TD',b'T*',b'cm',b'q',b'Q',b'Tj',b'TJ') for o in between):
            _fail('Estos fragmentos no comparten una línea con avances Td verificables.')
        if states[left.operation]!=states[right.operation]:
            _fail('La línea cambia el estado de espaciado entre fragmentos.')
        moves.append(td[0])
    owners=[]
    for i,s in enumerate(selected): owners.extend([i]*len(s.text))
    pieces=['']*len(selected)
    for tag,a,b,c,d in SequenceMatcher(a=original,b=new_text,autojunk=False).get_opcodes():
        if tag=='equal':
            for old,new in zip(range(a,b),range(c,d)): pieces[owners[old]]+=new_text[new]
        elif tag in ('insert','replace'):
            owner=owners[min(a,len(owners)-1)]
            pieces[owner]+=new_text[c:d]
    changes=[]
    line_shift=0.
    for i,(show,value) in enumerate(zip(selected,pieces)):
        part=show.parts[0]
        if value==show.text: continue
        encoded=show.font.edit(part[0],value)
        changes.append((part[1],part[2],b'<'+encoded.hex().encode('ascii')+b'>'))
        if i<len(moves):
            size,tc,tw,hz=states[show.operation]
            # Word spacing applies only to the single-byte space character.
            old_spaces=part[0].count(b' ') if show.font.width==1 else 0
            new_spaces=encoded.count(b' ') if show.font.width==1 else 0
            delta=((show.font.advance(encoded)-show.font.advance(part[0]))*size/1000
                   +(len(value)-len(show.text))*tc+(new_spaces-old_spaces)*tw)*hz
            if abs(delta)>1e-10:
                line_shift+=delta
                td=moves[i]; start,end=td.spans[0]
                changes.append((start,end,format(float(td.operands[0])+delta,'.12g').encode('ascii')))
    # A later line/cell in this BT must retain its original position when an
    # internal Td moved the selected run. Restore the line-matrix translation
    # at the first outgoing Td; a Tm/BT/ET already resets that dependency.
    for following in operations[selected[-1].operation+1:]:
        if following.operator in (b'ET',b'BT',b'Tm'): break
        if following.operator in (b'Tj',b'TJ',b"'",b'"'):
            _fail('Otro texto depende directamente del avance final de esta línea.')
        if following.operator==b'Td':
            if abs(line_shift)>1e-10:
                start,end=following.spans[0]
                changes.append((start,end,format(float(following.operands[0])-line_shift,'.12g').encode('ascii')))
            break
        if following.operator in (b'cm',b'q',b'Q',b'TD',b'T*'):
            _fail('No se puede verificar la posición del contenido después de la línea.')
    updated=raw
    for start,end,replacement in sorted(changes,reverse=True):
        updated=updated[:start]+replacement+updated[end:]
    writer=PdfWriter(reader,incremental=True)
    while len(writer._objects)<int(reader.trailer['/Size'])-1: writer._objects.append(None)
    stream=DecodedStreamObject(); stream.set_data(updated)
    writer.pages[page_index][NameObject('/Contents')]=writer._add_object(stream)
    allowed={writer.pages[page_index].indirect_reference.idnum,stream.indirect_reference.idnum}
    if any(ref.idnum not in allowed for ref in writer.list_objects_in_increment()):
        _fail('El guardado intentó modificar objetos adicionales.')
    output=io.BytesIO();writer.write(output);result=output.getvalue()
    if not result.startswith(data): _fail('No se conservó la revisión original.')
    check=_prepare(result,page_index,allow_cache=False)
    wanted=[s.text for s in shows]
    wanted[ordinals[0]:ordinals[-1]+1]=[p for p in pieces if p]
    if check[5]!=resource_hash or [s.text for s in check[3]]!=wanted:
        _fail('La verificación de la fuente o del texto de la línea no coincide.')
    return result


def joinable_fragments(data,page_index):
    """Pairs of source text ordinals with a verifiable shared-line Td."""
    _,raw,_,shows,_,_=_prepare(data,page_index)
    operations=_operations(raw)
    result=set()
    for i,(left,right) in enumerate(zip(shows,shows[1:])):
        between=operations[left.operation+1:right.operation]
        moves=[o for o in between if o.operator==b'Td']
        if (left.font is right.font and len(left.parts)==len(right.parts)==1
                and len(moves)==1 and len(moves[0].operands)==2 and float(moves[0].operands[1])==0
                and not any(o.operator in (b'BT',b'ET',b'Tm',b'TD',b'T*',b'cm',b'q',b'Q',b'Tf',b'Tc',b'Tw',b'Tz') for o in between)):
            result.add((i,i+1))
    return result
