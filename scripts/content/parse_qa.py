"""Parse qa_lines.json + qa_images.json into a draft question bank and an anomaly report."""
import json
import re
import sys

out_dir = sys.argv[1]
lines = json.load(open(f"{out_dir}/qa_lines.json"))
images = json.load(open(f"{out_dir}/qa_images.json"))

Q_RE = re.compile(r"^\s*(\d{1,3})\s*(?:[.)]|(?=[A-Z]))\s*(.*)$")
OPT_RE = re.compile(r"^\s*(\()?\s*([a-dA-D])\s*(\.|\))?\s*(\.)?\s*(\))?\s*(.*)$")

events = []
for ln in lines:
    t = ln["text"].strip()
    if not t or t in {"RESTRICTED", "IKINYARWANDA"}:
        continue
    if ln["y0"] < 50 and t.isdigit():
        continue
    events.append(("line", ln["page"], ln["y0"], ln["x0"], ln))
for im in images:
    events.append(("image", im["page"], im["y0"], im["x0"], im))
events.sort(key=lambda e: (e[1], round(e[2] / 3), e[3]))

questions = []
cur = None
cur_opt = None


def start_question(num, text, ln):
    global cur, cur_opt
    cur = {"num": num, "text": text.strip(), "options": [], "images": [], "page": ln["page"], "y": ln["y0"]}
    questions.append(cur)
    cur_opt = None


for kind, page, y, x, obj in events:
    if kind == "image":
        if cur is not None:
            cur["images"].append({**obj, "after_options": len(cur["options"])})
        continue
    ln = obj
    t = ln["text"].strip()
    mq = Q_RE.match(t)
    mo = OPT_RE.match(t)
    is_option = False
    if mo and mo.group(2) and (mo.group(3) or mo.group(1)):
        label = mo.group(2).lower()
        rest = mo.group(6)
        # avoid treating sentences starting with "A na B" etc as options: require explicit ) or . after the letter
        if mo.group(3) == "." and rest[:1].islower() is False and len(rest) > 0 and label in "abcd":
            is_option = True
        elif mo.group(3) == ")" or mo.group(1):
            is_option = True
        elif mo.group(3) == ".":
            is_option = True
    if mq and not is_option:
        start_question(mq.group(1), mq.group(2), ln)
        continue
    if is_option and cur is not None:
        paren = bool(mo.group(1))
        cur_opt = {
            "label": label,
            "text": mo.group(6).strip(),
            "paren": paren,
            "red": ln["red"],
            "hl": ln["highlight"],
            "green_text": ln["green_text"],
        }
        cur["options"].append(cur_opt)
        continue
    # continuation
    if cur is None:
        continue
    if cur_opt is not None:
        cur_opt["text"] = (cur_opt["text"] + " " + t).strip()
        cur_opt["red"] = max(cur_opt["red"], ln["red"])
        if ln["highlight"]:
            cur_opt["hl"] = ln["highlight"]
    else:
        cur["text"] = (cur["text"] + " " + t).strip()

# report
report = []
for i, q in enumerate(questions):
    correct = [j for j, o in enumerate(q["options"]) if o["paren"] or o["red"] > 0.5 or o["hl"] in ("green", "yellow")]
    paren = [j for j, o in enumerate(q["options"]) if o["paren"]]
    flags = []
    if len(q["options"]) != 4:
        flags.append(f"opts={len(q['options'])}")
    if len(paren) != 1:
        flags.append(f"paren={paren}")
    if len(correct) != 1:
        flags.append(f"correct={correct}")
    q["correct_candidates"] = correct
    q["flags"] = flags
    report.append(q)

json.dump(report, open(f"{out_dir}/qa_draft.json", "w"), ensure_ascii=False, indent=1)
print("questions", len(report))
nums = [q["num"] for q in report]
from collections import Counter

dups = [n for n, c in Counter(nums).items() if c > 1]
print("duplicate numbers", dups)
print("flagged", sum(1 for q in report if q["flags"]))
