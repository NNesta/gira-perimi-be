import uuid

from tests.conftest import login
from tests.test_admin import admin_login
from tests.test_exams import seed_completed_exams

INSTRUCTOR = "mwarimu@ishuri.rw"


async def open_school(client) -> dict:
    assert (await admin_login(client)).status_code == 200
    school = (await client.post("/api/v1/admin/schools", json={"name": "  Auto-École  Kigali "})).json()
    assert school["name"] == "Auto-École Kigali"
    school = (await client.post(f"/api/v1/admin/schools/{school['id']}/instructors", json={"email": INSTRUCTOR})).json()
    assert [(i["email"], i["name"]) for i in school["instructors"]] == [(INSTRUCTOR, None)]  # not signed up yet
    return school


async def test_instructors_see_the_progress_of_learners_who_join(client, admin, db):
    school = await open_school(client)
    client.cookies.clear()

    await login(client, email=INSTRUCTOR, name="Uwimana Claudine")
    assert (await client.get("/api/v1/auth/me")).json()["instructor"] is True
    klass = await client.post(f"/api/v1/teaching/schools/{school['id']}/classes", json={"name": "Itsinda rya mbere"})
    assert klass.status_code == 201
    klass = klass.json()
    code = klass["join_code"]
    assert len(code) == 6 and code.isupper()

    keza = await login(client)
    assert (await client.get("/api/v1/auth/me")).json()["instructor"] is False
    preview = (await client.get(f"/api/v1/classes/join/{code.lower()}")).json()
    assert preview == {"name": "Itsinda rya mbere", "school": "Auto-École Kigali"}
    joined = (await client.post("/api/v1/classes/join", json={"code": f" {code[:3]}-{code[3:]} "})).json()
    assert joined["school"] == "Auto-École Kigali"
    assert [c["name"] for c in (await client.get("/api/v1/me/classes")).json()] == ["Itsinda rya mbere"]
    assert (await client.get(f"/api/v1/teaching/classes/{klass['id']}")).status_code == 404  # learners are not staff
    await seed_completed_exams(db, uuid.UUID(keza["id"]), [16] * 11)

    await login(client, email=INSTRUCTOR, name="Uwimana Claudine")
    [teaching] = (await client.get("/api/v1/teaching")).json()
    assert teaching["classes"][0]["learners"] == 1
    detail = (await client.get(f"/api/v1/teaching/classes/{klass['id']}")).json()
    [row] = detail["learners"]
    assert row["name"] == "Keza Uwase" and row["readiness"]["ready"] is True and row["exams_completed"] == 11
    report = (await client.get(f"/api/v1/teaching/classes/{klass['id']}/learners/{keza['id']}")).json()
    assert report["readiness"]["status"] == "ready" and "phone" not in report

    await login(client)  # Keza leaves: her instructor no longer sees her
    assert (await client.delete(f"/api/v1/me/classes/{klass['id']}")).status_code == 204
    await login(client, email=INSTRUCTOR, name="Uwimana Claudine")
    assert (await client.get(f"/api/v1/teaching/classes/{klass['id']}")).json()["learners"] == []

    assert (await admin_login(client)).status_code == 200
    [listed] = (await client.get("/api/v1/admin/schools")).json()
    assert listed["instructors"][0]["name"] == "Uwimana Claudine" and listed["classes"] == 1


async def test_closed_schools_and_archived_classes(client, admin):
    school = await open_school(client)
    client.cookies.clear()
    await login(client, email=INSTRUCTOR, name="Uwimana Claudine")
    klass = (await client.post(f"/api/v1/teaching/schools/{school['id']}/classes", json={"name": "Itsinda"})).json()
    archived = await client.patch(f"/api/v1/teaching/classes/{klass['id']}", json={"archived": True})
    assert archived.json()["archived"] is True
    assert (await client.get(f"/api/v1/classes/join/{klass['join_code']}")).status_code == 404  # no new learners

    await admin_login(client)
    await client.patch(f"/api/v1/admin/schools/{school['id']}", json={"active": False})
    await login(client, email=INSTRUCTOR, name="Uwimana Claudine")
    assert (await client.get("/api/v1/teaching")).json() == []
    assert (await client.get("/api/v1/auth/me")).json()["instructor"] is False
    assert (await client.get(f"/api/v1/teaching/classes/{klass['id']}")).status_code == 404
    other = await client.post(f"/api/v1/teaching/schools/{school['id']}/classes", json={"name": "Irindi"})
    assert other.status_code == 404
