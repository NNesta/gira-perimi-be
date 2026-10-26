"""Contact sheets of extracted sign images, labelled by file name."""
import json
import os
import sys

from PIL import Image, ImageDraw

out_dir = sys.argv[1]
items = json.load(open(os.path.join(out_dir, "signs_raw.json")))
cell_w, cell_h, cols, per = 200, 190, 8, 48
for s in range(0, len(items), per):
    chunk = items[s : s + per]
    rows = (len(chunk) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "white")
    d = ImageDraw.Draw(sheet)
    for i, it in enumerate(chunk):
        im = Image.open(os.path.join(out_dir, "raw", it["file"])).convert("RGB")
        im.thumbnail((cell_w - 10, cell_h - 30))
        x, y = (i % cols) * cell_w, (i // cols) * cell_h
        sheet.paste(im, (x + 5, y + 25))
        d.text((x + 5, y + 5), it["file"][:-4], fill="red")
        d.rectangle([x, y, x + cell_w - 1, y + cell_h - 1], outline="#bbb")
    sheet.save(os.path.join(out_dir, f"sheet_{s // per}.png"))
print(len(items))
