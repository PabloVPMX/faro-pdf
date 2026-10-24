# Privacidad

Faro PDF procesa los documentos en el equipo del usuario. No incorpora
cuentas de usuario, telemetría, publicidad ni servicios de análisis remoto.
No envía automáticamente PDF, texto, imágenes ni fuentes a un servidor.

El OCR utiliza Tesseract y modelos incluidos de español e inglés, sin conexión.
Para reconocer un documento crea una copia temporal local y las imágenes de las
páginas procesadas. Los archivos temporales se eliminan al terminar o cancelar;
un cierre forzado del sistema podría dejar restos en la carpeta temporal de Windows.
El resultado solo se conserva como PDF cuando eliges guardarlo. El OCR no hace
peticiones a servicios externos ni descarga idiomas durante el uso.

La búsqueda de texto se ejecuta localmente. Imprimir entrega las páginas a la
cola y al controlador de la impresora que elijas en el diálogo de Windows.
Si eliges una impresora de red o un servicio de impresión externo, ese destino
recibirá el contenido como parte del trabajo que hayas confirmado. Faro no
imprime automáticamente ni añade los resaltados de búsqueda al documento.

## Actualizaciones

Desde 1.2.0, Faro consulta la API pública de GitHub cada día mientras se utiliza
la aplicación. No hay un servicio residente cuando Faro está cerrado. La edición
instalada descarga el instalador de la versión nueva y lo ejecuta al cerrar todas
las ventanas, después del diálogo habitual para los documentos sin guardar.
Puedes desactivar la búsqueda y la instalación automáticas desde **Actualizar**.
La edición portátil ofrece la descarga manual.

Estas conexiones comunican a GitHub la dirección IP, la versión de Faro en el
agente de usuario y la información técnica habitual de una petición HTTPS.
No envían documentos, contenido editado, fuentes, correo ni identificadores de
cuenta, y no requieren iniciar sesión en GitHub. GitHub aplica su propia política
de privacidad. Los paquetes se guardan en la carpeta local de datos de Faro;
las preferencias y la fecha de la última comprobación permanecen en el equipo.
No se añade telemetría ni se envían informes de uso o errores.

El botón «Buscar / descargar» de fuentes abre una búsqueda de Google Fonts
en el navegador predeterminado. Esa visita está sujeta a la política del
sitio externo y solo ocurre por una acción explícita del usuario.

Importar un TTF lee un archivo local. Guardar escribe en la ubicación
elegida. El instalador copia el programa y registra su disponibilidad como
lector PDF; no sube documentos y no impone una aplicación predeterminada.

Los informes de `--self-test` solo se generan si se invoca esa opción y
permanecen junto al archivo de informe indicado. Usan documentos sintéticos.

Al abrir un issue o un pull request en GitHub, el contenido que publiques
quedará en GitHub y estará sujeto a sus políticas. No publiques información
confidencial. Una eventual solicitud de firma o su proveedor no reciben
documentos PDF del usuario como parte del funcionamiento del programa.
