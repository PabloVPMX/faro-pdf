"""Font inventory, coverage checks and explicitly approximate raster matching."""
from dataclasses import dataclass
from functools import lru_cache
import io
import math
from pathlib import Path
import re
import winreg

from fontTools.ttLib import TTFont
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def clean_name(name):
    return re.sub(r'^[A-Z]{6}\+', '', name or '')


def key(name):
    return re.sub('[^a-z0-9]', '', clean_name(name).lower())


@dataclass(frozen=True)
class Face:
    family: str
    name: str
    path: str
    bold: bool = False
    italic: bool = False
    restricted: bool = False


@lru_cache(maxsize=256)
def read_face(path):
    with TTFont(path, lazy=True) as font:
        names = font['name']
        family = names.getBestFamilyName() or Path(path).stem
        style = names.getBestSubFamilyName() or ''
        name = names.getDebugName(4) or (family+' '+style).strip()
        os2 = font.get('OS/2')
        bold = bool(os2 and os2.usWeightClass >= 600) or 'bold' in style.lower()
        italic = 'italic' in style.lower() or 'oblique' in style.lower()
        restricted = bool(os2 and os2.fsType & 2)
    return Face(family, name, str(path), bold, italic, restricted)


@lru_cache(maxsize=128)
def coverage(path):
    with TTFont(path, lazy=True) as font:
        return frozenset((font.getBestCmap() or {}).keys())


def missing_characters(path, text):
    chars = coverage(path)
    return sorted({c for c in text if not c.isspace() and ord(c) not in chars})


def embedded_coverage(data):
    try:
        with TTFont(io.BytesIO(data), lazy=True) as font:
            cmap = font.getBestCmap()
            return frozenset(cmap.keys()) if cmap else None
    except Exception:
        return None


class Catalog:
    def __init__(self):
        self._paths = []
        self._faces = None
        for root, subkey, folder in (
            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts', Path('C:/Windows/Fonts')),
            (winreg.HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts', Path.home()/'AppData/Local/Microsoft/Windows/Fonts'),
        ):
            try:
                with winreg.OpenKey(root, subkey) as registry:
                    for i in range(winreg.QueryInfoKey(registry)[1]):
                        _, value, _ = winreg.EnumValue(registry, i)
                        path = Path(str(value))
                        if not path.is_absolute():
                            path = folder/path
                        if path.suffix.lower() == '.ttf' and path.is_file():
                            self._paths.append(str(path))
            except OSError:
                pass
        self._paths = list(dict.fromkeys(self._paths))
        # The file paths also work when Windows font enumeration is restricted.
        if not self._paths:
            self._paths = [str(p) for p in Path('C:/Windows/Fonts').glob('*.ttf')]

    @property
    def faces(self):
        if self._faces is None:
            self._faces = []
            for path in self._paths:
                try:
                    self._faces.append(read_face(path))
                except Exception:
                    continue
            self._faces.sort(key=lambda f: f.name.lower())
        return self._faces

    def add(self, path):
        face = read_face(str(Path(path).resolve()))
        if face.restricted:
            raise ValueError('Esta fuente marca la incrustación como restringida. Elige otra fuente.')
        if face.path not in [f.path for f in self.faces]:
            self._faces.append(face)
        return face

    def matching(self, name, bold=False, italic=False):
        wanted = key(name)
        # PDF Standard 14 families have Windows metric-compatible counterparts.
        alias = {'helvetica': 'arial', 'timesroman': 'timesnewroman', 'courier': 'couriernew'}
        normalized = wanted
        for _ in range(3):
            normalized = re.sub('(bolditalic|boldoblique|bold|italic|oblique|regular|psmt|mt)$', '', normalized)
        wanted = alias.get(normalized, normalized)
        matches = [f for f in self.faces if key(f.family) == wanted or key(f.name) == key(name)
                   or re.sub('(bolditalic|bold|italic|regular)$', '', key(f.name)) == wanted]
        return sorted(matches, key=lambda f: (f.bold != bold, f.italic != italic, f.restricted))

    def alternatives(self, name='', bold=False, italic=False):
        exact = self.matching(name, bold, italic)
        mono = any(n in key(name) for n in ('courier', 'mono', 'consolas'))
        serif = any(n in key(name) for n in ('times', 'serif', 'georgia', 'cambria'))
        families = ['Consolas', 'Courier New'] if mono else ['Times New Roman', 'Georgia', 'Cambria'] if serif else ['Arial', 'Segoe UI', 'Calibri', 'Aptos', 'Verdana']
        values = exact[:1]
        for family in families:
            found = self.matching(family, bold, italic)
            if found and found[0] not in values and not found[0].restricted:
                values.append(found[0])
        return values

    def raster_candidates(self):
        families = ['Arial', 'Segoe UI', 'Calibri', 'Aptos', 'Tahoma', 'Verdana', 'Trebuchet MS', 'Candara', 'Times New Roman', 'Georgia']
        candidates = []
        for family in families:
            for bold in (False, True):
                faces = self.matching(family, bold)
                if faces and faces[0] not in candidates and not faces[0].restricted:
                    candidates.append(faces[0])
        return candidates


def text_mask(text, path, size):
    font = ImageFont.truetype(path, max(4, int(size)))
    dummy = ImageDraw.Draw(Image.new('L', (1, 1)))
    box = dummy.multiline_textbbox((0, 0), text, font=font, spacing=max(1, int(size*.3)))
    image = Image.new('L', (max(1, box[2]-box[0]+6), max(1, box[3]-box[1]+6)))
    ImageDraw.Draw(image).multiline_text((3-box[0], 3-box[1]), text, fill=255, font=font, spacing=max(1, int(size*.3)))
    return image.crop(image.getbbox() or (0, 0, 1, 1))


def estimate_raster(image, text, catalog, scale=3):
    """Compare silhouette and proportions; scores are rankings, not confidence."""
    array = np.asarray(image.convert('RGB'), dtype=np.int16)
    edge = np.concatenate((array[0], array[-1], array[:, 0], array[:, -1]))
    background = np.median(edge, axis=0)
    distance = np.max(np.abs(array-background), axis=2)
    foreground = distance > 40
    mask = Image.fromarray((foreground*255).astype('uint8'))
    bounds = mask.getbbox()
    if not bounds or not text.strip():
        raise ValueError('No se detectó un bloque de texto legible en esta imagen.')
    target = mask.crop(bounds)
    pixels = array[foreground & (distance > 100)]
    color = tuple(int(v) for v in (np.median(pixels, axis=0) if len(pixels) else [13, 43, 49]))
    target_small = np.asarray(target.resize((360, 80)), dtype=float)/255
    ranked = []
    for face in catalog.raster_candidates():
        reference = text_mask(text, face.path, 100)
        aspect = reference.width/reference.height
        target_aspect = target.width/target.height
        silhouette = np.asarray(reference.resize((360, 80)), dtype=float)/255
        score = float(np.mean(np.abs(target_small-silhouette))) + .25*abs(math.log(aspect/target_aspect))
        size = 100*target.height/reference.height/scale
        ranked.append(dict(face=face, score=score, size=round(size, 2)))
    ranked.sort(key=lambda item: item['score'])
    return dict(text=text, alternatives=ranked[:5], color=color, ink_bounds=bounds,
                scale=scale, approximate=True)
