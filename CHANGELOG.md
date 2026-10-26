# Cambios

## 1.5.0 — Seleccionar, cortar, copiar y pegar objetos

- Modo Seleccionar objetos: imágenes y cuadros completos con clic, Ctrl+clic,
  recuadro de selección y Ctrl+A; arrastre de varios elementos juntos.
- Cortar, copiar y pegar con Ctrl+X/C/V, menú Edición y menú contextual; pegar aquí.
- Fragmentos PDF con fuentes e imágenes conservadas, compatibles con otras páginas
  y ventanas de Faro; los cuadros propios continúan editables al guardar y reabrir.
- Pegado de imágenes y texto externos; atajos de letras mientras se usa el cursor.
- Corte, borrado, arrastre y pegado atómicos, con deshacer y comprobación visual
  de conservación fuera de la selección. No se regeneran los streams del destino.
- Reutilización de fuentes idénticas al pegar y de mapas Unicode ya verificados.
- Pruebas sintéticas de fuentes, transparencia, página girada, pegados repetidos,
  párrafos nativos, portapapeles externo, cancelación de errores y deshacer.

## 1.4.0 — OCR local y selección de texto

- OCR con Tesseract 5.5.3 y modelos incluidos de español e inglés; sin conexión.
- Reconocimiento de página actual, documento o rango; se omiten páginas con texto.
- Capa de texto invisible que conserva las imágenes, rotaciones y recortes;
  comprobación visual antes de aceptar el resultado.
- Proceso independiente con progreso y cancelación; deshacer y rehacer el OCR.
- Modo Seleccionar texto, copiar con Ctrl+C y seleccionar la página con Ctrl+A.
- Búsqueda y selección del OCR al guardar y reabrir; edición propia independiente.
- Pruebas de OCR real con escaneos sintéticos, páginas mixtas y cuatro rotaciones.

## 1.3.1 — Añadir texto sin depender de las fuentes originales

- Los cuadros nuevos usan contenido y fuentes independientes. Una fuente del
  documento sin mapa ToUnicode ya no impide añadir y editar texto propio.
- Los cuadros conservan acentos, saltos, tamaño, fuente y posición al guardar
  y reabrir; se pueden mover y borrar sin regenerar los elementos originales.
- Si el editor no puede iniciarse, la inserción se revierte sin dejar «Texto».
- Se mantienen la validación de fuentes originales y los controles de píxeles
  fuera del cuadro. Prueba de regresión con una fuente original sin ToUnicode.

## 1.3.0 — Impresión y búsqueda

- Imprimir con Ctrl+P, diálogo de Windows, intervalos de páginas, página actual,
  orden de impresión y ajuste al papel conservando proporciones.
- Vista previa desde Archivo, renderizado de hasta 300 ppp y memoria acotada.
- Buscar con Ctrl+F en todas las páginas, resultados resaltados y navegación
  circular con Enter/F3 y Mayús+Enter/Mayús+F3; filtros de mayúsculas y palabras.
- Búsqueda incremental sin ejecutar PDFium en varios hilos; resultados actualizados
  después de editar y resaltados compatibles con zoom y páginas giradas.
- Pruebas sintéticas de navegación y salida de impresión a archivo. Ninguna prueba
  envía trabajos a impresoras físicas.

## 1.2.0 — Actualizaciones desde Faro

- Botón Actualizar y menú Archivo → Actualizaciones, con búsqueda en segundo plano.
- Búsqueda diaria y descarga automática configurables; instalación al cerrar todas
  las ventanas después de guardar o descartar los cambios de forma habitual.
- Actualizar ahora instala y vuelve a abrir Faro. Las ediciones anteriores requieren
  instalar esta versión una vez; la edición portátil ofrece descargas manuales.
- Comprobación del informe de la publicación, tamaño y SHA-256 antes de ejecutar
  el instalador. Se rechazan descargas incompletas o alteradas.
- Pruebas sin red para errores, cancelación, varias ventanas y protección de cambios.
- Política de privacidad actualizada con las conexiones automáticas a GitHub.

## 1.1.1 — Navegación continua estable

- El indicador de página sigue la hoja que contiene el centro visible del
  documento, sin adelantarse mientras se recorre la mitad inferior de la anterior.
- El ajuste inicial reserva el espacio de la barra de scroll y conserva el zoom
  al pasar de una página a otra.
- La validación espera a que se complete la activación de la página, en lugar
  de suponer un tiempo fijo de 90 ms.

## 1.1.0 — Vista continua y cuadros de texto

- Vista vertical continua con páginas de distintos tamaños y carga de vistas
  previas según se necesitan; opción para volver a la vista de una sola página.
- Creación de cuadros de texto arrastrando sobre la hoja, con fuente y tamaño
  en una barra compacta separada, sin abrir automáticamente las propiedades.
- Ajuste del texto nuevo al ancho del cuadro usando las métricas de su fuente.
  Los cuadros conservan su contenido y formato al guardar, mover y reabrir.
- Deshacer una inserción retira todo el cuadro, incluido el marcador inicial.
- Pruebas de interacción en varias páginas y comparación de píxeles para comprobar
  que las páginas ajenas a la edición no cambian.
- Solicitud a SignPath Foundation enviada, pendiente de evaluación.

## 1.0.2 — Primera versión pública preliminar

- Código fuente y scripts de compilación preparados para GitHub.
- Prueba sintética que no depende de documentos del desarrollador.
- Documentación de uso, privacidad, límites, licencias y firma pendiente.
- Compilación de Windows con dependencias fijadas y sin DLL ajenas al proyecto.
- El programa no abre automáticamente un documento de prueba.

## 1.0.1 — Corrección del paquete local

- Se retiró una versión incompatible de ICU recogida desde el PATH de otra
  herramienta, que impedía importar QtCore.
- El instalador elimina también las DLL obsoletas al actualizar.
- Se verificaron ejecución portable, instalación, actualización y guardado.

## Funciones iniciales

Edición de texto nativo, acentos y líneas múltiples; inserción y movimiento
de cuadros de texto; inserción, movimiento, borrado y tamaño de imágenes;
combinación, movimiento y borrado de páginas; guardado de copia y deshacer.
