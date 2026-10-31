"""Local OCR in a separate process; retain every original page and image."""
from pathlib import Path
import io
import json
import math
import os
import re
import subprocess
import sys
import time


class OCRCancelled(Exception):
    pass


def runtime_path():
    root = Path(__file__).resolve().parent
    return root / 'ocr' if getattr(sys, 'frozen', False) else root / '.cache' / 'ocr-runtime'


def page_range(value, count):
    pages = set()
    try:
        for part in value.replace(' ', '').split(','):
            ends = part.split('-')
            if len(ends) == 1: first = last = int(ends[0])
            elif len(ends) == 2: first, last = map(int, ends)
            else: raise ValueError()
            if not 1 <= first <= last <= count: raise ValueError()
            pages.update(range(first - 1, last))
    except (ValueError, TypeError):
        raise ValueError(f'Indica páginas entre 1 y {count}; por ejemplo: 1-3, 5.') from None
    return sorted(pages)


def emit(**value):
    print(json.dumps(value, ensure_ascii=True), flush=True)


def check_cancel(cancel):
    if cancel and Path(cancel).exists(): raise OCRCancelled()


def tesseract(image, output, language, dpi, cancel, runtime):
    env = os.environ.copy()
    env['OMP_THREAD_LIMIT'] = '2'
    # CLI dependencies stay beside the executable, isolated from Qt and PATH tools.
    env['PATH'] = str(runtime) + os.pathsep + str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32')
    command = [str(runtime / 'tesseract.exe'), str(image), str(output),
               '--tessdata-dir', str(runtime / 'tessdata'), '-l', language,
               '--dpi', str(dpi), '--oem', '1', '-c', 'textonly_pdf=1', 'pdf']
    with open(output.with_suffix('.log'), 'wb') as log:
        process = subprocess.Popen(command, stdout=log, stderr=log, env=env,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            deadline = time.monotonic() + 180
            while process.poll() is None:
                check_cancel(cancel)
                if time.monotonic() > deadline:
                    raise ValueError('Esta página superó el tiempo de reconocimiento. Prueba un rango menor.')
                time.sleep(.08)
            if process.returncode:
                raise ValueError('No se pudo reconocer esta página. Comprueba que el motor OCR y sus idiomas estén completos.')
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait()


def overlay_matrix(page, overlay):
    left, bottom, right, top = map(float, page.cropbox)
    width, height = right-left, top-bottom
    ow, oh = float(overlay.mediabox.width), float(overlay.mediabox.height)
    rotation = page.rotation % 360
    if rotation == 0: return width/ow, 0, 0, height/oh, left, bottom
    if rotation == 90: return 0, height/ow, -width/oh, 0, right, bottom
    if rotation == 180: return -width/ow, 0, 0, -height/oh, right, top
    if rotation == 270: return 0, -height/ow, width/oh, 0, left, top
    raise ValueError('La rotación de esta página no es compatible con OCR.')


def compact_unicode_maps(overlay, operations):
    """Keep Tesseract's exact identity mapping only for codes actually emitted.

    Its full 65,536-code CMap needlessly slows down PDF text editors/parsers.
    This changes only the generated hidden layer, never an original font.
    """
    fonts = overlay['/Resources'].get('/Font', {}).get_object()
    used = {}; current = None
    for operands, operator in operations:
        if operator == b'Tf': current = str(operands[0])
        if operator not in (b'Tj', b'TJ', b"'", b'"'): continue
        values = operands[0] if operator == b'TJ' else [operands[-1]]
        for value in values:
            if isinstance(value, (str, bytes)):
                data = value.original_bytes if hasattr(value, 'original_bytes') else bytes(value)
                if len(data) % 2: raise ValueError('El motor produjo una codificación OCR inesperada.')
                used.setdefault(current, set()).update(int.from_bytes(data[i:i+2], 'big') for i in range(0,len(data),2))
    pattern = rb'1\s+beginbfrange\s*<0000>\s*<FFFF>\s*<0000>\s*endbfrange'
    for name, codes in used.items():
        stream = fonts[name].get_object()['/ToUnicode'].get_object()
        original = stream.get_data()
        if not re.search(pattern, original): continue
        codes = sorted(codes); chunks = []
        for start in range(0,len(codes),100):
            part = codes[start:start+100]
            chunks.append(str(len(part)) + ' beginbfchar\n' +
                          '\n'.join(f'<{c:04X}> <{c:04X}>' for c in part) + '\nendbfchar')
        stream.set_data(re.sub(pattern, '\n'.join(chunks).encode('ascii'), original))


def recognize(data, pages, language, work, cancel=None, progress=None, runtime=None):
    """Return new bytes atomically; cancellation/failure never changes the input."""
    import pypdfium2 as pdf
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ContentStream, NameObject, BooleanObject
    runtime = Path(runtime or runtime_path())
    if language not in ('spa', 'eng', 'spa+eng'): raise ValueError('Idioma OCR no disponible.')
    if not (runtime / 'tesseract.exe').is_file():
        raise ValueError('Falta el motor OCR. Reinstala la versión completa de Faro PDF.')
    for lang in language.split('+'):
        if not (runtime / 'tessdata' / (lang + '.traineddata')).is_file():
            raise ValueError('Falta el idioma OCR seleccionado. Reinstala Faro PDF.')
    source = pdf.PdfDocument(data)
    writer = PdfWriter()
    writer.clone_document_from_reader(PdfReader(io.BytesIO(data)))
    pages = sorted(set(pages))
    if not pages or any(not isinstance(p, int) or not 0 <= p < len(source) for p in pages):
        source.close(); raise ValueError('El rango de páginas no es válido.')
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    changed, skipped, empty = [], [], []
    try:
        for done, index in enumerate(pages):
            check_cancel(cancel)
            if progress: progress(done=done, total=len(pages), page=index+1)
            page = source[index]
            try:
                text = page.get_textpage()
                try: existing = text.get_text_bounded().strip()
                finally: text.close()
                if existing:
                    skipped.append(index); continue
                width, height = page.get_size()
                scale = min(300/72, math.sqrt(20_000_000 / max(1, width*height)))
                image = work / 'page.png'; output = work / 'recognized'
                output.with_suffix('.pdf').unlink(missing_ok=True)
                bitmap = page.render(scale=scale, draw_annots=False)
                try: bitmap.to_pil().save(image)
                finally: bitmap.close()
                tesseract(image, output, language, max(70, round(scale*72)), cancel, runtime)
                check_cancel(cancel)
                layer = PdfReader(output.with_suffix('.pdf'))
                overlay = layer.pages[0]
                # Accept only invisible OCR text, never a replacement page image.
                operations = ContentStream(overlay.get_contents(), layer).operations
                mode = 0
                for operands, operator in operations:
                    if operator == b'Tr': mode = int(operands[0])
                    if operator in (b'Tj', b'TJ', b"'", b'"') and mode != 3:
                        raise ValueError('El motor OCR produjo texto visible; se ha descartado el resultado.')
                    if operator in (b'Do', b'INLINE IMAGE', b'S', b's', b'f', b'F', b'f*', b'B', b'B*', b'b', b'b*'):
                        raise ValueError('La capa OCR contiene elementos visibles; se ha descartado el resultado.')
                recognized = pdf.PdfDocument(output.with_suffix('.pdf'))
                recognized_page = recognized[0]; recognized_text = recognized_page.get_textpage()
                try: has_text = bool(recognized_text.get_text_bounded().strip())
                finally: recognized_text.close(); recognized_page.close(); recognized.close()
                if not has_text:
                    empty.append(index); continue
                compact_unicode_maps(overlay, operations)
                target = writer.pages[index]
                target.merge_transformed_page(overlay, overlay_matrix(target, overlay), over=True, expand=False)
                target[NameObject('/FaroOCR')] = BooleanObject(True)
                changed.append(index)
            finally: page.close()
        check_cancel(cancel)
        if not changed: return data, dict(changed=changed, skipped=skipped, empty=empty)
        output = io.BytesIO(); writer.write(output); result = output.getvalue()
        check = pdf.PdfDocument(result)
        try:
            if len(check) != len(source): raise ValueError('El OCR cambió el número de páginas.')
            for index in changed:
                check_cancel(cancel)
                old, new = source[index], check[index]
                try:
                    if old.get_size() != new.get_size(): raise ValueError('El OCR cambió el tamaño de una página.')
                    w, h = old.get_size(); scale = min(1.5, math.sqrt(2_000_000 / max(1,w*h)))
                    before, after = old.render(scale=scale), new.render(scale=scale)
                    try:
                        if before.to_pil().tobytes() != after.to_pil().tobytes():
                            raise ValueError('El OCR cambió la apariencia de la página. El resultado se ha descartado.')
                    finally: before.close(); after.close()
                finally: old.close(); new.close()
        finally: check.close()
        return result, dict(changed=changed, skipped=skipped, empty=empty)
    finally: source.close()


def worker_main(job_path):
    try:
        job = json.loads(Path(job_path).read_text(encoding='utf-8'))
        check_cancel(job['cancel'])
        if job.get('start'):
            # Heavy imports happen before the ready/start handshake. The GUI
            # can safely kill a cancelled startup: no child can exist yet.
            import pypdfium2
            import pypdf
            check_cancel(job['cancel'])
            emit(kind='ready')
            while not Path(job['start']).exists():
                check_cancel(job['cancel']);time.sleep(.02)
        check_cancel(job['cancel'])
        data, summary = recognize(Path(job['input']).read_bytes(), job['pages'], job['language'],
                                  job['work'], job['cancel'], progress=lambda **p: emit(kind='progress', **p))
        check_cancel(job['cancel'])
        Path(job['output']).write_bytes(data)
        emit(kind='complete', **summary)
        return 0
    except OCRCancelled:
        emit(kind='cancelled'); return 2
    except Exception as error:
        emit(kind='error', message=str(error)); return 1
