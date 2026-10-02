from fastapi import APIRouter

from app.api.v1.routes import (
    admin,
    admin_system,
    auth,
    files,
    health,
    notifications,
    resumes,
    tasks,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(resumes.router)
api_router.include_router(tasks.router)
api_router.include_router(notifications.router)
api_router.include_router(files.router)
api_router.include_router(admin.router)
api_router.include_router(admin_system.router)
