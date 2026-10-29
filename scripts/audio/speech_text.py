"""Turns question and explanation text into what the Kinyarwanda voice model can read aloud.

The model (facebook/mms-tts-kin) knows lower-case letters and the ASCII apostrophe, nothing else: numbers, units and
sign codes are written out in Kinyarwanda words, and punctuation becomes pauses (the text is cut into phrases).

Numbers are read as plain counting numbers ("50" -> "mirongo itanu"), without the agreement a speaker would make with
the noun; native speakers should listen and correct where it sounds wrong.
"""

import re

UNITS = ["", "rimwe", "kabiri", "gatatu", "kane", "gatanu", "gatandatu", "karindwi", "umunani", "icyenda"]
TENS = ["", "icumi", "makumyabiri", "mirongo itatu", "mirongo ine", "mirongo itanu", "mirongo itandatu",
        "mirongo irindwi", "mirongo inani", "mirongo icyenda"]  # fmt: skip
HUNDREDS = ["", "ijana", "magana abiri", "magana atatu", "magana ane", "magana atanu", "magana atandatu",
            "magana arindwi", "magana inani", "magana cyenda"]  # fmt: skip
THOUSANDS = ["", "igihumbi", "ibihumbi bibiri", "ibihumbi bitatu", "ibihumbi bine", "ibihumbi bitanu",
             "ibihumbi bitandatu", "ibihumbi birindwi", "ibihumbi umunani", "ibihumbi icyenda"]  # fmt: skip
LETTERS = {"a": "a", "b": "be", "c": "se", "d": "de", "e": "e", "f": "efu", "m": "emu"}
UNIT_WORDS = {
    "km/h": "kilometero mu isaha",
    "km": "kilometero",
    "kg": "kilogarama",
    "cm": "santimetero",
    "mm": "milimetero",
    "m": "metero",
    "t": "toni",
    "l": "litiro",
    "%": "ku ijana",
    "frw": "amafaranga y'u rwanda",
}


def _join(parts: list[str]) -> str:
    """Joins number parts with "na" ("and"), shortened to n' before a vowel: "cumi n'icyenda"."""
    words = [p for p in parts if p]
    out = words[0] if words else ""
    for word in words[1:]:
        out += f" n'{word}" if word[0] in "aeiou" else f" na {word}"
    return out


def number(n: int) -> str:
    if n == 0:
        return "zeru"
    if n >= 1_000_000:
        return " ".join(number(int(d)) for d in str(n))  # long numbers digit by digit
    thousands, rest = divmod(n, 1000)
    hundreds, rest = divmod(rest, 100)
    tens, units = divmod(rest, 10)
    thousand_words = THOUSANDS[thousands] if thousands < 10 else f"ibihumbi {number(thousands)}"
    if tens == 1:
        under_hundred = _join(["icumi" if not units else "cumi", UNITS[units]])
    else:
        under_hundred = _join([TENS[tens], UNITS[units]])
    return _join([thousand_words, HUNDREDS[hundreds], under_hundred])


def _decimal(match: re.Match) -> str:
    whole, fraction = match.group(1).replace(" ", ""), match.group(2)
    if fraction.strip("0") == "5" and len(fraction) <= 2:
        return f"{number(int(whole))} n'igice"  # 2,5 / 2,50: "two and a half"
    return f"{number(int(whole))} akitso {number(int(fraction))}"


def _measure(match: re.Match) -> str:
    return f"{UNIT_WORDS[match.group(2).lower()]} {match.group(1)}"


def normalize(text: str) -> str:
    """Speakable form of `text`: lower case, numbers and units in words, punctuation kept for phrasing."""
    t = text.replace("’", "'").replace("‘", "'").replace("ʼ", "'").replace("`", "'")
    t = t.replace("½", " n'igice").replace("³", "").replace("n°", "numero ").replace("N°", "numero ")
    # Sign codes such as B.1, C.2a, (A.22a): "icyapa" is already in the sentence, the code is read letter + number.
    t = re.sub(r"\b([A-FM])\.(\d+)([a-z]?)\b", lambda m: f"{LETTERS[m.group(1).lower()]} {m.group(2)} {m.group(3)}", t)
    # "50 km", "12 500 kg", "km 50": the unit is said first, as in Kinyarwanda ("kilometero mirongo itanu").
    t = re.sub(r"(\d[\d ,.]*)\s*(km/h|km|kg|cm|mm|m|t|l|%|frw)\b", _measure, t, flags=re.IGNORECASE)
    t = re.sub(r"(?<![\w/])(km/h|km|kg|cm|mm|frw)\.?\s*(?=\d)", lambda m: UNIT_WORDS[m.group(1).lower()] + " ", t,
               flags=re.IGNORECASE)  # fmt: skip
    t = re.sub(r"\b(\d{1,3}(?: \d{3})+)\b", lambda m: m.group(1).replace(" ", ""), t)  # 12 500 -> 12500
    t = re.sub(r"\b(\d+)[,.](\d+)\b", _decimal, t)
    t = re.sub(r"\b(\d+)/(\d+)\b", lambda m: f"{number(int(m.group(1)))} kuri {number(int(m.group(2)))}", t)
    t = re.sub(r"\d+", lambda m: number(int(m.group(0))), t)
    t = t.replace("%", " ku ijana")
    return re.sub(r"\s+", " ", t).strip().lower()


def phrases(text: str) -> list[tuple[str, float]]:
    """(phrase, pause after it in seconds): the model reads one phrase at a time, so punctuation becomes silence."""
    out = []
    for piece, mark in re.findall(r"([^.,:;?!()\"“”–]+)([.,:;?!()\"“”–]*)", normalize(text)):
        words = re.sub(r"[^a-z' -]", " ", piece)
        words = re.sub(r"\s+", " ", words).strip(" -")
        if not words:
            continue
        pause = 0.45 if any(c in mark for c in ".?!:;") else 0.22 if mark else 0.12
        out.append((words, pause))
    return out


def question_script(question: dict) -> str:
    """The question, then its answers announced by their letters as the screen shows them (a, be, se, de)."""
    parts = [question["text"].rstrip(" :") + "."]
    for letter, option in zip("abcd", question["options"], strict=False):
        parts.append(f"{LETTERS[letter]}: {option['text'] or 'ishusho'}.")
    return " ".join(parts)
