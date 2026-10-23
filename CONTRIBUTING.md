# Contribuir

Puedes reportar fallos, proponer funciones, mejorar la interfaz, traducir o
enviar pull requests. Explica el problema y cómo reproducirlo con un archivo
sintético o anonimizado. No uses documentos personales como fixtures.

Antes de un cambio, consulta los issues para evitar duplicar trabajo. Para
cambios grandes, describe primero el objetivo y el comportamiento esperado.
El mantenedor revisará las contribuciones; no se fusionan automáticamente.

Prioridades del proyecto:

- Conservar el contenido y la tipografía al modificar un bloque.
- Rechazar cambios ambiguos antes de alterar zonas no seleccionadas.
- Mantener deshacer y guardado fiables.
- Una interfaz compacta con espacio para el PDF.
- Un paquete de Windows que funcione fuera del equipo de desarrollo.

Ejecuta la prueba documentada en [BUILDING.md](BUILDING.md). Para cambios de
renderizado, compara también las zonas que no deberían cambiar. No añadas
tests que dependan de rutas o archivos privados del autor.

Al contribuir, aceptas que tus aportaciones originales se distribuyan bajo
la licencia MIT del proyecto. Las bibliotecas externas conservan sus licencias.
No se aceptan binarios de origen desconocido ni claves o credenciales.
