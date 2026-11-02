# Cambios

## 1.6.4 — Retirada del componente OCR

- Retira el menú, diálogo, motor Tesseract y modelos de reconocimiento. El instalador limpia el runtime OCR de instalaciones anteriores.
- Conserva la edición, búsqueda y selección del texto existente, junto con imágenes, páginas, portapapeles e impresión.
- Comprueba que los paquetes nuevos no incluyan motores ni idiomas OCR y que la actualización elimine los archivos obsoletos.
- Publicación automática con permisos corregidos, versión obtenida del informe y verificación de los archivos existentes al repetir el flujo.

## 1.6.3 — Actualizaciones después del cierre real

- El actualizador espera a que termine el proceso completo antes de reemplazar el ejecutable o sus DLL. Un coordinador independiente de Python/Qt verifica otra vez la suma SHA-256 y espera la salida del instalador antes de reabrir Faro.
- Un bloqueo entre procesos evita actualizaciones simultáneas y pospone nuevos arranques mientras se instala. Los PDF solicitados durante ese intervalo se abren al terminar correctamente.
- La actualización muestra progreso. Si falla, conserva un resultado consultable desde Actualizaciones; no abre automáticamente una instalación incompleta.
- El instalador comprueba que el lector haya terminado antes de escribir archivos. Conserva la confirmación de cambios sin guardar y no finaliza otras ventanas.
- Se añaden pruebas del coordinador real y de apertura maximizada/cierre con la plataforma nativa de Windows, tanto desde código como con el ejecutable portátil e instalado.

## 1.6.2 — Cancelación durante el arranque del OCR

- El proceso OCR necesita una confirmación de inicio del lector antes de procesar el PDF o crear un hijo Tesseract. Se puede terminar de forma segura un arranque cancelado sin dejar procesos hijos.
- El cierre se prueba también de forma inmediata, antes de que el trabajador confirme que está listo, cubriendo arranques lentos de Python o DLLs.
- Conserva los arreglos de fuentes CFF, estilos Standard-14 y cierre completo de 1.6.1.

## 1.6.1 — Fuentes originales y cierre completo

- Reconoce Times-Bold, Times-Italic y variantes PostScript, respetando negrita/cursiva al volver de editar imágenes.
- Amplía codificaciones CFF Type1/Identity-H reutilizando glifos originales de subconjuntos de la misma cara presentes en el PDF. Verifica contornos, métricas y apariencia de todas las páginas antes de editar.
- Cancela tareas y vuelve a intentar el cierre automáticamente; el cierre aceptado de la ventana principal termina el bucle de la aplicación aunque existan diálogos auxiliares. Detiene temporizadores y libera el PDF.
- Una edición no aplicable se puede descartar explícitamente, sin impedir salir de la aplicación.
- Regresiones sintéticas para imagen→texto, palabras/acentos CFF, guardado/reapertura y salida real de procesos con diálogos, OCR y actualizaciones.

## 1.6.0 — Áreas y encabezados agrupados

- Girar la página actual 90° a derecha/izquierda o 180°, con guardado y Deshacer.

- Selección de grupos Form, incluidos encabezados con transparencia, para copiar, cortar, pegar y mover conservando los recursos originales.
- Seleccionar área (imagen): recuadro libre sobre cualquier parte de la página, copia a 300 ppp y pegado como imagen que se puede mover/redimensionar. El recorte se limita a 20 millones de píxeles por página.
- Cortar área recorta visualmente el contenido sin rasterizar el resto y admite Deshacer. No es censura segura; las anotaciones y campos intersectados se rechazan.
- OCR muestra un resultado con texto disponible y explica las páginas que ya tenían texto, sin modificar su apariencia.
- Regresiones con encabezados Form, recortes parciales, cuatro rotaciones, CropBox, portapapeles, deshacer y original intacto.

## 1.5.1 — Copia fiel en PDF con texto trazado

- La copia de imágenes y gráficos conserva los operadores y transformaciones
  originales; evita regenerar el contenido al aislarlos. Se mantiene la comparación
  exacta de píxeles para rechazar cambios de apariencia.
- Selección de trazos vectoriales, agrupando contornos de letras próximos en una
  misma línea. Permite copiar, cortar, pegar y mover esos gráficos sin sustituir
  fuentes ni convertirlos a imágenes dentro del PDF.
- Los recortes que afectan a otros objetos se conservan al eliminar un trazo;
  se bloquea mover un trazo si define un recorte compartido.
- Lectura de operandos numéricos optimizada para páginas con muchos contornos.
- Regresión sintética con streams y matrices persistentes que reproduce el fallo
  de la copia anterior; validación de conservación, movimiento, corte y deshacer.

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
