from fastapi import APIRouter

from app.api.v1.routes import (
    admin,
    admin_insights,
    admin_system,
    applications,
    auth,
    automation,
    contacts,
    dashboard,
    documents,
    files,
    health,
    imports,
    integrations,
    interviews,
    jobs,
    notifications,
    outreach,
    resumes,
    saved_searches,
    tasks,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(resumes.router)
api_router.include_router(jobs.router)
api_router.include_router(documents.router)
api_router.include_router(applications.router)
api_router.include_router(contacts.router)
api_router.include_router(outreach.router)
api_router.include_router(integrations.router)
api_router.include_router(automation.router)
api_router.include_router(dashboard.router)
api_router.include_router(admin_insights.router)
api_router.include_router(imports.router)
api_router.include_router(interviews.router)
api_router.include_router(saved_searches.router)
api_router.include_router(tasks.router)
api_router.include_router(notifications.router)
api_router.include_router(files.router)
api_router.include_router(admin.router)
api_router.include_router(admin_system.router)
