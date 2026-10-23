Primera versión pública preliminar de **Faro PDF**, un lector y editor de PDF gratuito y de código abierto para Windows.

### Descargar

- **FaroPDF-1.0.2-Instalar.exe**: instalación por usuario, accesos directos y registro en «Abrir con». Incluye sus dependencias; no hace falta instalar Python.
- **FaroPDF-1.0.2-Portable.zip**: extrae la carpeta completa y abre `FaroPDF.exe`. Conserva `_internal` junto al ejecutable.
- **SHA256SUMS.txt**: sumas para comprobar la integridad de las descargas.
- **verification.json**: resultado de las comprobaciones automatizadas.

Requiere **Windows 10/11 de 64 bits**. El instalador conserva tu elección del lector PDF predeterminado y permite desinstalar Faro desde Configuración de Windows.

### Funciones

Edición de texto nativo con acentos y varias líneas; añadir, mover y dar formato a cuadros de texto; insertar, mover, redimensionar y borrar imágenes; combinar PDF y reordenar o borrar páginas; deshacer, rehacer y guardar una copia. El procesamiento ocurre localmente.

### Estado y límites

Es una publicación preliminar, con mejoras pendientes. Usa copias y revisa el resultado. No incluye OCR, impresión, búsqueda, firmas de documentos, PDF con contraseña ni ajuste automático de párrafos. El guardado incremental **no es una función de redacción segura** de información confidencial. Las estructuras complejas pueden rechazar una edición para conservar el contenido.

### Code signing policy

Esta versión **todavía no está firmada digitalmente**. Windows puede advertir o bloquear su ejecución, especialmente con Smart App Control activo. Publicar en GitHub no equivale a una firma reconocida. La evaluación de opciones de firma gratuita para código abierto está en preparación y no hay una aprobación concedida.

Consulta la [política de firma](https://github.com/PabloVPMX/faro-pdf/blob/main/CODE_SIGNING.md), la [privacidad](https://github.com/PabloVPMX/faro-pdf/blob/main/PRIVACY.md) y los [avisos de terceros](https://github.com/PabloVPMX/faro-pdf/blob/main/THIRD_PARTY_NOTICES.md).

### Verificación

Los binarios provienen del código público y de la compilación automatizada de GitHub Actions. Pasaron las pruebas del código, ejecutable empaquetado, imports nativos de Qt, instalación y desinstalación aisladas, limpieza de DLL obsoletas al actualizar, texto, imágenes, páginas, guardado y reapertura. Las pruebas usan documentos sintéticos y el paquete no contiene documentos personales.

El código original de Faro PDF se distribuye bajo licencia MIT. Las bibliotecas conservan sus licencias respectivas.
