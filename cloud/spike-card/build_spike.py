"""Monta o projeto da prova: copia a lógica do card e embute as fontes Poppins em base64."""

import base64
import re
from pathlib import Path

ROOT = Path(r"C:\Users\Marcio\Desktop\ofertinhas")
HERE = Path(__file__).parent
SRC = HERE / "src"
SRC.mkdir(exist_ok=True)

fonts = {p.name: base64.b64encode(p.read_bytes()).decode()
         for p in sorted((ROOT / "assets" / "fonts").glob("*.ttf"))}
(SRC / "fonts.py").write_text(
    "FONTS = {\n" + "".join(f"    {name!r}: {data!r},\n" for name, data in fonts.items()) + "}\n",
    encoding="utf-8",
)

image = (ROOT / "src/ofertinhas/creative/image.py").read_text(encoding="utf-8")
image = image.replace("from ..models import Offer\n", "from models import Offer\n")
image = image.replace("from .text import brl\n", "from textfmt import brl\n")
image = image.replace("from .themes import Theme\n", "from themes import Theme\n")
image = image.replace("from .title import short_title\n", "from title import short_title\n")
image = image.replace(
    'FONTS_DIR = Path(__file__).resolve().parents[3] / "assets" / "fonts"\n',
    "from fonts import FONTS\n",
)
image = image.replace(
    "    return ImageFont.truetype(str(FONTS_DIR / name), size)\n",
    "    import base64\n    return ImageFont.truetype(io.BytesIO(base64.b64decode(FONTS[name])), size)\n",
)
image = image.replace("import httpx\n", "")
image = image[: image.index("async def fetch_product_image")]  # a foto vem pelo fetch do Worker
assert "FONTS_DIR" not in image.split("from fonts import FONTS")[1].split("def _font")[0]
(SRC / "card.py").write_text(image, encoding="utf-8")

for name in ("themes.py", "title.py"):
    (SRC / name).write_text((ROOT / "src/ofertinhas/creative" / name).read_text(encoding="utf-8"),
                            encoding="utf-8")

models = (ROOT / "src/ofertinhas/models.py").read_text(encoding="utf-8")
(SRC / "models.py").write_text(models, encoding="utf-8")

text = (ROOT / "src/ofertinhas/creative/text.py").read_text(encoding="utf-8")
brl = re.search(r"def brl\(.*?\n\n", text, re.S).group(0)
(SRC / "textfmt.py").write_text(brl, encoding="utf-8")
print("ok:", sorted(p.name for p in SRC.iterdir()), "| fontes:", list(fonts))
