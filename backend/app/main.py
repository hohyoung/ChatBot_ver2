from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings, validate_on_startup
from app.services.logging import setup_logging
from fastapi.staticfiles import StaticFiles
from pathlib import Path


from app.router import chat
from app.router import docs
from app.router import feedback

try:
    from app.router import auth as auth_router
except Exception:
    auth_router = None


setup_logging()

app = FastAPI(
    title="chatBot_ver2",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allow_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    validate_on_startup()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "env": settings.app_env,
        "vector_collection": settings.collection_name,
        "openai_model": settings.openai_model,
    }


@app.get("/api/health", include_in_schema=False)
def api_health():
    return health()


@app.get("/")
def root():
    return {"ok": True, "service": "chatBot_ver2"}


# 정적 문서 서빙(원본 파일 공개 경로)
DOCS_DIR = Path("storage/docs")
DOCS_DIR.mkdir(parents=True, exist_ok=True)

# /static/docs/<파일명> 으로 접근 가능
app.mount("/static/docs", StaticFiles(directory=str(DOCS_DIR)), name="docs")


# 라우터 등록
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(docs.router, prefix="/api/docs", tags=["docs"])
if auth_router:
    app.include_router(auth_router.router, prefix="/api/auth", tags=["auth"])
app.include_router(feedback.router, prefix="/api/feedback", tags=["feedback"])
