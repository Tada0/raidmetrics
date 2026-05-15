import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from .dal.db import engine
from .dal.models import Base
from .v1.routers import battlenet_auth as battlenet_auth_v1
from .v1.routers import raid_roster as raid_roster_v1
from .v1.routers import session as session_v1
from .v1.routers import wow as wow_v1

FRONTEND_SECRET = os.getenv("FRONTEND_SECRET")


def verify_frontend(secret: str = Header(None, alias="X-Frontend-Auth")):
    if secret != FRONTEND_SECRET:
        raise HTTPException(status_code=403, detail="Not authorized")
    return True


def custom_openapi():
    html = """
This API has v1 and v2 versions. Visit their respective documentations.

<a href="http://localhost:8000/api/v1/docs">v1 Documentation</a>
<br />
<a href="http://localhost:8000/api/v2/docs">v2 Documentation</a>
"""
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Raidmetrics Portal API",
        version="1.0.0",
        description=html,
        routes=app.routes,
        servers=[],
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n" + "="*50)
    print("🐍 Raidmetrics API (Python/FastAPI)")
    print("="*50 + "\n")
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="Raidmetrics API", lifespan=lifespan)
app.openapi = custom_openapi

v1_app = FastAPI(title="Raidmetrics API v1", dependencies=[Depends(verify_frontend)])
v2_app = FastAPI(title="Raidmetrics API v2", dependencies=[Depends(verify_frontend)])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://localhost:8000", "https://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# V1
v1_router = APIRouter()
v1_auth_router = APIRouter(prefix="/auth")
v1_auth_router.include_router(battlenet_auth_v1.router, prefix="/battlenet")
v1_auth_router.include_router(session_v1.router, prefix="/session")

v1_router.include_router(v1_auth_router)
v1_router.include_router(wow_v1.router, prefix="/wow")
v1_router.include_router(raid_roster_v1.router, prefix="/raid-roster")

# Health endpoint (protected by X-Frontend-Auth)
@v1_router.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}

v1_app.include_router(v1_router)

# V2
v2_router = APIRouter()
v2_app.include_router(v2_router)

# App
app.mount("/api/v1", v1_app)
app.mount("/api/v2", v2_app)
