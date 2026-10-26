from fastapi import APIRouter

from app.api.v1 import admin, auth, content, exams, me, practice

api_router = APIRouter(prefix="/api/v1")
for module in (auth, content, exams, practice, me, admin):
    api_router.include_router(module.router)
