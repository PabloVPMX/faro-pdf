"""Non-blocking release checks and installation after normal document closure."""
from pathlib import Path
import sys
import threading
import time

from PySide6.QtCore import QObject, QThread, Signal, QTimer, QSettings, QStandardPaths, QLockFile, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QCheckBox, QPushButton,
                               QHBoxLayout, QProgressBar)

import update_service as service


class UpdateJob(QThread):
    completed = Signal(object)
    failed = Signal(str)
    progress = Signal(int)

    def __init__(self, version, root, download, parent=None, transport=None):
        super().__init__(parent)
        self.version, self.root, self.download = version, root, download
        self.transport = transport
        self.cancel = threading.Event()

    def run(self):
        lock = QLockFile(str(self.root/'download.lock'))
        lock.setStaleLockTime(0)
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            if not lock.tryLock(0):
                raise service.UpdateError('Otra ventana de Faro está comprobando actualizaciones. Inténtalo después.')
            candidate = service.find_update(self.version, self.transport, self.cancel)
            ready = False
            if candidate and self.download:
                service.stage_update(candidate, self.root, self.transport, self.cancel,
                                     lambda done, total: self.progress.emit(int(done*100/total)))
                ready = True
            service.check_cancelled(self.cancel)
            self.completed.emit((candidate, ready))
        except service.UpdateCancelled:
            pass
        except Exception as error:
            self.failed.emit('No se pudo completar la actualización. '+str(error))
        finally:
            if lock.isLocked():
                lock.unlock()


