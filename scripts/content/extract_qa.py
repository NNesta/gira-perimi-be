"""Dump text lines (with colour/highlight info) and image placements from the Q&A PDF."""
import json
import sys

import pymupdf

pdf_path, out_dir = sys.argv[1], sys.argv[2]
doc = pymupdf.open(pdf_path)


def rgb(c: int):
    return ((c >> 16) & 255, (c >> 8) & 255, c & 255)


def is_red(c):
    r, g, b = rgb(c)
    return r > 150 and g < 90 and b < 90


def is_green(c):
    r, g, b = rgb(c)
    return g > 120 and r < 100 and b < 120


lines_out = []
images_out = []
for pno in range(doc.page_count):
    page = doc[pno]
    # highlight rectangles (filled drawings) – green or yellow backgrounds behind answers
    highlights = []
    for d in page.get_drawings():
        fill = d.get("fill")
        if not fill:
            continue
        r, g, b = fill
        rect = d["rect"]
        if rect.width > 5 and rect.height > 4 and rect.height < 40:
            if g > 0.8 and r < 0.4 and b < 0.4:
                highlights.append(("green", rect))
            elif r > 0.8 and g > 0.8 and b < 0.4:
                highlights.append(("yellow", rect))
    td = page.get_text("dict")
    for block in td["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            text = "".join(s["text"] for s in line["spans"])
            red_chars = sum(len(s["text"].strip()) for s in spans if is_red(s["color"]))
            green_chars = sum(len(s["text"].strip()) for s in spans if is_green(s["color"]))
            total = sum(len(s["text"].strip()) for s in spans)
            bbox = pymupdf.Rect(line["bbox"])
            hl = None
            for kind, rect in highlights:
                inter = rect & bbox
                if (not inter.is_empty and inter.width > 0.4 * min(bbox.width, rect.width)
                        and inter.height > 0.6 * bbox.height):
                    hl = kind
            lines_out.append(
                {
                    "page": pno + 1,
                    "x0": round(bbox.x0, 1),
                    "y0": round(bbox.y0, 1),
                    "x1": round(bbox.x1, 1),
                    "y1": round(bbox.y1, 1),
                    "text": text,
                    "red": round(red_chars / total, 2) if total else 0,
                    "green_text": round(green_chars / total, 2) if total else 0,
                    "bold": any("Bold" in s["font"] for s in spans),
                    "highlight": hl,
                }
            )
    for info in page.get_image_info(xrefs=True):
        bb = pymupdf.Rect(info["bbox"])
        images_out.append(
            {
                "page": pno + 1,
                "xref": info["xref"],
                "x0": round(bb.x0, 1),
                "y0": round(bb.y0, 1),
                "x1": round(bb.x1, 1),
                "y1": round(bb.y1, 1),
                "width": info["width"],
                "height": info["height"],
            }
        )

with open(f"{out_dir}/qa_lines.json", "w") as f:
    json.dump(lines_out, f, ensure_ascii=False, indent=0)
with open(f"{out_dir}/qa_images.json", "w") as f:
    json.dump(images_out, f, ensure_ascii=False, indent=0)
print("pages", doc.page_count, "lines", len(lines_out), "images", len(images_out))
