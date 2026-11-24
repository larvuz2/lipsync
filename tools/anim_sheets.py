"""Character sheets of the two girls as stylized 3D-animated characters (fal Nano Banana Pro edit).

    python3 tools/anim_sheets.py layla                 # 2 variants from her reference crops
    python3 tools/anim_sheets.py melody <layla_sheet>  # 2 variants, styled to match the chosen Layla sheet

References: work/anim/refs/*_upper*.jpg, *_full*.jpg (crops of the v2 fragment). Output: work/anim/sheets/<name>_<k>.png
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import fal_api  # noqa: E402

STYLE = ("redesigned as a character in a high-end stylized 3D animated feature film: appealing stylized proportions, "
         "slightly larger expressive eyes, softly simplified facial features, smooth stylized skin with subtle "
         "subsurface scattering, sculpted stylized hair with clear strand clumps, soft cinematic studio lighting")
LAYOUT = ("Layout on a plain light-grey background: top row, a full-body turnaround (front, three-quarter, side "
          "profile, back) in a relaxed neutral standing pose; bottom row, five head-and-shoulders close-ups: talking "
          "with the mouth open, smiling, a sceptical raised eyebrow, laughing, surprised. Clean, evenly lit, no text, "
          "no labels, no logos, no watermark.")
CHAR = {
    "layla": ("the young woman with very long dark-brown curly hair pulled up into a high half-ponytail (the "
              "dark-haired girl in the black studded leather vest)",
              "same face shape, eyebrows, eyes, nose, mouth and smile, same light skin tone with a few freckles, same "
              "hair colour and hairstyle, small gold hoop earrings; exactly the same outfit: a black leather "
              "sleeveless vest with silver studs on the front panels, worn open over an orange-and-black floral "
              "short-sleeve blouse that continues as an orange floral skirt, a pink wristwatch and colourful woven "
              "bracelets, gold metallic platform sneakers with white soles and brown socks",
              ["layla_upper.jpg", "layla_upper2.jpg", "layla_full.jpg", "layla_full2.jpg"]),
    "melody": ("the young woman with long wavy honey-blonde hair with thin braids at the front (the blonde girl in "
               "the red plaid shirt)",
               "same face shape, eyebrows, eyes, nose, mouth and smile, same light skin tone, same hair colour and "
               "hairstyle; exactly the same outfit: a red-and-black buffalo-check flannel shirt worn open over a "
               "fitted heather-grey T-shirt, a long thin black cord necklace, black shorts, chunky black leather "
               "ankle boots with buckles",
               ["melody_upper.jpg", "melody_upper2.jpg", "melody_full.jpg"]),
}


def main():
    name = sys.argv[1]
    who, keep, refs = CHAR[name]
    urls = [fal_api.upload(f"work/anim/refs/{r}") for r in refs]
    prompt = (f"Create a professional character model sheet of {who} in these reference photos, {STYLE}. She must "
              f"stay clearly recognizable as the same person: {keep}. {LAYOUT}")
    if len(sys.argv) > 2:
        urls.append(fal_api.upload(sys.argv[2]))
        prompt += (" The last image is the model sheet of her friend from the same film: match its 3D animation art "
                   "style, rendering, proportions, lighting, background and sheet layout exactly, so both characters "
                   "belong to the same film; do not copy her face, hair or clothes.")
    res = fal_api.run("fal-ai/nano-banana-pro/edit", {"prompt": prompt, "image_urls": urls, "num_images": 2,
                                                      "aspect_ratio": "16:9", "resolution": "2K", "output_format": "png"},
                      log=lambda *a: None)
    for k, im in enumerate(res["images"]):
        fal_api.download(im["url"], f"work/anim/sheets/{name}_{k}.png")
    json.dump({"prompt": prompt, "refs": refs + sys.argv[2:3]}, open(f"work/anim/sheets/{name}.json", "w"), indent=1)
    print("saved", len(res["images"]), "sheets for", name)


if __name__ == "__main__":
    main()
