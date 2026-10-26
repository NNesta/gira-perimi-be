"""Static learning content: question bank, lessons and road signs, loaded once per process."""

import json
import random
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.services.lesson_parser import parse_lesson

APP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = APP_DIR / "data"
LESSONS_DIR = APP_DIR / "content" / "lessons"

QUESTION_MEDIA = "/media/questions/"
SIGN_MEDIA = "/media/signs/"

TOPICS: list[dict] = [
    {
        "id": "ibyapa",
        "name": "Ibyapa byo ku muhanda",
        "description": "Ibyapa biburira, ibibuza, ibitegeka n’ibiyobora.",
        "icon": "triangle-alert",
    },
    {
        "id": "ibimenyetso",
        "name": "Amatara n’imirongo yo mu muhanda",
        "description": "Ibimenyetso bimurika, iby’umupolisi n’imirongo iri mu muhanda.",
        "icon": "traffic-cone",
    },
    {
        "id": "gutambuka-mbere",
        "name": "Gutambuka mbere",
        "description": "Inkomane, amasangano n’uwo uha inzira.",
        "icon": "split",
    },
    {
        "id": "kunyuranaho",
        "name": "Kubisikana no kunyuranaho",
        "description": "Uko unyura ku bindi binyabiziga n’uko ubisikana na byo.",
        "icon": "arrow-left-right",
    },
    {
        "id": "umuvuduko",
        "name": "Umuvuduko",
        "description": "Umuvuduko ntarengwa n’intera hagati y’ibinyabiziga.",
        "icon": "gauge",
    },
    {
        "id": "guhagarara",
        "name": "Guhagarara",
        "description": "Guhagarara umwanya muto n’umwanya munini.",
        "icon": "square-parking",
    },
    {
        "id": "amatara",
        "name": "Amatara n’ihoni",
        "description": "Amatara y’ikinyabiziga, ihoni n’imburira zimurika.",
        "icon": "lightbulb",
    },
    {
        "id": "ibinyabiziga",
        "name": "Ikinyabiziga",
        "description": "Ibipimo, imizigo, feri n’ibikoresho by’ikinyabiziga.",
        "icon": "truck",
    },
    {
        "id": "abagenzi",
        "name": "Abagenzi bihariye",
        "description": "Abanyamaguru, amagare, moto, amatungo n’abagenzi.",
        "icon": "footprints",
    },
    {
        "id": "imyitwarire",
        "name": "Imyitwarire n’ibyangombwa",
        "description": "Amategeko rusange, impanuka, uruhushya n’ibyangombwa.",
        "icon": "shield-check",
    },
]
TOPIC_IDS = {t["id"] for t in TOPICS}


@dataclass(frozen=True, slots=True)
class Option:
    text: str
    image: str | None


@dataclass(frozen=True, slots=True)
class Question:
    id: int
    ref: str
    text: str
    image: str | None
    options: tuple[Option, ...]
    answer: int | None
    topic: str
    active: bool
    note: str | None


class ContentStore:
    def __init__(self, data_dir: Path = DATA_DIR, lessons_dir: Path = LESSONS_DIR) -> None:
        raw_questions = json.loads((data_dir / "questions.json").read_text(encoding="utf-8"))
        self.questions: dict[int, Question] = {}
        for q in raw_questions:
            if q["topic"] not in TOPIC_IDS:
                raise ValueError(f"question {q['id']} has unknown topic {q['topic']}")
            self.questions[q["id"]] = Question(
                id=q["id"],
                ref=q["ref"],
                text=q["text"],
                image=QUESTION_MEDIA + q["image"] if q["image"] else None,
                options=tuple(
                    Option(o["text"], QUESTION_MEDIA + o["image"] if o["image"] else None) for o in q["options"]
                ),
                answer=q["answer"],
                topic=q["topic"],
                active=q["active"] and q["answer"] is not None,
                note=q.get("note"),
            )
        self.active_ids: list[int] = [q.id for q in self.questions.values() if q.active]
        self.ids_by_topic: dict[str, list[int]] = {t: [] for t in TOPIC_IDS}
        for qid in self.active_ids:
            self.ids_by_topic[self.questions[qid].topic].append(qid)

        signs_data = json.loads((data_dir / "signs.json").read_text(encoding="utf-8"))
        self.sign_categories: list[dict] = signs_data["categories"]
        self.signs: list[dict] = [{**s, "image": SIGN_MEDIA + s["image"]} for s in signs_data["signs"]]
        self._signs_by_code: dict[str, list[dict]] = {}
        for sign in self.signs:
            self._signs_by_code.setdefault(sign["code"], []).append(sign)

        self.lessons: list[dict] = sorted(
            (parse_lesson(p.read_text(encoding="utf-8")) for p in sorted(lessons_dir.glob("*.md"))),
            key=lambda lesson: lesson["order"],
        )
        for lesson in self.lessons:
            self._resolve_lesson(lesson)
        self.lessons_by_slug: dict[str, dict] = {lesson["slug"]: lesson for lesson in self.lessons}
        if len(self.lessons_by_slug) != len(self.lessons):
            raise ValueError("duplicate lesson slugs")

    # ------------------------------------------------------------------ lessons
    def _resolve_lesson(self, lesson: dict) -> None:
        unknown = [t for t in lesson["topics"] if t not in TOPIC_IDS]
        if unknown:
            raise ValueError(f"lesson {lesson['slug']} has unknown topics {unknown}")

        def walk(blocks: list[dict]) -> None:
            for block in blocks:
                if block["type"] == "signs":
                    resolved = []
                    for code in block["codes"]:
                        matches = self._signs_by_code.get(code)
                        if not matches:
                            raise ValueError(f"lesson {lesson['slug']} references unknown sign {code}")
                        resolved.extend(matches)
                    block["signs"] = [
                        {"id": s["id"], "code": s["code"], "name": s["name"], "image": s["image"]} for s in resolved
                    ]
                elif block["type"] == "callout":
                    walk(block["blocks"])

        for section in lesson["sections"]:
            walk(section["blocks"])
        lesson["question_count"] = sum(len(self.ids_by_topic[t]) for t in lesson["topics"])

    # ------------------------------------------------------------------ questions
    def topic_of(self, question_id: int) -> str | None:
        q = self.questions.get(question_id)
        return q.topic if q else None

    def draw_exam(self, count: int, rng: random.Random | None = None) -> list[int]:
        """Random exam paper; never repeats a question and avoids identical stem+image pairs."""
        rng = rng or random.SystemRandom()
        pool = self.active_ids[:]
        rng.shuffle(pool)
        picked: list[int] = []
        seen: set[tuple[str, str | None]] = set()
        for qid in pool:
            q = self.questions[qid]
            key = (q.text.lower(), q.image)
            if key in seen:
                continue
            seen.add(key)
            picked.append(qid)
            if len(picked) == count:
                break
        return picked

    def sample(self, ids: list[int], count: int, rng: random.Random | None = None) -> list[int]:
        rng = rng or random.SystemRandom()
        return rng.sample(ids, min(count, len(ids)))

    def topic_list(self) -> list[dict]:
        return [
            {
                **t,
                "question_count": len(self.ids_by_topic[t["id"]]),
                "lessons": [lesson["slug"] for lesson in self.lessons if t["id"] in lesson["topics"]],
            }
            for t in TOPICS
        ]


@lru_cache
def get_content() -> ContentStore:
    return ContentStore()
