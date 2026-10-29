from app.services.lesson_parser import parse_lesson

LESSON = """---
slug: test
order: 1
title: Isomo: ikigeragezo
summary: Incamake
topics: ibyapa, umuvuduko
minutes: 3
free: true
sources: Iteka · Itegeko
---

## Igice cya mbere

Umurongo wa mbere
ukomeza hano.

- a
- b

| A | B |
|---|---|
| 1 | 2 |

> [!key] Ibyo kwibuka
> - ingingo

::signs B.1
"""


def test_parse_lesson_blocks():
    lesson = parse_lesson(LESSON)
    assert lesson["title"] == "Isomo: ikigeragezo"
    assert lesson["topics"] == ["ibyapa", "umuvuduko"]
    assert lesson["sources"] == ["Iteka", "Itegeko"]
    blocks = lesson["sections"][0]["blocks"]
    assert [b["type"] for b in blocks] == ["paragraph", "list", "table", "callout", "signs"]
    assert blocks[0]["text"] == "Umurongo wa mbere ukomeza hano."
    assert blocks[2] == {"type": "table", "head": ["A", "B"], "rows": [["1", "2"]]}
    assert blocks[3]["tone"] == "key" and blocks[3]["blocks"][0]["items"] == ["ingingo"]


def test_content_store_is_consistent(content):
    assert len(content.active_ids) == 399
    assert all(content.questions[qid].answer in range(4) for qid in content.active_ids)
    assert sum(len(ids) for ids in content.ids_by_topic.values()) == len(content.active_ids)
    paper = content.draw_exam(20)
    assert len(paper) == len(set(paper)) == 20


async def test_public_content_endpoints(client):
    overview = (await client.get("/api/v1/overview")).json()
    assert overview["questions"] == 399
    assert overview["exam"] == {
        "question_count": 20,
        "duration_minutes": 20,
        "pass_mark": 12,
        "readiness_min_exams": 10,
        "readiness_min_average": 15.0,
        "readiness_recent_exams": 10,
    }

    lessons = (await client.get("/api/v1/lessons")).json()
    assert lessons[0]["slug"] == "intangiriro" and not lessons[0]["completed"]
    lesson = (await client.get("/api/v1/lessons/ibyapa")).json()
    assert lesson["previous"]["slug"] == "amagambo-y-ingenzi"
    gallery = next(b for s in lesson["sections"] for b in s["blocks"] if b["type"] == "signs")
    assert gallery["signs"][0]["image"].startswith("/media/signs/")
    assert (await client.get("/api/v1/lessons/ntaho")).status_code == 404

    signs = (await client.get("/api/v1/signs")).json()
    assert sum(c["count"] for c in signs["categories"]) == len(signs["signs"]) == 166

    sample = (await client.get("/api/v1/questions/sample", params={"count": 5})).json()
    assert len(sample) == 5 and all("answer" in q for q in sample)


async def test_media_is_served(client):
    response = await client.get("/media/signs/b-1.webp")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