class UpdateController(QObject):
    def __init__(self, window, button, version, enabled=True, settings=None, root=None,
                 installed=None, transport=None):
        super().__init__(window)
        self.window, self.button, self.version = window, button, version
        self.settings = settings or QSettings('FaroPDF', 'Faro PDF')
        self.root = Path(root) if root else Path(QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppLocalDataLocation))/'updates'
        self.installed = (bool(getattr(sys, 'frozen', False)) and service.installed_directory() is not None
                          if installed is None else installed)
        self.transport = transport
        self.worker = None
        self.candidate = service.load_staged(self.root, version)
        self.ready = self.candidate is not None
        self.force_install = False
        self.close_when_idle = False
        self.dialog = None
        self.message = ('Actualización preparada. Se instalará al cerrar Faro.' if self.ready
                        else 'Busca nuevas versiones de Faro PDF en GitHub.')
        self.button.clicked.connect(self.show_dialog)
        self.timer = QTimer(self)
        self.timer.setInterval(60*60*1000)
        self.timer.timeout.connect(self.automatic_check)
        if enabled and getattr(sys, 'frozen', False):
            QTimer.singleShot(8000, self.automatic_check)
            self.timer.start()
        self.refresh()

    def option(self, key, default=True):
        return self.settings.value('updates/'+key, default, type=bool)

    def automatic_check(self):
        if not self.option('auto_check') or self.worker:
            return
        last = self.settings.value('updates/last_check_attempt', 0, type=float)
        if time.time()-last >= 24*60*60:
            self.check()

    def check(self, install=False):
        if self.worker:
            return
        self.force_install = install
        self.message = 'Comprobando versiones…'
        self.settings.setValue('updates/last_check_attempt', time.time())
        download = self.installed and (install or self.option('auto_install'))
        self.worker = UpdateJob(self.version, self.root, download, self, self.transport)
        self.worker.completed.connect(self.completed)
        self.worker.failed.connect(self.failed)
        self.worker.progress.connect(self.download_progress)
        self.worker.finished.connect(self.finished)
        self.refresh()
        self.worker.start()

    def completed(self, result):
        candidate, ready = result
        self.candidate, self.ready = candidate, ready
        if candidate is None:
            self.message = f'Tienes la versión más reciente disponible: {self.version}.'
        elif ready:
            self.message = f'Faro PDF {candidate.version} está listo. Se instalará al cerrar todas las ventanas de Faro.'
        else:
            self.message = f'Hay una nueva versión: Faro PDF {candidate.version}.'
        self.refresh()
        if candidate:
            self.window.statusBar().showMessage(self.message, 15000)

    def failed(self, message):
        self.message = message+' Puedes seguir usando Faro y volver a intentarlo.'
        self.force_install = False
        self.refresh()

    def finished(self):
        job = self.worker
        self.worker = None
        if job:
            job.deleteLater()
        self.refresh()
        if self.close_when_idle or (self.force_install and self.ready):
            self.close_when_idle = False
            QTimer.singleShot(0, self.window.close)

    def download_progress(self, value):
        self.message = f'Descargando actualización… {value} %'
        if self.dialog:
            self.progress.setRange(0, 100)
            self.progress.setValue(value)
            self.status.setText(self.message)

    def show_dialog(self):
        if self.dialog:
            self.dialog.show(); self.dialog.raise_(); self.dialog.activateWindow()
            return
        self.dialog = QDialog(self.window)
        self.dialog.setWindowTitle('Actualizaciones de Faro PDF')
        self.dialog.setMinimumWidth(470)
        layout = QVBoxLayout(self.dialog)
        layout.addWidget(QLabel(f'Faro PDF · Versión instalada {self.version}'))
        self.status = QLabel(); self.status.setWordWrap(True)
        self.status.setMinimumHeight(55); layout.addWidget(self.status)
        self.progress = QProgressBar(); layout.addWidget(self.progress)
        self.auto_check = QCheckBox('Buscar actualizaciones automáticamente cada día')
        self.auto_install = QCheckBox('Descargar e instalar automáticamente al cerrar Faro')
        self.auto_check.setChecked(self.option('auto_check'))
        self.auto_install.setChecked(self.option('auto_install') and self.installed)
        self.auto_install.setEnabled(self.installed)
        layout.addWidget(self.auto_check); layout.addWidget(self.auto_install)
        self.auto_check.toggled.connect(self.change_check)
        self.auto_install.toggled.connect(self.change_install)
        note = QLabel('Las actualizaciones consultan GitHub. Tus documentos permanecen en tu equipo.'
                      if self.installed else
                      'La edición portátil se actualiza descargando y extrayendo la carpeta completa desde GitHub.')
        note.setWordWrap(True); layout.addWidget(note)
        row = QHBoxLayout()
        self.search = QPushButton('Buscar ahora'); self.search.clicked.connect(lambda: self.check())
        self.install = QPushButton(); self.install.clicked.connect(self.install_now)
        notes = QPushButton('Ver versiones'); notes.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(service.HOME+'/releases')))
        row.addWidget(self.search); row.addWidget(self.install); row.addWidget(notes)
        layout.addLayout(row)
        close = QPushButton('Cerrar'); close.clicked.connect(self.dialog.close); layout.addWidget(close)
        self.dialog.finished.connect(self.dialog_closed)
        self.refresh(); self.dialog.show()
        if not self.ready:
            self.check()

    def dialog_closed(self):
        dialog = self.dialog
        self.dialog = None
        dialog.deleteLater()

    def change_check(self, checked):
        self.settings.setValue('updates/auto_check', checked)
        if not checked:
            self.auto_install.setChecked(False)

    def change_install(self, checked):
        self.settings.setValue('updates/auto_install', checked)
        if checked:
            self.auto_check.setChecked(True)

    def refresh(self):
        self.button.setText('Actualizar' if not self.candidate else 'Actualización disponible')
        self.button.setToolTip(self.message)
        if not self.dialog:
            return
        self.status.setText(self.message)
        self.search.setEnabled(self.worker is None)
        self.install.setVisible(self.candidate is not None)
        self.install.setEnabled(self.worker is None)
        self.install.setText('Actualizar ahora' if self.ready else
                             ('Descargar e instalar' if self.installed else 'Descargar en GitHub'))
        self.progress.setVisible(self.worker is not None)
        if self.worker:
            self.progress.setRange(0, 0)

    def install_now(self):
        if not self.installed:
            QDesktopServices.openUrl(QUrl(self.candidate.notes_url))
        elif self.ready:
            self.force_install = True
            self.window.close()
        else:
            self.check(install=True)

    def wait_before_close(self):
        if self.worker:
            self.close_when_idle = True
            self.worker.cancel.set()
            self.message = 'Terminando la comprobación para cerrar Faro…'
            self.refresh()
            return True
        return False

    def cancelled_close(self):
        self.force_install = False
        self.close_when_idle=False

    def before_close(self):
        if not self.ready or not self.installed or not (self.force_install or self.option('auto_install')):
            return True
        try:
            if not service.launch_installer(self.candidate, self.root, reopen=self.force_install):
                if self.force_install:
                    self.message = 'Cierra las otras ventanas de Faro y pulsa Actualizar ahora. Tus cambios siguen abiertos.'
                    self.force_install = False
                    self.show_dialog(); self.refresh()
                    return False
                return True
        except Exception as error:
            self.message = 'No se pudo iniciar el instalador: '+str(error)
            if self.force_install:
                self.force_install = False
                self.show_dialog(); self.refresh()
                return False
        return True
