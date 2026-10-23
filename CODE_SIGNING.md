# Code signing policy

## Estado actual

La versión pública inicial no tiene firma Authenticode. El autor está
preparando la evaluación de opciones para proyectos de código abierto,
incluida SignPath Foundation. **No hay una aprobación ni un certificado
concedido actualmente.**

El código abierto y las sumas SHA-256 permiten inspeccionar y comparar
los archivos, pero no equivalen a una firma reconocida por Windows.
Un certificado autofirmado tampoco resuelve la distribución pública con
Smart App Control activo.

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
