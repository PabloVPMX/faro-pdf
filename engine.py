"""Local PDFium document model. All mutations use reversible PDF snapshots."""
import ctypes as C
import hashlib
import io
import os
from pathlib import Path
import tempfile
import re
import unicodedata
from difflib import SequenceMatcher

import pypdfium2 as pdf

TEXT = pdf.raw.FPDF_PAGEOBJ_TEXT
IMAGE = pdf.raw.FPDF_PAGEOBJ_IMAGE


def comparable_text(value):
    # Some embedded cmap tables alias the space glyph to U+00A0.
    return unicodedata.normalize('NFC', value).replace('\xa0', ' ').replace('\r\n', '\n')


def align_character_geometry(rows,value,origin=None):
    """Align source spaces suppressed by PDFium; never invent visible glyphs."""
    actual=''.join(r['character'] for r in rows)
    if actual==value: return rows
    result=[]
    for tag,a,b,c,d in SequenceMatcher(a=actual,b=value,autojunk=False).get_opcodes():
        if tag=='equal': result.extend(rows[a:b]); continue
        if tag!='insert' or set(value[c:d])-{' '}: return None
        previous=rows[a-1] if a else None
        following=rows[a] if a<len(rows) else None
        left=previous['bounds'][1] if previous else origin[0] if origin else following['origin'][0] if following else 0
        right=following['origin'][0] if following else left
        y=following['origin'][1] if following else previous['origin'][1] if previous else origin[1] if origin else 0
        for offset,char in enumerate(value[c:d]):
            x=left+(right-left)*offset/(d-c)
            result.append(dict(character=char,origin=(x,y),bounds=(x,x,y,y)))
    return result


def _encodable(character):
    try:
        character.encode('cp1252')
        return True
    except UnicodeEncodeError:
        return False


