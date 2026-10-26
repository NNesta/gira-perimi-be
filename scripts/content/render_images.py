"""Render every embedded image region of the Q&A PDF to WebP and build labelled contact sheets."""
import json
import os
import sys

import pymupdf
from PIL import Image, ImageDraw

pdf_path, out_dir = sys.argv[1], sys.argv[2]
doc = pymupdf.open(pdf_path)
draft = json.load(open(f"{out_dir}/qa_draft.json"))
img_dir = os.path.join(out_dir, "imgs")
os.makedirs(img_dir, exist_ok=True)

thumbs = []
for qi, q in enumerate(draft):
    for k, im in enumerate(q["images"]):
        page = doc[im["page"] - 1]
        rect = pymupdf.Rect(im["x0"], im["y0"], im["x1"], im["y1"])
        pix = page.get_pixmap(clip=rect, dpi=220)
        name = f"q{qi:03d}_{k}.png"
        path = os.path.join(img_dir, name)
        pix.save(path)
        thumbs.append((qi, q["num"], k, path, im))

# contact sheets
cell_w, cell_h = 260, 230
cols = 6
per_sheet = 36
for s in range(0, len(thumbs), per_sheet):
    chunk = thumbs[s : s + per_sheet]
    rows = (len(chunk) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (qi, num, k, path, im) in enumerate(chunk):
        img = Image.open(path).convert("RGB")
        img.thumbnail((cell_w - 10, cell_h - 40))
        x = (i % cols) * cell_w
        y = (i // cols) * cell_h
        sheet.paste(img, (x + 5, y + 30))
        draw.text((x + 5, y + 5), f"#{qi} Q{num} img{k} p{im['page']}", fill="black")
        draw.rectangle([x, y, x + cell_w - 1, y + cell_h - 1], outline="#999")
    sheet.save(os.path.join(out_dir, f"sheet_{s // per_sheet}.png"))
print("images", len(thumbs), "sheets", (len(thumbs) + per_sheet - 1) // per_sheet)
