"""Build the final question bank (questions.json + WebP images) from the parsed draft.

Usage: python -I build_bank.py <out_dir> <dest_json> <dest_media_dir>
"""
import json
import os
import re
import sys
import unicodedata

from PIL import Image

out_dir, dest_json, dest_media = sys.argv[1], sys.argv[2], sys.argv[3]
draft = json.load(open(f"{out_dir}/qa_draft.json"))
os.makedirs(dest_media, exist_ok=True)

# ---------------------------------------------------------------- manual fixes
# Option images: draft index -> image index for options a, b, c, d (verified against page coordinates)
OPTION_IMAGES = {
    195: [0, 1, 3, 2],  # Q224
    205: [0, 1, 2, 3],  # Q235
    206: [0, 1, 3, 2],  # Q236
    219: [0, 1, 2, 3],  # Q249
    236: [0, 1, 2, 3],  # Q266
}
# Image laid out beside the question text was attached to the previous question.
MOVE_IMAGE = {(374, 1): 375}  # blue "straight ahead" sign belongs to Q406
# The source marks every option of Q390 as correct, so its key cannot be trusted.
INACTIVE = {359: "Igitabo cy'ibibazo kigaragaza ibisubizo byose nk'iby'ukuri; ntigikoreshwa mu bizamini."}

# Topic overrides (draft index -> topic) are filled after reviewing the automatic classification.
TOPIC_OVERRIDES: dict[int, str] = {}
if os.path.exists(f"{out_dir}/topic_overrides.json"):
    TOPIC_OVERRIDES = {int(k): v for k, v in json.load(open(f"{out_dir}/topic_overrides.json")).items()}

for (qi, k), target in MOVE_IMAGE.items():
    img = draft[qi]["images"].pop(k)
    draft[target]["images"].append(img)


def clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("'", "’").replace("`", "’")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:?])", r"\1", text)
    text = re.sub(r"([,;])(?=\S)", r"\1 ", text)
    return text


# ---------------------------------------------------------------- topics
TOPIC_RULES = [
    ("ibyapa", r"\bcyapa\b|\bibyapa\b|kanunga|cyapa"),
    ("ibimenyetso", r"umurongo|imirongo|ibimenyetso bimurika|ikimenyetso kimurika|itara ritukura rivuga|itara ry’umuhondo risobanura|itara ry’icyatsi|kimenyetso cyaka|ibice by’umuhanda byera|kimenyetso kiri mu muhanda|ikimenyetso gitanzwe|umukozi ubifi|imitemeri|ngarurarumuri|imbibi"),
    ("gutambuka-mbere", r"inkomane|isangano|amasangano|gutambuka mbere|bazenguruka|bazengurutse|uburenganzira bwo gutambuka"),
    ("kunyuranaho", r"kunyura|kunyuranaho|kubisikana|bibisikane|ibisate|igisate|nyuzweho|bakinyuzeho|uzungazunga|ugukurikiye|umukurikiye"),
    ("guhagarara", r"guhagarara akanya|guhagarara umwanya|guhagarara akanya kanini|gupariki|iparitse|guhagararwa|sitasiyo"),
    ("umuvuduko", r"umuvuduko|km\s?\d+ mu isaha|feri y’urugendo ikoreshwa"),
    ("amatara", r"\bitara\b|amatara|akagarurarumuri|utugarurarumuri|ihoni|amahoni|imburira|ndanga"),
    ("ibinyabiziga", r"romoruki|rumoruki|ubugari|uburebure|uburemere|imizigo|toni|feri|inziga|ibiziga|uturebanyuma|uduhanagura|makuzungu|imitambiko|ibizirikisho|iminyururu|ibikururwa|gukurura"),
    ("abagenzi", r"abanyamaguru|umunyamaguru|igare|velomoteri|amatungo|inyamaswa|abanyeshuri|imperekerane|ingabo|otobisi|abana|umukumbi|ingorofani|ubumuga|akanyabiziga gasunikwa|ipikipiki|umunyegare|abanyamagare"),
    ("imyitwarire", r"uruhushya|isuzum|impanuka|telefone|telephone|ubwishingizi|imisoro|umusoro|ikarita|wasinze|umukandara|ibitotsi|umunaniro|ubutabazi|inkomere|ibyangombwa|abagenzi bemewe"),
]


def classify(q: dict) -> str:
    text = q["text"].lower()
    if q["images"] and re.search(r"cyapa|ibyapa", text):
        return "ibyapa"
    for topic, pattern in TOPIC_RULES:
        if re.search(pattern, text):
            return topic
    return "imyitwarire"


# ---------------------------------------------------------------- build
bank = []
for qi, q in enumerate(draft):
    opts = q["options"]
    paren = [j for j, o in enumerate(opts) if o["paren"]]
    marked = [j for j, o in enumerate(opts) if o["red"] > 0.5 or o["hl"] in ("green", "yellow")]
    if len(paren) == 1:
        answer = paren[0]
    elif len(marked) == 1:
        answer = marked[0]
    else:
        answer = None
    qid = qi + 1
    image_name = None
    options = []
    if qi in OPTION_IMAGES:
        order = OPTION_IMAGES[qi]
        for slot, img_idx in enumerate(order):
            src = os.path.join(out_dir, "imgs", f"q{qi:03d}_{img_idx}.png")
            name = f"q{qid:03d}-{'abcd'[slot]}.webp"
            Image.open(src).convert("RGB").save(os.path.join(dest_media, name), "WEBP", quality=88, method=6)
            options.append({"text": clean(opts[slot]["text"]) if slot < len(opts) else "", "image": name})
    else:
        options = [{"text": clean(o["text"]), "image": None} for o in opts]
        if q["images"]:
            # find the rendered file for the (single) question image; moved images keep their source name
            img = q["images"][0]
            src_q = qi
            src_k = 0
            for (oq, ok), target in MOVE_IMAGE.items():
                if target == qi:
                    src_q, src_k = oq, ok
            src = os.path.join(out_dir, "imgs", f"q{src_q:03d}_{src_k}.png")
            image_name = f"q{qid:03d}.webp"
            im = Image.open(src).convert("RGB")
            if im.width > 900:
                im.thumbnail((900, 900))
            im.save(os.path.join(dest_media, image_name), "WEBP", quality=86, method=6)
    if len(options) != 4:
        raise SystemExit(f"draft #{qi} (Q{q['num']}) has {len(options)} options")
    active = qi not in INACTIVE and answer is not None
    bank.append(
        {
            "id": qid,
            "ref": q["num"],
            "text": clean(q["text"]),
            "image": image_name,
            "options": options,
            "answer": answer,
            "topic": TOPIC_OVERRIDES.get(qi, classify(q)),
            "active": active,
            "note": INACTIVE.get(qi),
        }
    )

# duplicate detection: identical stem + options => keep the first one active
seen = {}
for item in bank:
    sig = (item["text"].lower(), tuple((o["text"].lower(), o["image"] is not None) for o in item["options"]))
    if sig in seen and item["active"]:
        item["active"] = False
        item["note"] = f"Gisa neza n'ikibazo cya {seen[sig]}."
    else:
        seen.setdefault(sig, item["id"])

json.dump(bank, open(dest_json, "w"), ensure_ascii=False, indent=1)
print("questions", len(bank), "active", sum(b["active"] for b in bank))
from collections import Counter

print(Counter(b["topic"] for b in bank))
print("missing answers", [b["id"] for b in bank if b["answer"] is None])