def wide(value):
    data = value.encode('utf-16-le') + b'\0\0'
    return (C.c_ushort * (len(data) // 2)).from_buffer_copy(data)


class Document:
    def __init__(self, path):
        self.source = Path(path).resolve()
        self.saved_path = None
        self.doc = None
        self.page = None
        self.textpage = None
        self.objects = []
        self.index = 0
        self.undo_stack = []
        self.redo_stack = []
        self._load(self.source.read_bytes())
        self.current_version = self.saved_version = 0
        self.next_version = 1

    def _load(self, data):
        self.close()
        self._data = data
        self.doc = pdf.PdfDocument(data)
        self._edit_data=data
        has_forms=False
        for i in range(len(self.doc)):
            page=self.doc[i]
            try:has_forms=has_forms or any(o.type==pdf.raw.FPDF_PAGEOBJ_FORM for o in page.get_objects(max_depth=0))
            finally:page.close()
        if has_forms:
            try:
                from forms import editable_forms
                self._edit_data=editable_forms(data)
            except ValueError:
                self._edit_data=data
            if self._edit_data!=data:
                self.doc.close();self.doc=pdf.PdfDocument(self._edit_data)
        self._font_resources = self._read_font_resources(self._edit_data)
        self.native_preflight = {}
        self.index = min(self.index, len(self.doc) - 1)
        self.set_page(self.index)

    def close_page(self):
        self.objects = []
        self._character_rows = None
        self._text_runs = None
        self._text_blocks = None
        if self.textpage:
            self.textpage.close()
            self.textpage = None
        if self.page:
            self.page.close()
            self.page = None

    def close(self):
        self.close_page()
        if self.doc:
            self.doc.close()
            self.doc = None

    def set_page(self, index):
        self.close_page()
        self.index = index
        self.page = self.doc[index]
        self.textpage = self.page.get_textpage()
        self.objects = list(self.page.get_objects(max_depth=0, textpage=self.textpage))
        if index not in self.native_preflight and any(obj.type == TEXT and pdf.raw.FPDFTextObj_GetTextRenderMode(obj) != 3 for obj in self.objects):
            try:
                from content_patch import prepare_native,source_texts
                self.native_preflight[index] = {'objects': prepare_native(self._edit_data, index),
                                                'texts':source_texts(self._edit_data,index), 'error': None}
            except Exception as error:
                self.native_preflight[index] = {'error': str(error)}

    def bytes(self):
        output = io.BytesIO()
        self.doc.save(output)
        return output.getvalue()

    @property
    def dirty(self):
        return self.current_version != self.saved_version

    def info(self, index):
        obj = self.objects[index]
        data = dict(index=index, type=obj.type, bounds=obj.get_bounds(), text='', size=12)
        if obj.type == TEXT:
            data['text'] = obj.extract()
            source=self.native_preflight.get(self.index,{}).get('texts')
            if source is not None:
                ordinal=sum(o.type==TEXT for o in self.objects[:index])
                data['text']=source[ordinal]
            data['size'] = obj.get_font_size()
            data['font'] = obj.get_font().get_base_name()
            resource_names = self._font_resources.get(self.index, [])
            for name in resource_names:
                if re.sub(r'^[A-Z]{6}\+', '', name) == data['font']:
                    data['font'] = name
                    break
            font = obj.get_font()
            data['family'] = font.get_family_name()
            data['embedded'] = font.is_embedded
            data['weight'] = font.get_weight()
            data['subset'] = bool(re.match(r'^[A-Z]{6}\+', data['font']))
            data['italic'] = bool(pdf.raw.FPDFFont_GetFlags(font) & 64)
            data['matrix'] = obj.get_matrix().get()
            color = [C.c_uint() for _ in range(4)]
            if pdf.raw.FPDFPageObj_GetFillColor(obj, *[C.byref(v) for v in color]):
                data['color'] = tuple(v.value for v in color[:3])
        return data

    @staticmethod
    def _read_font_resources(data):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data), strict=False)
        found = {}
        def scan(resources, names, visited):
            if not resources:
                return
            resources = resources.get_object()
            identity = id(resources)
            if identity in visited:
                return
            visited.add(identity)
            fonts = resources.get('/Font', {})
            for entry in fonts.get_object().values() if hasattr(fonts, 'get_object') else fonts.values():
                base = entry.get_object().get('/BaseFont')
                if base:
                    names.append(str(base).lstrip('/'))
            objects = resources.get('/XObject', {})
            for entry in objects.get_object().values() if hasattr(objects, 'get_object') else objects.values():
                value = entry.get_object()
                if value.get('/Subtype') == '/Form':
                    scan(value.get('/Resources'), names, visited)
        for i, page in enumerate(reader.pages):
            names = []
            scan(page.get('/Resources'), names, set())
            found[i] = names
        return found

    def font_data(self, index):
        font = self.objects[index].get_font()
        count = C.c_size_t()
        if not pdf.raw.FPDFFont_GetFontData(font, None, 0, C.byref(count)) or not count.value:
            return None
        buffer = (C.c_ubyte * count.value)()
        if not pdf.raw.FPDFFont_GetFontData(font, buffer, count.value, C.byref(count)):
            return None
        return bytes(buffer[:count.value])

    def character_geometry(self, index):
        """Actual source-character geometry; generated/other-object chars excluded."""
        if self._character_rows is None:
            self._character_rows = self.page_character_geometry(self.textpage)
        target = C.cast(self.objects[index].raw, C.c_void_p).value
        rows=list(self._character_rows.get(target, []))
        value=self.info(index)['text']
        matrix=self.objects[index].get_matrix().get()
        aligned=align_character_geometry(rows,value,matrix[4:6])
        return aligned if aligned is not None else rows

    @staticmethod
    def object_character_geometry(textpage, page_object):
        target = C.cast(page_object.raw, C.c_void_p).value
        return Document.page_character_geometry(textpage, {target}).get(target, [])

    @staticmethod
    def page_character_geometry(textpage, targets=None):
        rows = {}
        for position in range(pdf.raw.FPDFText_CountChars(textpage)):
            obj = pdf.raw.FPDFText_GetTextObject(textpage, position)
            address = C.cast(obj, C.c_void_p).value if obj else None
            if not address or (targets is not None and address not in targets) or pdf.raw.FPDFText_IsGenerated(textpage, position):
                continue
            x, y = C.c_double(), C.c_double()
            box = [C.c_double() for _ in range(4)]
            if not pdf.raw.FPDFText_GetCharOrigin(textpage, position, C.byref(x), C.byref(y)):
                raise ValueError('No se pudo leer la posición original de un carácter.')
            if not pdf.raw.FPDFText_GetCharBox(textpage, position, *[C.byref(v) for v in box]):
                raise ValueError('No se pudo leer la geometría original de un carácter.')
            rows.setdefault(address, []).append(dict(character=chr(pdf.raw.FPDFText_GetUnicode(textpage, position)),
                             origin=(x.value, y.value), bounds=tuple(v.value for v in box)))
        return rows

    def text_runs(self):
        """Join adjacent fragments on one baseline, never across table gutters.

        The source objects and original glyph positions remain separate. Runs
        are UI/editing units; joining them does not rewrite the document.
        """
        if self._text_runs is not None:
            return self._text_runs
        if not any(obj.type == TEXT and pdf.raw.FPDFTextObj_GetTextRenderMode(obj) != 3 for obj in self.objects):
            self._text_runs = []
            return self._text_runs
        try:
            from content_patch import joinable_fragments
            joinable=joinable_fragments(self._edit_data,self.index)
        except ValueError:
            joinable=set()
        runs = []
        ordinal=-1
        for index, obj in enumerate(self.objects):
            if obj.type != TEXT:
                continue
            ordinal+=1
            if pdf.raw.FPDFTextObj_GetTextRenderMode(obj) == 3:
                continue
            info = self.info(index)
            rows = self.character_geometry(index)
            if not rows:
                continue
            a,b,c,d,_,_ = info['matrix']
            size = info['size'] * (c*c+d*d)**.5
            bounds = info['bounds']
            key = (info['font'], round(info['size'],4), info.get('color'), tuple(round(v,5) for v in (a,b,c,d)))
            previous = runs[-1] if runs else None
            # Only horizontal fragments are joined for now. Small negative
            # gaps are intentional kerning; a gutter remains a separate run.
            join = (previous is not None and previous['key']==key
                    and (ordinal-1,ordinal) in joinable
                    and abs(b)<1e-5 and abs(c)<1e-5 and a>0
                    and abs(rows[0]['origin'][1]-previous['baseline']) < max(.15,size*.04)
                    and -.5*size <= bounds[0]-previous['bounds'][2] <= max(.8,size*.65)
                    and bounds[0] >= previous['bounds'][0])
            if join:
                previous['indices'].append(index)
                previous['characters'].extend(rows)
                left,bottom,right,top = previous['bounds']
                previous['bounds']=(min(left,bounds[0]),min(bottom,bounds[1]),max(right,bounds[2]),max(top,bounds[3]))
            else:
                runs.append(dict(indices=[index], characters=rows, bounds=bounds,
                                 baseline=rows[0]['origin'][1], size=size, key=key))
        try:
            from text_layout import block_records,block_geometry
            records=block_records(self._edit_data,self.index)
        except ValueError:records={}
        text_indices=[i for i,o in enumerate(self.objects) if o.type==TEXT]
        for key,record in records.items():
            indices=[text_indices[i] for i in record['ordinals']]
            if not indices:continue
            own=set(indices);runs=[r for r in runs if not own.intersection(r['indices'])]
            chars,end=block_geometry(self,self.textpage,[self.objects[i] for i in text_indices],record)
            boxes=[self.objects[i].get_bounds() for i in indices]
            bounds=(min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))
            info=self.info(indices[0]);scale=(info['matrix'][2]**2+info['matrix'][3]**2)**.5
            bounds=(min(bounds[0],end[0]),min(bounds[1],end[1]),max(bounds[2],end[0]+info['size']*scale*.4),max(bounds[3],end[1]+info['size']*scale*.8))
            box=tuple(map(float,record['meta']['/Box'])) if '/Box' in record['meta'] else None
            if box:bounds=(min(bounds[0],box[0]),min(bounds[1],box[1]),max(bounds[2],box[2]),max(bounds[3],box[3]))
            runs.append(dict(indices=indices,characters=chars,bounds=bounds,baseline=info['matrix'][5],size=info['size']*scale,key=('Faro',key),layout=key,text=str(record['meta']['/Text']),end_origin=end,matrix=tuple(map(float,record['meta']['/Matrix'])),box_bounds=box,owned=record.get('owned',False)))
        self._text_runs = runs
        return runs

    def text_run(self, index):
        return next((r for r in self.text_runs() if index in r['indices']), None)

    def text_blocks(self):
        """Visual paragraph outlines; individual lines retain fixed baselines."""
        if self._text_blocks is not None: return self._text_blocks
        blocks=[]
        for run in self.text_runs():
            l,b,r,t=run['bounds']; target=None
            for block in reversed(blocks):
                previous=block['runs'][-1]
                dy=previous['baseline']-run['baseline']
                pl,pb,pr,pt=previous['bounds']
                if (run['key']==previous['key'] and run['size']*.6<=dy<=run['size']*1.55
                        and (abs(l-pl)<=max(.8,run['size']*.55) or abs(r-pr)<=max(.8,run['size']*.55))
                        and min(r,pr)>max(l,pl)):
                    target=block; break
            if target is None:
                blocks.append(dict(bounds=run['bounds'],runs=[run]))
            else:
                bl,bb,br,bt=target['bounds']
                target['bounds']=(min(l,bl),min(b,bb),max(r,br),max(t,bt))
                target['runs'].append(run)
        self._text_blocks=blocks
        return blocks

    def native_run_bytes(self, indices, expected, value):
        from content_patch import patch_native_run
        ordinals=[sum(o.type==TEXT for o in self.objects[:i]) for i in indices]
        from font_extension import extend_for_text
        staged=extend_for_text(self._edit_data,self.index,ordinals[0],value)
        return patch_native_run(staged,self.index,ordinals,expected,value)

    def apply_native_run(self, indices, expected, value):
        after=self.native_run_bytes(indices,expected,value)
        return self._apply_native_bytes(indices,after)

    def raster_crop(self, index, scale=3):
        bounds = self.objects[index].get_bounds()
        bitmap = self.page.render(scale=scale)
        try:
            points = []
            for x in (bounds[0], bounds[2]):
                for y in (bounds[1], bounds[3]):
                    sx, sy = C.c_int(), C.c_int()
                    pdf.raw.FPDF_PageToDevice(self.page, 0, 0, bitmap.width, bitmap.height, 0, x, y, C.byref(sx), C.byref(sy))
                    points.append((sx.value, sy.value))
            xs, ys = zip(*points)
            return bitmap.to_pil().crop((min(xs), min(ys), max(xs), max(ys))).convert('RGB').copy()
        finally:
            bitmap.close()

    def preserve_font_missing(self, index, value):
        from typography import embedded_coverage
        info = self.info(index)
        data = self.font_data(index)
        chars = embedded_coverage(data) if data else None
        if chars is not None:
            return sorted({c for c in value if not c.isspace() and ord(c) not in chars and c not in info['text']})
        if info['subset']:
            return sorted(set(value)-set(info['text'])-set(' \n\r\t'))
        if info['font'] in pdf.PdfFont.STANDARD_FONTS:
            return sorted({c for c in value if not c.isspace() and not _encodable(c)})
        return []

    def _new_font_object(self, value, size, face_path, color):
        from typography import read_face, missing_characters
        face = read_face(str(face_path))
        if face.restricted:
            raise ValueError('Esta fuente no permite su incrustación. Elige otra fuente.')
        missing = missing_characters(face.path, value)
        if missing:
            raise ValueError('La fuente no incluye estos caracteres: '+''.join(missing))
        data = Path(face.path).read_bytes()
        buffer = (C.c_ubyte * len(data)).from_buffer_copy(data)
        raw_font = pdf.raw.FPDFText_LoadFont(self.doc, buffer, len(data), pdf.raw.FPDF_FONT_TRUETYPE, True)
        if not raw_font:
            raise ValueError('No se pudo cargar la fuente TrueType seleccionada.')
        font = pdf.PdfFont(raw_font, parent=self.doc, needs_free=True)
        self.doc._add_kid(font)
        raw = pdf.raw.FPDFPageObj_CreateTextObj(self.doc, font, size)
        if not raw:
            raise ValueError('No se pudo crear el objeto de texto con esta fuente.')
        obj = pdf.PdfObject(raw, pdf=self.doc)
        if not pdf.raw.FPDFText_SetText(obj, wide(value)):
            obj.close()
            raise ValueError('No se pudo codificar el texto.')
        pdf.raw.FPDFPageObj_SetFillColor(obj, *color, 255)
        return obj

    def apply_inline(self, index, value, size, face_path=None, color=None, ink_top=None, ink_left=None):
        info = self.info(index)
        if info['type'] != TEXT:
            raise ValueError('Este objeto es una imagen. La conversión a texto está bloqueada para evitar sustituir su tipografía por una aproximación.')
        if face_path is None and value == info['text'] and abs(size-info['size']) < .01:
            return
        if info['type'] == TEXT and not face_path:
            if '\n' in value:
                raise ValueError('Este objeto es una línea de texto. Para añadir líneas elige una fuente instalada.')
            after = self.native_text_bytes(index, value, size)
            return self._apply_native_bytes(index, after)
        if not value.strip():
            return self.delete(index)
        if not face_path:
            raise ValueError('Elige una fuente para convertir el texto de la imagen.')

        def operation():
            old = self.objects[index]
            if self.textpage:
                self.textpage.close()
                self.textpage = None
            self.page.remove_obj(old)
            old.close()
            for line_index, line in enumerate(value.splitlines()):
                if not line:
                    continue
                new = self._new_font_object(line, size, face_path, color or info.get('color', (13, 43, 49)))
                if info['type'] == TEXT:
                    a, b, c, d, e, f = info['matrix']
                    matrix = pdf.PdfMatrix(a, b, c, d, e-c*size*1.3*line_index, f-d*size*1.3*line_index)
                else:
                    top = ink_top if ink_top is not None else info['bounds'][3]
                    from PIL import ImageFont
                    glyph_top = ImageFont.truetype(face_path, 100).getbbox(line)[1]/100*size
                    ascent = ImageFont.truetype(face_path, 100).getmetrics()[0]/100*size
                    baseline = top-(ascent-glyph_top)-size*1.3*line_index
                    matrix = pdf.PdfMatrix(1, 0, 0, 1, ink_left if ink_left is not None else info['bounds'][0], baseline)
                new.set_matrix(matrix)
                if not pdf.raw.FPDFPage_InsertObjectAtIndex(self.page, new, index+line_index):
                    new.close()
                    raise ValueError('No se pudo colocar el texto en su posición original.')
                new._detach_finalizer()
                new.page, new.pdf = self.page, self.doc
        self._change('Editar texto en la página', operation, value.splitlines()[0])

    def native_text_bytes(self, index, value, size=None):
        """Stage an operand edit using the original PDF font and content state."""
        from content_patch import patch_native
        info = self.info(index)
        if info['type'] != TEXT:
            raise ValueError('La edición nativa requiere un objeto de texto original.')
        if size is not None and abs(size-info['size']) >= .01:
            raise ValueError('El cambio de tamaño todavía no está validado en la edición que conserva el contenido. Mantén el tamaño original.')
        ordinal = sum(obj.type == TEXT for obj in self.objects[:index])
        from font_extension import extend_for_text
        staged=extend_for_text(self._edit_data,self.index,ordinal,value)
        return patch_native(staged, self.index, ordinal, info['text'], value)

    def layout_text_bytes(self,indices,value,size,face=None,color=None,block_id=None,box=None):
        from text_layout import replace_block
        info=self.info(indices[0]);run=self.text_run(indices[0])
        expected=run.get('text') if run and run.get('layout') else ''.join(r['character'] for i in indices for r in self.character_geometry(i))
        if len(indices)==1 and not (run and run.get('layout')):expected=info['text']
        matrix=run.get('matrix',info['matrix']) if run else info['matrix']
        ordinals=[sum(o.type==TEXT for o in self.objects[:i]) for i in indices]
        return replace_block(self._edit_data,self.index,ordinals,expected,value,size,matrix,color or info.get('color',(0,0,0)),face,block_id,box)

    def apply_text_layout(self,indices,value,size,face=None,color=None,block_id=None,box=None):
        from text_layout import block_records
        data,key=self.layout_text_bytes(indices,value,size,face,color,block_id,box)
        record=block_records(data,self.index).get(key)
        self._apply_native_bytes(indices,data,record['ordinals'] if record else [])
        return key

    def _apply_native_bytes(self, index, after, new_ordinals=None):
        """Reject collateral visual changes before installing a native patch."""
        if after==self._data: return
        import numpy as np
        before = self._data
        indices = index if isinstance(index,list) else [index]
        old_bounds = [self.objects[i].get_bounds() for i in indices]
        ordinals = [sum(obj.type == TEXT for obj in self.objects[:i]) for i in indices]
        candidate = pdf.PdfDocument(after)
        candidate_page = candidate[self.index]
        try:
            text_objects = [o for o in candidate_page.get_objects(max_depth=0) if o.type == TEXT]
            # Empty fragments disappear from PDFium's object list. Only the
            # selected run may change; gather its surviving objects by count.
            removed = len([o for o in self.objects if o.type==TEXT])-len(text_objects)
            count = max(0,len(indices)-removed)
            selected=[text_objects[i] for i in new_ordinals] if new_ordinals is not None else text_objects[ordinals[0]:ordinals[0]+count]
            new_bounds = [o.get_bounds() for o in selected]
            bitmaps = [self.page.render(scale=2), candidate_page.render(scale=2)]
            try:
                images = [np.asarray(b.to_pil().convert('RGB')).copy() for b in bitmaps]
                if images[0].shape != images[1].shape:
                    raise ValueError('La prueba de conservación detectó un cambio de tamaño de página.')
                changed = np.any(images[0] != images[1], axis=2)
                points = []
                for bounds in old_bounds+new_bounds:
                    for x in (bounds[0]-2, bounds[2]+2):
                        for y in (bounds[1]-2, bounds[3]+2):
                            sx, sy = C.c_int(), C.c_int()
                            pdf.raw.FPDF_PageToDevice(self.page, 0, 0, bitmaps[0].width, bitmaps[0].height, 0, x, y, C.byref(sx), C.byref(sy))
                            points.append((sx.value, sy.value))
                xs, ys = zip(*points)
                changed[max(0,min(ys)):max(0,max(ys)+1), max(0,min(xs)):max(0,max(xs)+1)] = False
                if changed.any():
                    raise ValueError('Se bloqueó el cambio porque alteraba contenido fuera del texto seleccionado. El documento conserva el estado anterior.')
            finally:
                for bitmap in bitmaps:
                    bitmap.close()
        finally:
            candidate_page.close()
            candidate.close()
        try:
            self._load(after)
        except Exception:
            self._load(before)
            raise
        self.undo_stack.append(('Editar texto conservando la fuente', before, self.current_version))
        self.undo_stack = self.undo_stack[-30:]
        self.current_version = self.next_version
        self.next_version += 1
        self.redo_stack.clear()

    def _change(self, label, operation, expected=None):
        before = self.bytes()
        try:
            # PDFium's content generator cannot serialize every named color
            # space. Resolve solid path/text colors before regenerating so
            # ICC/named grayscale backgrounds do not silently become black.
            for obj in self.objects:
                if obj.type not in (TEXT, pdf.raw.FPDF_PAGEOBJ_PATH):
                    continue
                for getter, setter in (
                    (pdf.raw.FPDFPageObj_GetFillColor, pdf.raw.FPDFPageObj_SetFillColor),
                    (pdf.raw.FPDFPageObj_GetStrokeColor, pdf.raw.FPDFPageObj_SetStrokeColor),
                ):
                    values = [C.c_uint() for _ in range(4)]
                    if getter(obj, *[C.byref(v) for v in values]):
                        if not setter(obj, *[v.value for v in values]):
                            raise ValueError('No se pudo conservar un color del documento.')
            operation()
            self.page.gen_content()
            after = self.bytes()
            self._load(after)
            if expected is not None and comparable_text(expected) not in comparable_text(self.textpage.get_text_range()):
                raise ValueError('La fuente no pudo representar ese texto. Prueba reemplazarlo con una fuente de la lista.')
        except Exception:
            self._load(before)
            raise
        self.undo_stack.append((label, before, self.current_version))
        self.undo_stack = self.undo_stack[-30:]
        while len(self.undo_stack) > 1 and sum(len(entry[1]) for entry in self.undo_stack) > 128 * 1024 * 1024:
            self.undo_stack.pop(0)
        self.current_version = self.next_version
        self.next_version += 1
        self.redo_stack.clear()

    def undo(self):
        if self.undo_stack:
            label, data, version = self.undo_stack.pop()
            self.redo_stack.append((label, self._data, self.current_version))
            self._load(data)
            self.current_version = version

    def redo(self):
        if self.redo_stack:
            label, data, version = self.redo_stack.pop()
            self.undo_stack.append((label, self._data, self.current_version))
            self._load(data)
            self.current_version = version

    def move(self, index, dx, dy):
        if self.objects[index].type==IMAGE:
            return self.transform_image(index,(1,0,0,1,dx,dy))
        def operation():
            self.objects[index].transform(pdf.PdfMatrix(1, 0, 0, 1, dx, dy))
        self._change('Mover objeto', operation)

    def delete(self, index):
        if self.objects[index].type==IMAGE:return self.transform_image(index,None)
        if self.objects[index].type==TEXT:
            run=self.text_run(index)
            if run and run.get('owned'):
                return self.apply_text_layout(run['indices'],'',run['size'],box=run.get('box_bounds'))
        def operation():
            obj = self.objects[index]
            if obj.type == TEXT:
                self.textpage.close()
                self.textpage = None
            self.page.remove_obj(obj)
            obj.close()
        self._change('Borrar objeto', operation)

    def resize_image(self,index,bounds):
        l,b,r,t=self.objects[index].get_bounds();nl,nb,nr,nt=bounds
        if min(r-l,t-b)<1e-7:raise ValueError('La imagen no tiene dimensiones válidas. Deshaz el último cambio.')
        if min(nr-nl,nt-nb)<1:raise ValueError('La imagen debe medir al menos un punto.')
        sx=(nr-nl)/(r-l);sy=(nt-nb)/(t-b)
        return self.transform_image(index,(sx,0,0,sy,nl-sx*l,nb-sy*b))

    def transform_image(self,index,matrix):
        from insertions import transform_image
        import numpy as np
        obj=self.objects[index];old=obj.get_bounds()
        ordinal=sum(o.type==IMAGE for o in self.objects[:index])
        after=transform_image(self._edit_data,self.index,ordinal,obj.get_matrix().get(),matrix)
        candidate=pdf.PdfDocument(after);page=candidate[self.index]
        candidate_images=[o for o in page.get_objects(max_depth=0) if o.type==IMAGE]
        original_count=sum(o.type==IMAGE for o in self.objects)
        if len(candidate_images)!=original_count-(matrix is None):
            page.close();candidate.close();raise ValueError('No se conservó la estructura de imágenes.')
        if matrix:
            from insertions import compose
            expected=compose(matrix,obj.get_matrix().get())
            actual=candidate_images[ordinal].get_matrix().get()
            if any(abs(a-b)>max(.001,abs(b)*1e-5) for a,b in zip(actual,expected)):
                page.close();candidate.close();raise ValueError('La transformación guardada no coincide con el movimiento solicitado.')
        bitmaps=[self.page.render(scale=2),page.render(scale=2)]
        try:
            images=[np.asarray(bitmap.to_pil().convert('RGB')).copy() for bitmap in bitmaps]
            changed=np.any(images[0]!=images[1],axis=2)
            boxes=[old]
            if matrix:
                a,b,c,d,e,f=matrix
                points=[(a*x+c*y+e,b*x+d*y+f) for x in (old[0],old[2]) for y in (old[1],old[3])]
                xs,ys=zip(*points);boxes.append((min(xs),min(ys),max(xs),max(ys)))
            for l,b,r,t in boxes:
                points=[]
                for x in (l-2,r+2):
                    for y in (b-2,t+2):
                        sx,sy=C.c_int(),C.c_int()
                        pdf.raw.FPDF_PageToDevice(self.page,0,0,bitmaps[0].width,bitmaps[0].height,0,x,y,C.byref(sx),C.byref(sy));points.append((sx.value,sy.value))
                xs,ys=zip(*points)
                changed[max(0,min(ys)):max(0,max(ys)+1),max(0,min(xs)):max(0,max(xs)+1)]=False
            if changed.any():raise ValueError('Se bloqueó el cambio porque alteraba contenido fuera de la imagen.')
        finally:
            for bitmap in bitmaps:bitmap.close()
            page.close();candidate.close()
        self.install_bytes('Modificar imagen',after)

    def move_page(self,source,destination):
        from insertions import rearrange_pages
        if not (0<=source<len(self.doc) and 0<=destination<len(self.doc)):raise ValueError('Página inválida.')
        if source==destination:return
        self.install_bytes('Mover página',rearrange_pages(self._data,source,destination))
        self.set_page(destination)

    def move_text(self,indices,dx,dy):
        from text_layout import move_text
        ordinals=[sum(o.type==TEXT for o in self.objects[:i]) for i in indices]
        data=move_text(self._edit_data,self.index,ordinals,dx,dy)
        self._apply_native_bytes(indices,data,new_ordinals=ordinals)

    def delete_page(self,index):
        from insertions import rearrange_pages
        self.install_bytes('Borrar página',rearrange_pages(self._data,index))
        self.set_page(min(index,len(self.doc)-1))

    def edit_text(self, index, value, size=None):
        if not value.strip():
            raise ValueError('Escribe un texto o utiliza Borrar para eliminar el objeto.')
        if self.objects[index].type != TEXT:
            raise ValueError('Este objeto contiene píxeles. Usa Reemplazar por texto.')
        def operation():
            if not pdf.raw.FPDFText_SetText(self.objects[index], wide(value)):
                raise ValueError('No se pudo editar el texto con su fuente original.')
            if size is not None and not pdf.raw.FPDFTextObj_SetFontSize(self.objects[index], size):
                raise ValueError('No se pudo cambiar el tamaño de fuente.')
        self._change('Editar texto', operation, value)

    def _insert_text(self, value, x, top, size, font, color):
        for row, line in enumerate(value.splitlines()):
            if not line:
                continue
            raw = pdf.raw.FPDFPageObj_NewTextObj(self.doc, font.encode('ascii'), size)
            if not raw:
                raise ValueError('No se pudo crear el texto.')
            obj = pdf.PdfObject(raw, pdf=self.doc)
            if not pdf.raw.FPDFText_SetText(obj, wide(line)):
                obj.close()
                raise ValueError('La fuente seleccionada no admite el texto.')
            pdf.raw.FPDFPageObj_SetFillColor(obj, *color, 255)
            obj.set_matrix(pdf.PdfMatrix(1, 0, 0, 1, x, top - size * .85 - row * size * 1.3))
            self.page.insert_obj(obj)

    def replace_with_text(self, index, value, size=12, font='Helvetica', color=(13, 43, 49)):
        if self.objects[index].type != TEXT:
            raise ValueError('La conversión de imagen a texto está bloqueada para conservar la tipografía original visible.')
        if not value.strip():
            raise ValueError('Escribe el texto que sustituirá al objeto seleccionado.')
        bounds = self.objects[index].get_bounds()
        def operation():
            obj = self.objects[index]
            if obj.type == TEXT:
                self.textpage.close()
                self.textpage = None
            self.page.remove_obj(obj)
            obj.close()
            self._insert_text(value, bounds[0], bounds[3], size, font, color)
        self._change('Reemplazar por texto', operation, value.splitlines()[0])

    def add_text(self, value, x, top, size=12, font='Helvetica', color=(13, 43, 49), face=None, box=None):
        if not value.strip():
            raise ValueError('Escribe un texto.')
        from owned_text import add
        from text_layout import block_records
        data,key=add(self._edit_data,self.index,value,x,top,size,font,color,face,box)
        record=block_records(data,self.index)[key]
        self._apply_native_bytes([],data,new_ordinals=record['ordinals'])
        self.undo_stack[-1]=('Añadir texto',self.undo_stack[-1][1],self.undo_stack[-1][2])

    def install_bytes(self,label,data):
        before=self._data
        try:self._load(data)
        except Exception:
            self._load(before);raise
        self.undo_stack.append((label,before,self.current_version))
        self.current_version=self.next_version;self.next_version+=1;self.redo_stack.clear()

    def add_image(self,path,x,top,width):
        from insertions import add_image
        self.install_bytes('Insertar imagen',add_image(self._data,self.index,path,x,top,width))

    def insert_pdfs(self,paths,position):
        from insertions import insert_pdfs
        if not 0<=position<=len(self.doc):raise ValueError('La posición de inserción no es válida.')
        self.install_bytes('Insertar páginas PDF',insert_pdfs(self._data,paths,position))

    def save(self, path):
        target = Path(path).resolve()
        data = self._data
        # Validate the serialized document before replacing any destination.
        check = pdf.PdfDocument(data)
        try:
            if len(check) != len(self.doc):
                raise ValueError('El documento guardado no conserva sus páginas.')
            for i in range(len(check)):
                page = check[i]
                page.close()
        finally:
            check.close()
        fd, temporary = tempfile.mkstemp(prefix='.faro-', suffix='.pdf', dir=target.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self.saved_path = target
        self.saved_version = self.current_version
