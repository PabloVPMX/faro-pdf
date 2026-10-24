# Ejecutar y compilar Faro PDF

## Requisitos

- Windows 10/11 x64.
- Python 3.12 x64.
- Git, si quieres clonar el repositorio.

```powershell
git clone https://github.com/PabloVPMX/faro-pdf.git
cd faro-pdf
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt
.\.venv\Scripts\python.exe packaging\prepare_ocr.py
.\.venv\Scripts\python.exe app.py
```

Para abrir un archivo directamente:

```powershell
.\.venv\Scripts\python.exe app.py "C:\ruta\documento.pdf"
```

## Crear el ejecutable y el instalador

```powershell
& .\packaging\build.ps1
```

El script usa el Python del entorno virtual cuando existe, prepara los
recursos y licencias, crea el ejecutable con PyInstaller y descarga el
compilador oficial de Inno Setup 6.7.3 cuando no está disponible. Comprueba
su SHA-256 y su firma de origen antes de ejecutarlo. Las herramientas y
cachés quedan en `.cache/`, fuera del código publicado.

`prepare_ocr.py` descarga el instalador oficial de Tesseract 5.5.3 y los modelos
de español e inglés de un commit fijado de tessdata_fast. Comprueba los hashes,
extrae el ejecutable con 7-Zip sin instalarlo en Windows y conserva únicamente
las DLL necesarias. El instalador de Faro incluye ese runtime en `_internal/ocr`,
separado de las DLL de Qt. En ejecución no se descargan motores ni idiomas.
Las herramientas de extracción quedan únicamente en la caché de compilación.

Salida en `release/`:

- `FaroPDF-1.4.0-Instalar.exe`
- `FaroPDF-1.4.0-Portable.zip`
- `SHA256SUMS.txt`
- Informes y ejemplo sintético de validación.

El instalador es por usuario y no requiere privilegios de administrador.
No cambia la elección del lector PDF predeterminado. Las DLL incompatibles
del paquete 1.0.0 se retiran al actualizar.

## Verificación

La compilación debe pasar la misma prueba en el código y en el ejecutable:

```powershell
.\.venv\Scripts\python.exe app.py --self-test .cache\validation\source.json
```

La prueba crea su propio PDF e imagen junto al informe. Comprueba texto
multilínea con acentos, fuente y tamaño, imágenes, combinación y movimiento
de páginas, deshacer, guardado, reapertura y conservación del original.
No depende de archivos privados del desarrollador.

También ejecuta OCR real sobre escaneos sintéticos con las cuatro rotaciones,
CropBox desplazado y documentos mixtos. Verifica la conservación de imágenes,
selección, copia, búsqueda, guardado, reapertura, cancelación y deshacer. El modo
diagnóstico del ejecutable usa su propio proceso OCR y los idiomas empaquetados.

Después de compilar, también se comprueban el binario, los imports nativos
de Qt, la instalación y desinstalación aisladas, y la actualización sobre
restos del paquete anterior. Los archivos que se publican deben provenir
del workflow de compilación o de un árbol limpio del mismo commit.

## Dependencias reemplazables

Qt y sus bindings se distribuyen como DLL/PYD separados en `_internal`.
Puedes reemplazarlos por versiones compatibles o ejecutar el código con
tu propia compilación de las bibliotecas. El código fuente, las instrucciones
y las licencias permiten reconstruir la aplicación sin una clave del autor.
Consulta [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Las fuentes de Windows no se redistribuyen. Faro usa las instaladas en el
equipo y las incrustadas en el PDF, con las comprobaciones correspondientes.
