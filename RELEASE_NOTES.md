**Faro PDF 1.6.3 corrige la coordinación del cierre y las actualizaciones.**

Una actualización podía empezar antes de que el lector hubiera terminado de liberar sus DLL. Si Faro volvía a abrirse durante la instalación, el instalador podía encontrar archivos en uso y abortar. Esta revisión separa ambas tareas.

- El coordinador espera la salida real del lector antes de instalar; usa Windows PowerShell sin cargar el runtime de Faro ni cambiar políticas de Windows.
- Se comprueba de nuevo el SHA-256 antes de ejecutar el instalador y se muestra su progreso. Faro se reabre únicamente después de que el instalador termine correctamente.
- Durante la actualización se posponen nuevos arranques. Si abres un PDF en ese momento, se conserva la solicitud para abrirlo después.
- Se evita ejecutar varios instaladores a la vez. Las otras ventanas y sus documentos no se finalizan por la fuerza.
- Las actualizaciones fallidas dejan un estado consultable y no provocan una reapertura automática de una instalación incompleta.

### Actualizar

Cierra las ventanas de Faro y ejecuta **FaroPDF-1.6.3-Instalar.exe** sobre tu instalación actual. No necesitas desinstalar. Espera a que termine el instalador antes de abrir la aplicación. Esta primera actualización desde 1.6.2 conviene hacerla con el instalador, para evitar utilizar su coordinador anterior.

- **FaroPDF-1.6.3-Portable.zip**: extrae toda la carpeta y conserva `_internal` junto a `FaroPDF.exe`.
- **SHA256SUMS.txt** y **verification.json**: integridad de los paquetes y resultados de las comprobaciones.

### Verificación

Además de las regresiones de edición, impresión, búsqueda y OCR, se prueba el coordinador real con un proceso padre vivo, un segundo arranque bloqueado antes de cargar Qt y un paquete modificado después de la primera verificación. El coordinador debe salir y liberar el bloqueo. También se abren ventanas maximizadas con la plataforma nativa de Windows y se exige la terminación real del proceso tras cerrar con diálogos, OCR y actualizaciones en curso. Estas pruebas se ejecutan desde código, con el ejecutable portátil y después de una instalación aislada.

Windows 10/11 x64. Los ejecutables siguen sin firma digital. No se incluyen documentos personales ni se modifican las protecciones de Windows.
