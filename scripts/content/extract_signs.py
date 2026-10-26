"""Pair each sign image in the gazette annex with the caption text beside it."""
import json
import os
import sys

import pymupdf
from PIL import Image

pdf_path, out_dir = sys.argv[1], sys.argv[2]
doc = pymupdf.open(pdf_path)
img_dir = os.path.join(out_dir, "raw")
os.makedirs(img_dir, exist_ok=True)
items = []
for pno in range(3, 19):  # pages 4..19 (1-based)
    page = doc[pno]
    lines = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            text = "".join(s["text"] for s in line["spans"]).strip()
            if not text or text.startswith("Resume du Journal") or text.startswith("TEL :"):
                continue
            bold = "".join(s["text"] for s in line["spans"] if "Bold" in s["font"]).strip()
            lines.append({"bbox": pymupdf.Rect(line["bbox"]), "text": text, "bold": bold})
    infos = sorted(page.get_image_info(xrefs=True), key=lambda i: (round(i["bbox"][1] / 4), i["bbox"][0]))
    for k, info in enumerate(infos):
        bb = pymupdf.Rect(info["bbox"])
        if bb.width < 15 or bb.height < 15:
            continue
        cap = [l for l in lines if l["bbox"].x0 >= bb.x1 - 4 and l["bbox"].y1 > bb.y0 - 6 and l["bbox"].y0 < bb.y1 + 6]
        cap.sort(key=lambda l: (round(l["bbox"].y0), l["bbox"].x0))
        name = f"p{pno + 1:02d}_{k:02d}.png"
        # Use the embedded image itself (a page render would include overlapping neighbours), then
        # restore the aspect ratio it is displayed with on the page.
        pix = pymupdf.Pixmap(doc, info["xref"])
        if pix.alpha:
            pix = pymupdf.Pixmap(pix, 0)
        if pix.colorspace is None or pix.colorspace.n != 3:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        path = os.path.join(img_dir, name)
        pix.save(path)
        with Image.open(path) as im:
            target_h = max(1, round(im.width * bb.height / bb.width))
            im.convert("RGB").resize((im.width, target_h), Image.LANCZOS).save(path)
        items.append({
            "file": name, "page": pno + 1, "bbox": [round(v) for v in bb],
            "caption": " ".join(l["text"] for l in cap), "bold": " ".join(l["bold"] for l in cap if l["bold"]),
        })
json.dump(items, open(os.path.join(out_dir, "signs_raw.json"), "w"), ensure_ascii=False, indent=1)
for it in items:
    print(it["file"], it["bbox"], "|", it["caption"][:150])
