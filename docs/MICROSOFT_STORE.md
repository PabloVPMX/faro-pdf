# Firma y distribución con presupuesto adicional cero

Evaluación del 26 de octubre de 2026. Esta es una vía propuesta, no una
publicación aprobada ni un paquete MSIX ya probado.

## Opción viable: Microsoft Store y MSIX

Microsoft indica que el nuevo registro de desarrolladores no cobra inscripción.
Se debe empezar en [storedeveloper.microsoft.com](https://storedeveloper.microsoft.com/):
otras entradas pueden mostrar el proceso antiguo. Una cuenta individual para
un proyecto personal requiere cuenta Microsoft, identificación y selfie. El
mantenedor debe completar esa verificación directamente con Microsoft.

Al aprobar un paquete MSIX, la tienda lo firma y gestiona su distribución y
actualizaciones. No entrega una clave o certificado para firmar otros binarios.
La edición EXE de GitHub continuaría sin firma mientras no exista otro proveedor.
La aprobación depende de la certificación de la aplicación.

Fuentes:

- [Registro y tipos de cuenta](https://learn.microsoft.com/en-us/windows/apps/publish/partner-center/open-a-developer-account)
- [Firma gratuita exclusivamente en la vía MSIX de la tienda](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options)
- [Registro gratuito y servicios incluidos](https://blogs.windows.com/windowsdeveloper/2025/09/10/free-developer-registration-for-individual-developers-on-microsoft-store/)

## Adaptaciones concretas de Faro por comprobar

Faro se empaqueta actualmente con PyInstaller y un instalador Inno Setup; esto
no constituye un MSIX. No se ha cambiado el comportamiento de la aplicación
durante esta investigación.

1. Reservar la identidad de producto en Partner Center y usar el Publisher e
   Identity asignados en el manifiesto; no inventar una identidad de producción.
2. Empaquetar la aplicación Win32 y sus dependencias Qt, PDFium y OCR como MSIX.
3. Declarar la asociación .pdf y comprobar «Abrir con», doble clic y argumentos
   con espacios sin cambiar a la fuerza el lector predeterminado.
4. Separar el canal de actualizaciones: la edición de tienda debe usar el canal
   de Microsoft, sin intentar reemplazarse mediante el instalador EXE de GitHub.
   Hoy updates.py y update_service.py implementan ese canal EXE.
5. Verificar rutas de datos temporales y configuración fuera del directorio de
   instalación, apertura/guardado en carpetas elegidas por el usuario, impresión,
   portapapeles y ejecución del proceso OCR dentro de una instalación MSIX real.
6. Preparar ficha, capturas sintéticas, soporte, privacidad y avisos de licencias;
   ejecutar las regresiones e instalar/actualizar/desinstalar en un entorno de
   prueba antes de enviar a certificación.

Referencias técnicas:

- [Preparar una aplicación de escritorio](https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-prepare)
- [Comportamiento de aplicaciones empaquetadas](https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-behind-the-scenes)
- [Asociaciones y extensiones](https://learn.microsoft.com/en-us/windows/apps/desktop/modernize/desktop-to-uwp-extensions)

## Alternativas examinadas

- **SignPath Foundation:** solicitud rechazada por visibilidad insuficiente,
  según el mensaje comunicado por el mantenedor. Es posible volver a solicitar
  cuando exista más adopción; no se presupone aprobación futura.
- **Necessary Code Signing:** ofrece firma gratuita, pero limita su servicio a
  herramientas abiertas consolidadas y ampliamente utilizadas. La aceptación
  de Faro no está confirmada. [Condiciones](https://sign.necessary.nu/).
- **Certum Open Source:** el catálogo oficial muestra precios desde 25 EUR;
  por tanto no cumple el presupuesto cero. El coste final depende del producto
  e infraestructura. [Catálogo](https://www.certum.eu/en/code-signing-certificates/).
- **Certificado autofirmado:** útil para desarrollo o equipos administrados;
  no equivale a confianza pública ni resuelve Smart App Control para todos los
  usuarios. No se instalarán certificados raíz ni se cambiarán las protecciones
  de Windows como parte de esta investigación.

La firma de paquetes, la reputación SmartScreen y el antivirus son mecanismos
distintos. Que una instalación funcione después de cambiar una protección no
demuestra que el archivo haya adquirido firma o confianza pública.
