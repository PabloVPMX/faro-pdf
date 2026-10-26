**Faro PDF 1.6.0 añade selección libre por área y corrige los encabezados agrupados que no se podían seleccionar.**

### Seleccionar y recortar

- **Edición → Girar página**: 90° a derecha/izquierda o 180°. Se guarda en el PDF y admite Deshacer; las otras páginas conservan su orientación.

- **Seleccionar objetos** reconoce grupos Form, incluidos encabezados con texto, logotipos y transparencia. Puedes copiarlos, cortarlos y moverlos manteniendo sus recursos PDF y apariencia.
- **Seleccionar área (imagen)** permite rodear cualquier parte del documento con un rectángulo, aunque atraviese un objeto. **Ctrl+C** copia, **Ctrl+X** recorta visualmente y **Ctrl+V** pega como imagen que puedes mover y redimensionar.
- La copia de área usa 300 ppp, limitada a 20 millones de píxeles por página. Solo el fragmento se convierte en imagen; el resto conserva su contenido original. **Ctrl+Z** recupera el recorte.
- Cortar área es un recorte visual, no una herramienta de censura segura. Se rechazan áreas que intersectan anotaciones o campos de formulario para no dejar apariencias inconsistentes.

### Resultado visible del OCR

El OCR conserva el aspecto original y añade letras que permiten buscar con **Ctrl+F** y copiar con **Seleccionar texto**. Ahora muestra un resultado con texto disponible, páginas reconocidas y páginas omitidas porque ya contenían texto. No reconstruye la fuente original ni convierte escaneos en cuadros editables. Revisa los datos reconocidos, especialmente nombres y cantidades.

### Actualizar

Pulsa **Actualizar → Buscar ahora → Actualizar ahora**. También puedes ejecutar el nuevo instalador sobre la versión anterior, sin desinstalar.

- **FaroPDF-1.6.0-Instalar.exe**: instalación por usuario, dependencias y OCR incluidos.
- **FaroPDF-1.6.0-Portable.zip**: extrae todo el ZIP y abre FaroPDF.exe; conserva _internal.
- **SHA256SUMS.txt** y **verification.json**: integridad y comprobaciones de la publicación.

Windows 10/11 x64. El instalador conserva la elección del lector predeterminado. Los documentos se procesan en tu equipo y no se publican. Los ejecutables siguen sin firma digital; la solicitud a SignPath está pendiente.

### Verificación y límites

Se comprueban código, ejecutable, imports nativos e instalación/desinstalación aisladas. Las pruebas incluyen Form con transparencia, copia/corte/movimiento, áreas parciales, cuatro rotaciones y recortes desplazados, portapapeles, píxeles fuera del área, Deshacer y originales intactos, además de todas las regresiones anteriores de texto, imágenes, impresión, búsqueda y OCR real. Las pruebas públicas usan únicamente documentos sintéticos.

No se incluyen firmas de documentos, PDF con contraseña ni recomposición automática de párrafos. El guardado incremental y los recortes no eliminan de forma segura datos confidenciales. El código original de Faro es MIT; las dependencias conservan sus licencias.
