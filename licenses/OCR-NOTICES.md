# OCR runtime

Faro invokes Tesseract as a separate local executable. Its replaceable DLLs
remain in the same isolated directory. The binaries are unmodified files from
the upstream Windows installer; the installation and training tools are omitted.

- Tesseract 5.5.3, Apache-2.0. Copyright the Tesseract contributors.
  Source: https://github.com/tesseract-ocr/tesseract/tree/5.5.3
  Windows build: https://github.com/UB-Mannheim/tesseract
- English and Spanish tessdata_fast models, Apache-2.0, commit
  87416418657359cb625c412a48b6e1d6d41c29bd.
  Source: https://github.com/tesseract-ocr/tessdata_fast
- The upstream Windows runtime uses shared libraries built by MSYS2:
  https://github.com/msys2/MINGW-packages
  Package sources, build recipes, version history and license references:
  https://packages.msys2.org/ and https://repo.msys2.org/mingw/mingw64/

Runtime dependencies retain their own licenses, including Leptonica (BSD),
libarchive (BSD and incorporated notices), libcurl (curl license), zlib (zlib),
libpng (libpng), libjpeg-turbo (BSD/IJG), libtiff (libtiff), OpenJPEG (BSD),
libwebp (BSD), LERC (Apache-2.0), libdeflate (MIT), Brotli (MIT), bzip2 (BSD-like),
libb2 (CC0), Expat (MIT), LZ4 (BSD), XZ/liblzma (0BSD and incorporated notices),
Zstandard (BSD), giflib (MIT), libssh2 (BSD), libpsl (MIT), libidn2 (LGPLv3),
libunistring (LGPLv3), libiconv and GNU gettext runtime (LGPL),
JBIG-KIT (GPLv2 or later), GCC runtime (GPLv3 with GCC Runtime Library Exception),
and mingw-w64 winpthreads (MIT/BSD notices).

This executable communicates with Faro through temporary files. Faro's original
source remains MIT; this does not relicense any upstream component. Runtime
libraries can be replaced with ABI-compatible builds. Faro imposes no restriction
on reverse engineering to debug changes to those libraries. No system fonts or
personal documents are bundled. The small GlyphLessFont pdf.ttf is provided by
Tesseract for its invisible OCR text layer.

The exact redistributed files and SHA-256 values are in ../manifest.json.
