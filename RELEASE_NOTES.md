**Faro PDF 1.6.4 elimina el componente OCR.**

Se retiran la opción Reconocer texto, el diálogo de resultados, el proceso de reconocimiento, Tesseract y sus modelos de español e inglés. El instalador también elimina el runtime OCR de las versiones anteriores.

La edición del texto existente conserva su funcionamiento: fuentes, tamaño, formato y posición. Se mantienen imágenes, selección de áreas y objetos, copiar/cortar/pegar, impresión, búsqueda y organización de páginas. Las páginas escaneadas siguen tratándose como imágenes. El texto que ya contiene un PDF, incluidas capas de texto añadidas con otras herramientas, continúa disponible para selección y búsqueda.

### Actualizar

Usa **Actualizar** en Faro o cierra sus ventanas y ejecuta **FaroPDF-1.6.4-Instalar.exe** sobre la instalación actual. No hace falta desinstalar. El coordinador espera la salida completa del lector y muestra el progreso.

- **FaroPDF-1.6.4-Portable.zip**: extrae todo y conserva `_internal` junto a `FaroPDF.exe`.
- **SHA256SUMS.txt** y **verification.json**: integridad y comprobaciones del código, ejecutable, DLL, instalación y cierre nativo.

Las pruebas verifican la ausencia de OCR en menús y paquetes, la eliminación del runtime antiguo al actualizar y las funciones de edición, guardado, portapapeles, impresión y búsqueda. La publicación automática verifica la etiqueta y los archivos sin duplicar ni reemplazar versiones existentes.

Windows 10/11 x64. Los ejecutables continúan sin firma digital. No se incluyen documentos personales ni se modifican las protecciones de Windows.
