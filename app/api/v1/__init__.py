from fastapi import APIRouter

from app.api.v1 import admin, auth, content, exams, me, offline, practice, push, reminders, review, share, stats

api_router = APIRouter(prefix="/api/v1")
for module in (auth, content, exams, practice, review, offline, me, push, reminders, share, stats, admin):
    api_router.include_router(module.router)
