**Faro PDF 1.5.0 añade selección, corte, copia y pegado de imágenes y cuadros de texto completos.**

Elige **Seleccionar objetos** en el selector de herramientas o en **Edición**.
Selecciona con un clic, añade o quita elementos con **Ctrl+clic**, o rodea varios
con un recuadro. Arrastra la selección para moverla, incluso si combina imágenes
y cuadros de texto. **Ctrl+A** marca los objetos de la página actual.

- **Ctrl+C** copia, **Ctrl+X** corta, **Ctrl+V** pega y **Supr** borra.
- **Clic derecho → Pegar aquí** coloca los objetos junto al cursor.
- Pega en otra página o ventana de Faro. Cada pegado crea cuadros independientes.
- Los cuadros propios conservan fuente, tamaño, color y líneas y siguen editables
  con doble clic, incluso después de guardar y reabrir.
- Puedes pegar imágenes o texto de otras aplicaciones. Dentro del editor, los
  atajos cortan, copian y pegan letras.
- **Ctrl+Z** deshace una operación completa, incluido el arrastre de un grupo.

El copiado conserva los recursos PDF de las fuentes e imágenes. El pegado se
anexa sin regenerar los streams originales de la página de destino. Se comprueba
que los cambios no alteren contenido fuera de la selección. Se mantienen el OCR
local en español e inglés, impresión, búsqueda, edición y organización de páginas.

### Actualizar y descargar

Si tienes Faro 1.2.0 o posterior, pulsa **Actualizar → Buscar ahora → Actualizar ahora**.
También puedes ejecutar el instalador sobre la versión anterior sin desinstalar.

- **FaroPDF-1.5.0-Instalar.exe**: instalación por usuario, dependencias y OCR incluidos.
- **FaroPDF-1.5.0-Portable.zip**: extrae todo el ZIP y abre `FaroPDF.exe`; conserva `_internal`.
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
