**Faro PDF 1.1.0** añade vista vertical continua y cuadros de texto dentro del documento. Es un lector y editor gratuito y de código abierto para Windows.

### Descargar

- **FaroPDF-1.1.0-Instalar.exe**: instalación por usuario, accesos directos y registro en «Abrir con». Incluye sus dependencias; no hace falta instalar Python.
- **FaroPDF-1.1.0-Portable.zip**: extrae la carpeta completa y abre `FaroPDF.exe`. Conserva `_internal` junto al ejecutable.
- **SHA256SUMS.txt**: sumas para comprobar la integridad de las descargas.
- **verification.json**: resultado de las comprobaciones automatizadas.

Requiere **Windows 10/11 de 64 bits**. El instalador conserva tu elección del lector PDF predeterminado y permite desinstalar Faro desde Configuración de Windows.

### Funciones

Desplázate por varias páginas con la rueda y dibuja cuadros de texto directamente sobre la hoja. La fuente y el tamaño aparecen en una barra aparte; el texto nuevo se ajusta al ancho del cuadro y sigue siendo editable al guardar y reabrir. Se conservan la edición de texto nativo con acentos y varias líneas; las imágenes; la combinación y organización de páginas; deshacer, rehacer y guardar una copia. El procesamiento ocurre localmente.

### Estado y límites

Es una publicación preliminar, con mejoras pendientes. Usa copias y revisa el resultado. No incluye OCR, impresión, búsqueda, firmas de documentos, PDF con contraseña ni ajuste automático de párrafos. El guardado incremental **no es una función de redacción segura** de información confidencial. Las estructuras complejas pueden rechazar una edición para conservar el contenido.

### Code signing policy

Esta versión **todavía no está firmada digitalmente**. Windows puede advertir o bloquear su ejecución, especialmente con Smart App Control activo. Publicar en GitHub no equivale a una firma reconocida. La solicitud a SignPath Foundation se envió el 23 de octubre de 2026 y está pendiente de evaluación; no hay una aprobación concedida.

Consulta la [política de firma](https://github.com/PabloVPMX/faro-pdf/blob/main/CODE_SIGNING.md), la [privacidad](https://github.com/PabloVPMX/faro-pdf/blob/main/PRIVACY.md) y los [avisos de terceros](https://github.com/PabloVPMX/faro-pdf/blob/main/THIRD_PARTY_NOTICES.md).

### Verificación

Los binarios provienen del código público y de la compilación automatizada de GitHub Actions. Pasaron las pruebas del código, ejecutable empaquetado, imports nativos de Qt, instalación y desinstalación aisladas, limpieza de DLL obsoletas al actualizar, texto, imágenes, páginas, guardado y reapertura. Las pruebas usan documentos sintéticos y el paquete no contiene documentos personales.

El código original de Faro PDF se distribuye bajo licencia MIT. Las bibliotecas conservan sus licencias respectivas.
