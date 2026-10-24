"""OCR dialog and cancellable child process; PDFium stays outside the GUI process."""
import json
from pathlib import Path
import sys
import tempfile

from PySide6.QtCore import QObject, QProcess, Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QFormLayout, QComboBox,
                               QLineEdit, QDialogButtonBox, QProgressDialog)
from ocr_engine import page_range, runtime_path


class OCRController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.process = None
        self.temporary = None
        self.progress = None
        self.cancelled = False
        self.last_summary = None
        self.buffer = b''
        self.terminal = None

    @property
    def busy(self):
        return self.process is not None

    def show(self):
        window = self.window
        if self.busy or not window.model: return
        if window.inline.active and not window.inline.commit(): return
        dialog = QDialog(window); dialog.setWindowTitle('Reconocer texto (OCR)')
        dialog.setMinimumWidth(460)
        layout = QVBoxLayout(dialog)
        text = QLabel('Convierte escaneos en texto buscable y seleccionable.\n'
                      'Se conserva la imagen original. Todo se procesa en tu equipo.')
        text.setWordWrap(True); layout.addWidget(text)
        form = QFormLayout(); layout.addLayout(form)
        scope = QComboBox(); scope.addItems(['Todo el documento', 'Página actual', 'Rango de páginas'])
        scope.setCurrentIndex(1)
        ranges = QLineEdit(); ranges.setPlaceholderText('Ejemplo: 1-3, 5'); ranges.setEnabled(False)
        scope.currentIndexChanged.connect(lambda i: ranges.setEnabled(i == 2))
        language = QComboBox()
        for title, code in [('Español e inglés', 'spa+eng'), ('Español', 'spa'), ('Inglés', 'eng')]:
            language.addItem(title, code)
        form.addRow('Reconocer', scope); form.addRow('Páginas', ranges); form.addRow('Idioma', language)
        note = QLabel('Las páginas que ya tienen texto se omiten para evitar duplicados.\n'
                      'Revisa los datos reconocidos, especialmente nombres y cantidades.\n'
                      'El OCR permite buscar y copiar; no reconstruye la fuente original.')
        note.setWordWrap(True); layout.addWidget(note)
        error = QLabel(); error.setStyleSheet('color:#b3261e'); error.setWordWrap(True); layout.addWidget(error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Reconocer texto')
        layout.addWidget(buttons); buttons.rejected.connect(dialog.reject)
        selected = []
        def accept():
            try:
                model = window.model
                pages = (list(range(len(model.doc))) if scope.currentIndex() == 0 else
                         [model.index] if scope.currentIndex() == 1 else page_range(ranges.text(), len(model.doc)))
                selected[:] = pages; dialog.accept()
            except ValueError as exc: error.setText(str(exc))
        buttons.accepted.connect(accept)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.start(selected, language.currentData())

    def start(self, pages, language='spa+eng'):
        try:
            return self._start(pages, language)
        except Exception as error:
            if self.process is None and self.temporary:
                self.temporary.cleanup(); self.temporary = None
            self.window.error(error)
            return False

    def _start(self, pages, language):
        window = self.window
        if self.busy or not window.model: return False
        if window.inline.active and not window.inline.commit(): return False
        if not (runtime_path() / 'tesseract.exe').is_file():
            window.error('Falta el motor OCR. Instala la versión completa de Faro PDF.'); return False
        self.temporary = tempfile.TemporaryDirectory(prefix='faro-ocr-', ignore_cleanup_errors=True)
        self.work = Path(self.temporary.name)
        self.model = window.model; self.version = self.model.current_version
        (self.work / 'input.pdf').write_bytes(self.model._data)
        job = dict(input=str(self.work / 'input.pdf'), output=str(self.work / 'output.pdf'),
                   work=str(self.work / 'pages'), cancel=str(self.work / 'cancel'),
                   pages=list(pages), language=language)
        job_path = self.work / 'job.json'; job_path.write_text(json.dumps(job), encoding='utf-8')
        self.cancelled = False; self.buffer = b''; self.terminal = None; self.last_summary = None
        self.progress = QProgressDialog('Preparando reconocimiento local…', 'Cancelar', 0, len(pages), window)
        self.progress.setWindowTitle('Reconocer texto (OCR)')
        self.progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress.setMinimumDuration(0); self.progress.setAutoClose(False); self.progress.setAutoReset(False)
        self.progress.canceled.connect(self.cancel)
        process = self.process = QProcess(self)
        process.readyReadStandardOutput.connect(self.read_output)
        # Drain stderr without retaining document content or unbounded logs.
        process.readyReadStandardError.connect(lambda: process.readAllStandardError())
        process.finished.connect(self.finished)
        process.errorOccurred.connect(self.process_error)
        arguments = ['--ocr-worker', str(job_path)]
        if not getattr(sys, 'frozen', False): arguments.insert(0, str(Path(__file__).with_name('app.py')))
        process.setProgram(sys.executable); process.setArguments(arguments); process.start()
        self.progress.show()
        return True

    def read_output(self):
        if not self.process: return
        self.buffer += bytes(self.process.readAllStandardOutput())
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            try: record = json.loads(line)
            except (ValueError, UnicodeError): continue
            if record.get('kind') == 'progress' and self.progress and not self.cancelled:
                self.progress.setLabelText(f'Reconociendo página {record["page"]}…\nLos documentos permanecen en tu equipo.')
                self.progress.setValue(record['done'])
            else: self.terminal = record

    def cancel(self):
        if not self.busy: return
        self.cancelled = True
        (self.work / 'cancel').touch()
        if self.progress:
            self.progress.setLabelText('Cancelando reconocimiento…')
            self.progress.setCancelButton(None)

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.terminal = dict(kind='error', message='No se pudo iniciar el proceso de reconocimiento OCR.')
            self.finished(-1)

    def finished(self, exit_code, *_):
        if self.process is None: return
        self.read_output()
        process = self.process; self.process = None
        process.deleteLater()
        if self.progress:
            self.progress.close(); self.progress.deleteLater(); self.progress = None
        try:
            result = self.terminal or {}
            if self.cancelled or result.get('kind') == 'cancelled':
                self.window.statusBar().showMessage('OCR cancelado. El documento no se ha cambiado.', 12000)
            elif exit_code or result.get('kind') != 'complete':
                self.window.error(result.get('message', 'No se pudo completar el reconocimiento OCR. El documento no se ha cambiado.'))
            elif self.window.model is not self.model or self.model.current_version != self.version:
                self.window.error('El documento cambió durante el OCR. Vuelve a reconocerlo para conservar tus cambios.')
            else:
                self.last_summary = result
                if result['changed']:
                    self.model.install_bytes('Reconocer texto (OCR)', (self.work / 'output.pdf').read_bytes())
                    self.window.set_mode('select'); self.window.render_page()
                self.window.statusBar().showMessage(
                    f'OCR: {len(result["changed"])} páginas reconocidas; '
                    f'{len(result["skipped"])} omitidas con texto; {len(result["empty"])} sin texto detectado. '
                    'Selecciona para copiar y guarda una copia para conservar el resultado.', 30000)
        except Exception as error: self.window.error(error)
        finally:
            self.temporary.cleanup(); self.temporary = None
