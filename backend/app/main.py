from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings, validate_on_startup
from app.services.logging import setup_logging
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# ⬇️ 라우터 “모듈”이 아니라 “router 객체”를 직접 임포트
from app.router.chat import router as chat_router
from app.router.docs import router as docs_router
from app.router.feedback import router as feedback_router
from app.router.auth import router as auth_router  # /api/auth/*
from app.router.admin import router as admin_router


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
PUBLIC_DOCS_DIR = Path("storage/docs/public")
PUBLIC_DOCS_DIR.mkdir(parents=True, exist_ok=True)

# /static/docs/<파일명> 으로 접근 가능
app.mount("/static/docs", StaticFiles(directory=str(PUBLIC_DOCS_DIR)), name="docs")

# 라우터 등록
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
app.include_router(docs_router, prefix="/api/docs", tags=["docs"])
app.include_router(feedback_router, prefix="/api/feedback", tags=["feedback"])
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
