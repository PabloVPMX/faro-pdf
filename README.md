# Faro PDF

**Lee y edita tus PDF en Windows, gratis y en tu equipo.**

Faro PDF nace como una alternativa de código abierto para tareas habituales
que suelen estar reservadas a editores de pago: modificar texto, trabajar con
imágenes y organizar páginas. No requiere una cuenta ni una suscripción.
La interfaz actual está en español.

> Primera versión pública preliminar. El proyecto está en desarrollo:
> trabaja sobre copias y revisa el resultado antes de usarlo.

![Faro PDF con un documento sintético, texto multilínea e imagen](docs/faro-pdf.png)

## Descargar e instalar

Para **Windows 10/11 de 64 bits**:

- [Descargar instalador de Faro PDF 1.0.2](https://github.com/PabloVPMX/faro-pdf/releases/download/v1.0.2/FaroPDF-1.0.2-Instalar.exe)
- [Descargar versión portable](https://github.com/PabloVPMX/faro-pdf/releases/download/v1.0.2/FaroPDF-1.0.2-Portable.zip)
- [Ver todas las versiones y notas](https://github.com/PabloVPMX/faro-pdf/releases)

El instalador incluye Python, Qt y PDFium; no hace falta instalarlos por
separado. Registra Faro PDF en «Abrir con» y crea accesos directos. Puedes
desinstalarlo desde Configuración de Windows. Para usarlo como lector
predeterminado, elige Faro PDF al abrir un archivo PDF con «Abrir con».
Windows conserva tu elección actual hasta que la cambies.

Para la edición portable, extrae **todo el ZIP** y ejecuta `FaroPDF.exe`.
Conserva la carpeta `_internal` junto al ejecutable.

**Firma digital:** la primera versión pública todavía no está firmada.
Windows puede mostrar advertencias o bloquearla, especialmente con Smart App
Control activo. Publicar en GitHub no elimina ese requisito. No se pide
desactivar el antivirus. Consulta nuestra [Code signing policy](CODE_SIGNING.md).

## Qué puedes hacer

- Leer PDF, navegar por páginas y ajustar el zoom.
- Editar texto nativo directamente en sus recuadros: seleccionar, añadir y
  borrar letras, escribir acentos e insertar saltos de línea.
- Conservar la fuente original cuando sus recursos permiten verificar el
  cambio; elegir otra fuente es una acción explícita.
- Añadir texto, cambiar su fuente y tamaño y mover sus cuadros.
- Insertar imágenes, moverlas, redimensionarlas desde sus bordes y borrarlas.
- Combinar varios PDF al inicio, al final o en una posición intermedia.
- Mover y borrar páginas, deshacer y rehacer, y guardar una copia.

La vista usa todo el ancho disponible. Las opciones se muestran en menús y
paneles flotantes para dejar espacio al documento.

## Uso rápido

1. Abre un PDF con el menú Archivo, arrastrándolo a la ventana o con «Abrir con».
2. Elige **Editar texto** y haz clic dentro de un recuadro.
3. **Enter** añade una línea; **Ctrl+Enter** o clic fuera aplica; **Esc** cancela.
4. En **Añadir texto**, haz clic y escribe. Usa las opciones flotantes para
   elegir el estilo y el tirador verde para mover el cuadro.
5. En **Imágenes**, arrastra la imagen o sus tiradores. Las esquinas conservan
   la proporción. El menú Edición permite insertar imágenes y organizar páginas.
6. Guarda con **Archivo → Guardar copia**. **Ctrl+Z** deshace.

## Límites actuales

- Los escaneos son imágenes: esta versión no incluye OCR.
- Algunos PDF, fuentes, transparencias y estructuras complejas pueden
  rechazar cambios para evitar alterar el resto de la página.
- No incluye todavía impresión, búsqueda, firmas digitales de documentos,
  edición de PDF con contraseña ni recomposición automática de párrafos.
- Los saltos de línea son explícitos; no hay ajuste automático al ancho de
  una columna.
- **Borrar texto no es una redacción segura.** El guardado incremental puede
  conservar revisiones anteriores dentro del archivo. No lo uses para ocultar
  información confidencial de manera irreversible.
- La firma digital de la aplicación y la firma de documentos PDF son funciones
  diferentes. Ninguna se ofrece como resuelta en esta publicación.

## Privacidad

El procesamiento de los PDF ocurre localmente. Faro PDF no incluye
telemetría, publicidad ni subida automática de documentos. Buscar una fuente
abre Google Fonts en el navegador solo cuando pulsas esa opción; importar un
TTF lee un archivo local y no lo instala en Windows.
Consulta [PRIVACY.md](PRIVACY.md).

## Compilar y contribuir

El código de Faro PDF está bajo [licencia MIT](LICENSE). Las bibliotecas
mantienen sus propias licencias, descritas en
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Consulta [BUILDING.md](BUILDING.md) para ejecutar o compilar el programa y
[CONTRIBUTING.md](CONTRIBUTING.md) para proponer mejoras. La compilación
automatizada utiliza exclusivamente documentos sintéticos de prueba.

Puedes [reportar un problema o proponer una mejora](https://github.com/PabloVPMX/faro-pdf/issues).
No adjuntes estados de cuenta, identificaciones, cotizaciones ni otros datos
personales: reproduce el caso con un PDF de ejemplo sin información sensible.

## Code signing policy

La política y el estado de la firma están en [CODE_SIGNING.md](CODE_SIGNING.md).
La firma de futuras versiones está pendiente de obtener un proveedor y de su
evaluación; no se afirma una aprobación de SignPath ni de Microsoft.
