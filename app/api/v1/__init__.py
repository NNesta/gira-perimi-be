from fastapi import APIRouter

from app.api.v1 import admin, auth, content, exams, me, offline, practice, reminders, review

api_router = APIRouter(prefix="/api/v1")
for module in (auth, content, exams, practice, review, offline, me, reminders, admin):
    api_router.include_router(module.router)
