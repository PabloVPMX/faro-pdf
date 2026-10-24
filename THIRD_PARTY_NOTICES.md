# Bibliotecas y licencias de terceros

La licencia MIT de Faro PDF cubre el código original de esta aplicación.
No cambia las licencias de las bibliotecas ni de sus componentes internos.
Se usan distribuciones sin modificar de sus respectivos proyectos.

| Componente | Versión fijada | Licencia principal y procedencia |
| --- | --- | --- |
| Python | 3.12 | [PSF y licencias incorporadas](https://docs.python.org/3/license.html) |
| PySide6 Essentials y Shiboken6 | 6.12.0 | [LGPL-3.0 / GPL y componentes de Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html) |
| Qt Core, Gui, Widgets, PrintSupport, Network, Svg y Test | 6.12.0 | [LGPL-3.0 y licencias de componentes incorporados](https://doc.qt.io/qt-6/licenses-used-in-qt.html) |
| pypdfium2 | 5.14.0 | Apache-2.0 / BSD-3-Clause y avisos de [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) |
| PDFium | Distribuido por pypdfium2 5.14.0 | BSD y licencias de terceros, incluidas en los avisos del paquete |
| fontTools | 4.67.0 | [MIT](https://github.com/fonttools/fonttools) |
| Pillow | 13.0.0 | [HPND y componentes incorporados](https://github.com/python-pillow/Pillow) |
| NumPy | 2.5.4 | [BSD-3-Clause y componentes incorporados](https://github.com/numpy/numpy) |
| pypdf | 6.21.1 | [BSD-3-Clause](https://github.com/py-pdf/pypdf) |
| Tesseract OCR | 5.5.3 | [Apache-2.0](https://github.com/tesseract-ocr/tesseract/tree/5.5.3), CLI independiente y sus bibliotecas |
| tessdata_fast, español e inglés | commit 87416418657359cb625c412a48b6e1d6d41c29bd | [Apache-2.0](https://github.com/tesseract-ocr/tessdata_fast) |

Los textos de licencia, avisos de los paquetes y manifiesto de versiones se
incluyen en `_internal/assets/licenses/` en la distribución de Windows.
Las copias de [LGPLv3](LICENSE-LGPL-3.0.txt) y [GPLv3](LICENSE-GPL-3.0.txt)
acompañan también al código.

El runtime OCR y sus avisos se incluyen en `_internal/ocr/`, con un manifiesto
de los archivos y sus hashes. Sus DLL están aisladas de Qt y se pueden reemplazar
por compilaciones compatibles. Consulta [los avisos de OCR](licenses/OCR-NOTICES.md)
para la procedencia y las licencias de sus dependencias.

## Qt y sus bindings

Faro usa la opción de licencia de código abierto de Qt/PySide6. Qt se carga
mediante bibliotecas compartidas; no se exige una licencia comercial de Qt
para usar el código original de Faro bajo MIT.

Las DLL y PYD de Qt y Shiboken se mantienen separadas, sin modificar. Puedes
reemplazarlas por versiones compatibles, ejecutar el código con tu propia
compilación y depurar modificaciones de esas bibliotecas. La aplicación no
impone restricciones de ingeniería inversa para depurar tales modificaciones.

Código fuente correspondiente de las versiones utilizadas:

- [Qt base, etiqueta v6.12.0](https://github.com/qt/qtbase/tree/v6.12.0).
- [Qt SVG, etiqueta v6.12.0](https://github.com/qt/qtsvg/tree/v6.12.0).
- [Qt translations, etiqueta v6.12.0](https://github.com/qt/qttranslations/tree/v6.12.0).
- [PySide6 y Shiboken, etiqueta v6.12.0](https://code.qt.io/cgit/pyside/pyside-setup.git/tree/?h=v6.12.0).
- [Instrucciones oficiales para compilar Qt for Python](https://doc.qt.io/qtforpython-6/building_from_source/index.html).

Las versiones y bibliotecas internas exactas se pueden comprobar en los
archivos `version.json`, metadatos y avisos incluidos en el paquete. El código
de Faro, sus scripts y dependencias fijadas están disponibles en este repositorio.

## Fuentes y otros recursos

No se redistribuyen las fuentes de Windows, documentos de prueba del autor,
logotipos de otros editores ni código binario de aplicaciones propietarias.
Las fuentes importadas o incrustadas en un PDF mantienen sus propias
condiciones; es responsabilidad de quien comparte ese documento respetarlas.

El icono de Faro se genera desde `packaging/make_assets.py` y forma parte del
código original del proyecto bajo MIT. Los nombres de bibliotecas y marcas
se utilizan únicamente para atribución e identificación.
