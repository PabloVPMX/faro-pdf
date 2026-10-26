# Code signing policy

## Estado actual

Los paquetes publicados todavía no tienen firma Authenticode. El 23 de
octubre de 2026 se envió la solicitud al programa de SignPath Foundation
para proyectos de código abierto. El 26 de octubre de 2026 el mantenedor
comunicó que **la solicitud fue rechazada por falta de trayectoria y visibilidad
públicas suficientes**. El proveedor permite volver a solicitarla cuando el
proyecto gane adopción. No hay certificado ni servicio de firma aprobado.

El código abierto y las sumas SHA-256 permiten inspeccionar y comparar
los archivos, pero no equivalen a una firma reconocida por Windows.
Un certificado autofirmado tampoco resuelve la distribución pública con
Smart App Control activo.

## Vía sin presupuesto en evaluación

La alternativa propuesta es una edición **MSIX distribuida mediante Microsoft
Store**. Microsoft documenta el registro gratuito mediante su nuevo proceso
y la firma del paquete MSIX después de la certificación. Esto no concede un
certificado reutilizable para firmar el instalador EXE de GitHub. Presentar ese
EXE directamente a la tienda tampoco incluye la firma gratuita.

Faro todavía no dispone de un paquete MSIX verificado ni de una publicación
aprobada en Microsoft Store. El registro, la verificación de identidad del
mantenedor y la revisión de Microsoft siguen siendo necesarios. El proyecto
mantiene el presupuesto adicional de cero y no ha contratado una suscripción.

Consulta la [evaluación de la vía Microsoft Store](docs/MICROSOFT_STORE.md),
las [opciones oficiales de firma](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options)
y el [registro gratuito](https://learn.microsoft.com/en-us/windows/apps/publish/partner-center/open-a-developer-account).

## Responsabilidades

- Autor, mantenedor y revisor inicial: [PabloVPMX](https://github.com/PabloVPMX).
- Aprobador de futuras solicitudes de firma: el mantenedor del proyecto.
- Las contribuciones externas requieren revisión antes de incorporarse.
- Si se aprueba un servicio de firma, sus cuentas y las de los mantenedores
  deberán cumplir sus requisitos de autenticación multifactor y aprobación.

## Proceso previsto

1. Publicar el código y los scripts de compilación del commit de la versión.
2. Compilar en un entorno limpio con dependencias fijadas.
3. Ejecutar las pruebas sintéticas sobre el código, el binario y el instalador.
4. Generar sumas SHA-256 y revisar el contenido de los paquetes.
5. Tras la aprobación del proveedor y del mantenedor, firmar exclusivamente
   los artefactos propios autorizados, sin atribuirse las bibliotecas ajenas.
6. Verificar la firma, volver a probar la instalación y publicar la versión.

No se guardarán claves privadas, PFX, tokens de firma ni contraseñas en el
repositorio. No se presentarán versiones sin firma como si estuvieran firmadas.
No se modificarán las protecciones de Windows desde la aplicación o el instalador.

Si SignPath acepta el proyecto, se actualizará esta política con la
atribución exacta, el proveedor y el flujo de aprobación correspondientes.
La elegibilidad y aceptación dependen de sus
[condiciones oficiales](https://signpath.org/terms.html), incluida la
procedencia verificable de las compilaciones y la reputación del proyecto.
