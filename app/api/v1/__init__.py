from fastapi import APIRouter

from app.api.v1 import (
    admin,
    auth,
    challenges,
    content,
    exams,
    me,
    offline,
    practice,
    push,
    reminders,
    review,
    schools,
    share,
    stats,
)

api_router = APIRouter(prefix="/api/v1")
for module in (
    auth,
    content,
    exams,
    challenges,
    practice,
    review,
    offline,
    me,
    schools,
    push,
    reminders,
    share,
    stats,
    admin,
):
    api_router.include_router(module.router)
