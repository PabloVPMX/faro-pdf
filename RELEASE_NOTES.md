**Faro PDF 1.6.1 corrige el reconocimiento de fuentes y el cierre de la aplicación.**

### Texto después de editar imágenes

Se reconocen correctamente Times-Bold, Times-Italic y nombres PostScript equivalentes. La negrita y cursiva se conservan. El cambio de modo no sustituye las fuentes del PDF.

Las fuentes CFF con subconjuntos separados pueden reutilizar sus glifos originales presentes en el documento para añadir palabras y acentos. Se verifican los contornos y métricas conservados y se exige que las páginas originales sigan viéndose igual antes de aplicar la edición. Si un carácter no está incluido en ningún subconjunto disponible de esa cara, sigue siendo necesaria la fuente original completa o una alternativa elegida explícitamente; no se inventan glifos ni se selecciona una fuente parecida automáticamente.

### Cierre completo

Al cerrar con OCR, impresión o actualizaciones en curso, Faro solicita la cancelación y reintenta el cierre automáticamente cuando esas tareas terminan. No hace falta volver a pulsar la X. El cierre aceptado de la ventana principal termina el bucle de la aplicación, oculta los diálogos auxiliares, detiene temporizadores y libera el documento. Se conserva la confirmación de cambios sin guardar. Si un texto no se puede aplicar, es posible descartarlo explícitamente para continuar o cerrar.

### Actualizar

**Actualizar → Buscar ahora → Actualizar ahora**, o ejecuta el instalador sobre la versión anterior.

- **FaroPDF-1.6.1-Instalar.exe**: instalación por usuario, dependencias y OCR incluidos.
- **FaroPDF-1.6.1-Portable.zip**: extrae todo el ZIP y conserva _internal junto a FaroPDF.exe.
- **SHA256SUMS.txt** y **verification.json**: integridad y resultados de las comprobaciones.

Windows 10/11 x64. Los ejecutables continúan sin firma digital. SignPath Foundation rechazó la solicitud inicial por visibilidad pública insuficiente; la edición MSIX para Microsoft Store sigue en evaluación y todavía no está publicada. No se modifican las protecciones de Windows.

### Verificación

Pruebas sintéticas de estilos Standard-14, transición de imágenes a texto, ampliación CFF con acentos y otras páginas intactas, guardado/reapertura, deshacer y descarte explícito. Los procesos de prueba deben terminar realmente después de cerrar con diálogos, OCR y actualizaciones activos. Se mantienen las regresiones de edición, gráficos, áreas, rotación, impresión, búsqueda y OCR local. El código, ejecutable, imports nativos e instalación/desinstalación se verifican antes de publicar. No se incluyen documentos personales.
