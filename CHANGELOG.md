# Cambios

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
