**Faro PDF 1.3.1** corrige el bloqueo al **añadir texto** en documentos cuyas fuentes originales no tienen un mapa ToUnicode verificable.

Los cuadros nuevos usan sus propias fuentes y contenido independiente: puedes escribir acentos y saltos de línea, cambiar formato, moverlos y volver a editarlos al guardar y reabrir. Las fuentes y los elementos originales permanecen intactos. Si no se puede iniciar el editor, se revierte la inserción sin dejar un marcador «Texto».

Se mantienen las funciones de impresión, búsqueda, imágenes, organización de páginas y actualizaciones de la versión anterior.

**Ctrl+P / Archivo → Imprimir** abre el diálogo de Windows para elegir impresora y páginas. **Archivo → Vista previa de impresión** permite revisar la salida. Se imprime la edición actual, ajustada al papel y conservando las proporciones, con renderizado de hasta 300 ppp.

**Ctrl+F / Archivo → Buscar en el documento** busca en todas las páginas y resalta las coincidencias. Usa Enter/F3 y Mayús+Enter/Mayús+F3 para avanzar y retroceder. Incluye filtros de mayúsculas y palabras completas, funciona con páginas giradas y recalcula los resultados al editar. Los resaltados no se guardan ni se imprimen; los escaneos sin texto requieren OCR.

Si tienes **1.2.0**, puedes actualizar desde el botón **Actualizar**. Se conservan la búsqueda diaria, la descarga en segundo plano y la instalación al cerrar todas las ventanas, configurables desde ese cuadro.

**Si ya tienes Faro 1.1.1 o anterior**, descarga únicamente el instalador nuevo y ejecútalo sobre la instalación existente. No hace falta desinstalar. Esta instalación inicial incorpora el actualizador para las versiones futuras. La edición portátil se actualiza descargando y extrayendo el ZIP completo.

Se comprueban el informe de publicación, el tamaño y las sumas SHA-256 de GitHub antes de ejecutar el instalador. Esta comprobación no sustituye la firma digital de Windows, que sigue pendiente. Las conexiones a GitHub no envían tus PDF.

### Descargar

- **FaroPDF-1.3.1-Instalar.exe**: instalación por usuario, accesos directos y registro en «Abrir con». Incluye sus dependencias; no hace falta instalar Python.
- **FaroPDF-1.3.1-Portable.zip**: extrae la carpeta completa y abre `FaroPDF.exe`. Conserva `_internal` junto al ejecutable.
- **SHA256SUMS.txt**: sumas para comprobar la integridad de las descargas.
- **verification.json**: resultado de las comprobaciones automatizadas.

Requiere **Windows 10/11 de 64 bits**. El instalador conserva tu elección del lector PDF predeterminado y permite desinstalar Faro desde Configuración de Windows.

### Funciones

Desplázate por varias páginas con la rueda y dibuja cuadros de texto directamente sobre la hoja. La fuente y el tamaño aparecen en una barra aparte; el texto nuevo se ajusta al ancho del cuadro y sigue siendo editable al guardar y reabrir. Se conservan la edición de texto nativo con acentos y varias líneas; las imágenes; la combinación y organización de páginas; deshacer, rehacer y guardar una copia. El procesamiento ocurre localmente.

### Estado y límites

Es una publicación preliminar, con mejoras pendientes. Usa copias y revisa el resultado. No incluye OCR, firmas de documentos, PDF con contraseña ni ajuste automático de párrafos. El guardado incremental **no es una función de redacción segura** de información confidencial. Las estructuras complejas pueden rechazar una edición para conservar el contenido.

### Code signing policy

Esta versión **todavía no está firmada digitalmente**. Windows puede advertir o bloquear su ejecución, especialmente con Smart App Control activo. Publicar en GitHub no equivale a una firma reconocida. La solicitud a SignPath Foundation se envió el 23 de octubre de 2026 y está pendiente de evaluación; no hay una aprobación concedida.

Consulta la [política de firma](https://github.com/PabloVPMX/faro-pdf/blob/main/CODE_SIGNING.md), la [privacidad](https://github.com/PabloVPMX/faro-pdf/blob/main/PRIVACY.md) y los [avisos de terceros](https://github.com/PabloVPMX/faro-pdf/blob/main/THIRD_PARTY_NOTICES.md).

### Verificación

Los binarios provienen del código público y de la compilación automatizada de GitHub Actions. Pasaron las pruebas del código, ejecutable empaquetado, imports nativos de Qt, instalación y desinstalación aisladas, limpieza de DLL obsoletas al actualizar, texto, imágenes, páginas, guardado y reapertura. Las pruebas usan documentos sintéticos y el paquete no contiene documentos personales.

El código original de Faro PDF se distribuye bajo licencia MIT. Las bibliotecas conservan sus licencias respectivas.
