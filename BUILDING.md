# Ejecutar y compilar Faro PDF

## Requisitos

- Windows 10/11 x64.
- Python 3.12 x64.
- Git, si quieres clonar el repositorio.

```powershell
git clone https://github.com/PabloVPMX/faro-pdf.git
cd faro-pdf
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-build.txt
.\.venv\Scripts\python.exe app.py
```

Para abrir un archivo directamente:

```powershell
.\.venv\Scripts\python.exe app.py "C:\ruta\documento.pdf"
```

## Crear el ejecutable y el instalador

```powershell
& .\packaging\build.ps1
```

El script usa el Python del entorno virtual cuando existe, prepara los
recursos y licencias, crea el ejecutable con PyInstaller y descarga el
compilador oficial de Inno Setup 6.7.3 cuando no está disponible. Comprueba
su SHA-256 y su firma de origen antes de ejecutarlo. Las herramientas y
cachés quedan en `.cache/`, fuera del código publicado.

Salida en `release/`:

- `FaroPDF-1.6.5-Instalar.exe`
- `FaroPDF-1.6.5-Portable.zip`
- `SHA256SUMS.txt`
- Informes y ejemplo sintético de validación.

El instalador es por usuario y no requiere privilegios de administrador.
No cambia la elección del lector PDF predeterminado. Las DLL incompatibles
del paquete 1.0.0 se retiran al actualizar.

## Verificación

La compilación debe pasar la misma prueba en el código y en el ejecutable:

```powershell
.\.venv\Scripts\python.exe app.py --self-test .cache\validation\source.json
```

La prueba crea su propio PDF e imagen junto al informe. Comprueba texto
multilínea con acentos, fuente y tamaño, imágenes, combinación y movimiento
de páginas, deshacer, guardado, reapertura y conservación del original.
No depende de archivos privados del desarrollador.

Las pruebas de portapapeles usan el portapapeles virtual de la plataforma Qt
offscreen, aislado del portapapeles de Windows. Comprueban selección y arrastre
real con eventos de ratón, Ctrl+X/C/V, grupos, fuentes incrustadas, transparencias,
página girada, pegados repetidos, edición posterior y guardado/reapertura.

También incluyen una página con letras trazadas, un logotipo sintético y matrices
persistentes entre streams. La versión anterior rechazaba copiar esa imagen; la
regresión verifica ahora la copia exacta, los gráficos vectoriales y su movimiento,
corte, pegado y deshacer. Los casos reales se comprueban solo localmente y no se
incorporan al repositorio ni al instalador.

Después de compilar, también se comprueban el binario, los imports nativos
de Qt, la instalación y desinstalación aisladas, y la actualización sobre
restos del paquete anterior. Los archivos que se publican deben provenir
del workflow de compilación o de un árbol limpio del mismo commit.

## Publicar una compilación verificada

El workflow manual **Publish verified Windows release** recibe el ID de una
compilación correcta y su SHA exacto. Comprueba la identidad del workflow,
el informe, los cuatro archivos y sus sumas SHA-256 antes de publicar.
La versión se obtiene del informe, sin editar el workflow en cada entrega.

La etiqueta debe apuntar al commit compilado. Primero se verifica o crea esa
etiqueta; después se usa la rama predeterminada como `target_commitish` de la
publicación. GitHub ignora ese campo para crear una etiqueta que ya existe,
pero lo utiliza al comprobar el permiso de modificar workflows. Este orden
evita el HTTP 403 sin un PAT ni permisos adicionales para `GITHUB_TOKEN`.
Si se necesita una etiqueta nueva y los workflows del commit compilado ya
difieren de la rama predeterminada, se exige compilar la rama actual antes
de escribir nada. Véase la [documentación de la API de releases](https://docs.github.com/en/rest/releases/releases#create-a-release).

Repetir una publicación verifica los archivos públicos existentes y conserva
sus contenidos. Un archivo distinto provoca un error; no se reemplaza.
Los envíos nuevos se completan en borrador antes de hacerlos públicos.
Las regresiones del publicador se ejecutan sin red con:

```powershell
python -m unittest discover -s tests -p test_publish_verified.py -v
```

## Dependencias reemplazables

Qt y sus bindings se distribuyen como DLL/PYD separados en `_internal`.
Puedes reemplazarlos por versiones compatibles o ejecutar el código con
tu propia compilación de las bibliotecas. El código fuente, las instrucciones
y las licencias permiten reconstruir la aplicación sin una clave del autor.
Consulta [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Las fuentes de Windows no se redistribuyen. Faro usa las instaladas en el
equipo y las incrustadas en el PDF, con las comprobaciones correspondientes.
