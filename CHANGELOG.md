# Cambios

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
