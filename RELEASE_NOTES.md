**Faro PDF 1.5.1 corrige la copia de imágenes en páginas con transformaciones persistentes y añade selección de contornos vectoriales.**

En algunos PDF, aislar un logotipo desplazaba la copia fuera de la página y Faro
la rechazaba para conservar su apariencia. Ahora la extracción mantiene los
operadores y transformaciones originales. Se conserva la comparación exacta de
píxeles antes de aceptar la copia.

Algunos documentos dibujan sus letras como trazos. **Seleccionar objetos** permite
seleccionarlos, copiarlos, cortarlos y moverlos como gráficos, agrupando los
contornos próximos en una misma línea. Un recuadro permite seleccionar conjuntos.
No se sustituye la fuente ni se rasterizan esos contornos dentro del PDF. Para
buscar o copiar sus letras como texto, utiliza el OCR local.

Se mantienen Ctrl+X/C/V, pegar aquí, el arrastre de grupos, los cuadros editables,
imágenes, impresión, búsqueda y OCR en español e inglés. Ctrl+Z deshace la operación.

### Actualizar y descargar

Si tienes Faro 1.2.0 o posterior, pulsa **Actualizar → Buscar ahora → Actualizar ahora**.
También puedes ejecutar el instalador sobre la versión anterior sin desinstalar.

- **FaroPDF-1.5.1-Instalar.exe**: instalación por usuario, dependencias y OCR incluidos.
- **FaroPDF-1.5.1-Portable.zip**: extrae todo el ZIP y abre `FaroPDF.exe`; conserva `_internal`.
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
pruebas incluyen selección de grupos, corte/copia/pegado repetido, imágenes transparentes,
fuentes incrustadas, texto nativo y página girada, además de OCR real en escaneos sintéticos con acentos, cuatro rotaciones,
recortes desplazados y páginas mixtas; selección, copia, búsqueda, guardado,
reapertura, deshacer y cancelación. No se incluyen documentos personales.

El código original de Faro es MIT; sus dependencias conservan sus propias licencias.
