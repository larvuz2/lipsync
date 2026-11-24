"""Corner labels for the product-placement section, in the Melody demo's label design.

    python3 tools/pp_labels.py work/melody work/pp/labels

Left: "ORIGINAL FOOTAGE / Product placement / before", then "AI PRODUCT PLACEMENT / Product placement / after".
Right: the Phatty Acid logo (same PNG as the language demo).
"""
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))
from melody_labels import CREAM, GOLD, INK, MUTED, brand_label, fonts, spaced, spaced_len  # noqa: E402

STATES = {
    "before": ("ORIGINAL FOOTAGE", "Product placement", "before"),
    "after": ("AI PRODUCT PLACEMENT", "Product placement", "after"),
}


def label(eyebrow, name, sub, F, W=None):
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    w_eb = spaced_len(tmp, eyebrow, F["eyebrow"], 3) + 26
    w_name = tmp.textlength(name, font=F["name"]) + 18 + tmp.textlength(sub, font=F["native"])
    W = W or int(max(w_eb, w_name)) + 48
    H = 106
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, W - 1, H - 1), radius=16, fill=INK + (168,))
    d.rectangle((0, 16, 3, H - 17), fill=GOLD + (255,))
    d.ellipse((24, 26, 34, 36), fill=GOLD + (255,))
    spaced(d, (44, 20), eyebrow, F["eyebrow"], GOLD + (255,), 3)
    d.text((24, 44), name, font=F["name"], fill=CREAM + (255,))
    x = 24 + d.textlength(name, font=F["name"]) + 16
    d.text((x, 60), sub, font=F["native"], fill=MUTED + (255,))
    return im


def main():
    w, out = sys.argv[1], sys.argv[2]
    F = fonts(os.path.join(w, "fonts"))
    os.makedirs(out, exist_ok=True)
    ims = {k: label(*v, F) for k, v in STATES.items()}
    W = max(im.width for im in ims.values())  # same width so the crossfade does not jump
    for k, v in STATES.items():
        label(*v, F, W=W).save(os.path.join(out, f"pp_{k}.png"))
    brand_label(F, os.path.join(w, "fonts", "logo_cream.png")).save(os.path.join(out, "brand.png"))
    print("labels in", out)


if __name__ == "__main__":
    main()
