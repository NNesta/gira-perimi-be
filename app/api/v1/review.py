from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import DB, Content, PaidUser
from app.db.base import utcnow
from app.models.review import KIND_QUESTION, KIND_SIGN
from app.schemas.content import SignOut
from app.schemas.review import ReviewQuestionOut, ReviewSessionOut, ReviewSignOut, SignRecallIn
from app.services import review as review_service
from app.services.practice import questions_out

router = APIRouter(prefix="/review", tags=["review"])


@router.get("")
async def review_session(
    db: DB, user: PaidUser, content: Content, limit: int = Query(20, ge=1, le=50)
) -> ReviewSessionOut:
    """Today's spaced review: due questions (with answers and explanations) and due signs, oldest first."""
    items = await review_service.due_items(db, user.id, content, limit)
    question_ids = [int(i.item_id) for i in items if i.kind == KIND_QUESTION]
    questions = {q.id: q for q in await questions_out(db, content, question_ids)}
    out: list[ReviewQuestionOut | ReviewSignOut] = []
    for item in items:
        if item.kind == KIND_QUESTION:
            out.append(ReviewQuestionOut(box=item.box, question=questions[int(item.item_id)]))
        else:
            out.append(ReviewSignOut(box=item.box, sign=SignOut(**content.signs_by_id[item.item_id])))
    return ReviewSessionOut(summary=await review_service.summary(db, user.id), items=out)


@router.post("/signs", status_code=status.HTTP_204_NO_CONTENT)
async def recall_sign(body: SignRecallIn, db: DB, user: PaidUser, content: Content) -> None:
    """Flashcard result for a sign: "Sinari nkizi" schedules it for review, "Nari nkizi" moves a due sign on."""
    if body.sign_id not in content.signs_by_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Icyo cyapa ntikibonetse.")
    await review_service.record(db, user.id, KIND_SIGN, [(body.sign_id, body.known, utcnow())])
    await db.commit()
