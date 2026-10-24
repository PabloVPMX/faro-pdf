**Faro PDF 1.4.0 incorpora OCR local en español e inglés y selección de texto.**

Abre **Edición → Reconocer texto (OCR)** y elige la página actual, todo el documento
o un rango como `1-3, 5`. Tesseract y ambos idiomas están incluidos: no necesitas
una cuenta ni conexión a internet. El proceso muestra el avance y permite cancelar.
Las páginas que ya tienen texto se omiten para evitar duplicados.

Se conservan las imágenes originales y se añade texto invisible para buscar y
copiar. Faro compara el renderizado antes y después y descarta un resultado que
cambie la apariencia de la página. El reconocimiento se aplica completo al terminar;
**Ctrl+Z** lo deshace. Guarda una copia para conservarlo al reabrir el PDF.

En **Seleccionar texto**, arrastra sobre las palabras y pulsa **Ctrl+C**.
**Ctrl+A** selecciona el texto de la página actual. **Ctrl+F** busca en el documento,
incluido el texto reconocido. Se mantienen la edición, los cuadros de texto,
imágenes, organización de páginas, impresión y actualizaciones.

### Actualizar y descargar

Si tienes Faro 1.2.0 o posterior, pulsa **Actualizar → Buscar ahora → Actualizar ahora**.
También puedes ejecutar el instalador sobre la versión anterior sin desinstalar.

- **FaroPDF-1.4.0-Instalar.exe**: instalación por usuario, dependencias y OCR incluidos.
- **FaroPDF-1.4.0-Portable.zip**: extrae todo el ZIP y abre `FaroPDF.exe`; conserva `_internal`.
- **SHA256SUMS.txt** y **verification.json**: integridad y comprobaciones de la publicación.

Requiere **Windows 10/11 x64**. El instalador conserva tu elección del lector PDF
predeterminado. Los documentos se procesan localmente y no se envían a GitHub.

### Límites

El OCR puede confundir caracteres: revisa nombres, acentos y cantidades. No recupera
la fuente original ni convierte el escaneo en párrafos editables. Puedes añadir tus
propios cuadros de texto con las herramientas habituales. No se incluyen todavía
firmas de documentos, PDF con contraseña ni recomposición automática de párrafos.
El guardado incremental no es una función de redacción segura de información.

Esta es una versión preliminar. Los ejecutables **siguen sin firma digital**;
la solicitud a SignPath está pendiente. No se pide desactivar la seguridad de Windows.
Consulta la [política de firma](https://github.com/PabloVPMX/faro-pdf/blob/main/CODE_SIGNING.md),
la [privacidad](https://github.com/PabloVPMX/faro-pdf/blob/main/PRIVACY.md) y los
[avisos de terceros](https://github.com/PabloVPMX/faro-pdf/blob/main/THIRD_PARTY_NOTICES.md).

### Verificación

La publicación usa la compilación automatizada del código público. Se comprueban
código, ejecutable, imports nativos, instalación y desinstalación aisladas. Las
pruebas incluyen OCR real en escaneos sintéticos con acentos, cuatro rotaciones,
recortes desplazados y páginas mixtas; selección, copia, búsqueda, guardado,
reapertura, deshacer y cancelación. No se incluyen documentos personales.

El código original de Faro es MIT; sus dependencias conservan sus propias licencias.
