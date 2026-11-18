"""Corner labels for the Melody multi-language demo (Phatty Acid brand: near-black, cream, gold).

    python3 tools/melody_labels.py work/melody            # renders label PNGs into work/melody/labels/

Left corner: the language now playing ("Original audio" / "AI dub + lip sync" over the language name and its
native name). Right corner: the Phatty Acid logo only.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

CREAM = (245, 240, 230)
GOLD = (212, 167, 98)
MUTED = (190, 182, 168)
INK = (10, 10, 10)
LANGS = {
    "es": ("ORIGINAL AUDIO", "Spanish", "Español"),
    "en": ("AI DUB + LIP SYNC", "English", None),
    "he": ("AI DUB + LIP SYNC", "Hebrew", "עברית"),  # Pillow with raqm lays out right-to-left text itself
    "pt": ("AI DUB + LIP SYNC", "Portuguese", "Português"),
    "fr": ("AI DUB + LIP SYNC", "French", "Français"),
}


def fonts(d):
    f = lambda n, s: ImageFont.truetype(os.path.join(d, n), s)
    return {"eyebrow": f("SpaceMono-Bold.ttf", 18), "name": f("PlayfairDisplay-Bold.ttf", 40),
            "native": f("Inter-SemiBold.ttf", 23), "native_he": f("NotoSansHebrew-SemiBold.ttf", 24),
            "service": f("SpaceMono-Bold.ttf", 16)}


def spaced(draw, xy, text, font, fill, spacing):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + spacing
    return x


def spaced_len(draw, text, font, spacing):
    return sum(draw.textlength(ch, font=font) + spacing for ch in text) - spacing


def lang_label(code, F):
    eyebrow, name, native = LANGS[code]
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    w_eb = spaced_len(tmp, eyebrow, F["eyebrow"], 3) + 26
    nf = F["native_he"] if code == "he" else F["native"]
    w_name = tmp.textlength(name, font=F["name"]) + (18 + tmp.textlength(native, font=nf) if native else 0)
    W = int(max(w_eb, w_name)) + 48
    H = 106
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, W - 1, H - 1), radius=16, fill=INK + (168,))
    d.rectangle((0, 16, 3, H - 17), fill=GOLD + (255,))
    # live dot + eyebrow
    d.ellipse((24, 26, 34, 36), fill=GOLD + (255,))
    spaced(d, (44, 20), eyebrow, F["eyebrow"], GOLD + (255,), 3)
    d.text((24, 44), name, font=F["name"], fill=CREAM + (255,))
    if native:
        x = 24 + d.textlength(name, font=F["name"]) + 16
        d.text((x, 60 if code != "he" else 57), native, font=nf, fill=MUTED + (255,))
    return im


def brand_label(F, logo_path):
    """Top-right corner: the Phatty Acid logo only (the service name is on the language label)."""
    logo = Image.open(logo_path).convert("RGBA")
    lh = 62
    logo = logo.resize((round(logo.width * lh / logo.height), lh), Image.LANCZOS)
    W, H = logo.width + 40, lh + 36
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, W - 1, H - 1), radius=16, fill=INK + (168,))
    im.alpha_composite(logo, (20, 18))
    return im


def main():
    w = sys.argv[1]
    F = fonts(os.path.join(w, "fonts"))
    out = os.path.join(w, "labels")
    os.makedirs(out, exist_ok=True)
    for code in LANGS:
        lang_label(code, F).save(os.path.join(out, f"lang_{code}.png"))
    brand_label(F, os.path.join(w, "fonts", "logo_cream.png")).save(os.path.join(out, "brand.png"))
    print("labels in", out)


if __name__ == "__main__":
    main()
