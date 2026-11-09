"""Nepenthe 内容管理系统 —— FastAPI 入口。

启动：server\\.venv\\Scripts\\python -m uvicorn app.main:app --reload --port 8000
（工作目录是 server/，这样 app 才能当包导入）

- 前台（后台管理界面）：http://127.0.0.1:8000/admin
- 接口文档：http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import ALLOWED_ORIGINS, GALLERY_DIR, PUBLIC_SITE_URL, STATIC_DIR
from .db import Base, SessionLocal, backup_database, engine
from .routers import albums, auth, content, music, novels, publish, site, visits
from .seed import seed_if_empty


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_if_empty(db)
    GALLERY_DIR.mkdir(parents=True, exist_ok=True)
    backup_database()  # 启动时自动备份数据库
    yield


app = FastAPI(
    title="Nepenthe 内容管理",
    description="忘忧居的后台：写内容、传照片、改站点文案，点一下发布，静态站重新生成。",
    version="1.0.0",
    lifespan=lifespan,
)

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# CSRF 防护：对写操作校验 Origin 头
@app.middleware("http")
async def csrf_protect(request: Request, call_next):
    method = request.method.upper()
    if method in ("POST", "PUT", "DELETE", "PATCH"):
        # 健康检查和登录接口放行
        if request.url.path in ("/api/health", "/api/auth/login"):
            return await call_next(request)
        origin = request.headers.get("origin", "")
        # 同域请求 Origin 为空或等于自身，放行
        if not origin or origin.rstrip("/") == str(request.base_url).rstrip("/"):
            return await call_next(request)
        # 允许列表里的 Origin 放行
        if origin.rstrip("/") in [o.rstrip("/") for o in ALLOWED_ORIGINS]:
            return await call_next(request)
        return JSONResponse(
            status_code=403,
            content={"detail": "CSRF 校验失败：Origin 不在允许列表"},
        )
    return await call_next(request)


app.include_router(auth.router)
app.include_router(content.router)
app.include_router(novels.router)
app.include_router(albums.router)
app.include_router(site.router)
app.include_router(publish.router)
app.include_router(publish.stats_router)
app.include_router(visits.router)
app.include_router(visits.admin_router)
app.include_router(music.router)

# 上传的图，后台里直接预览（和站点同一个目录）
app.mount("/gallery", StaticFiles(directory=str(GALLERY_DIR), check_dir=False), name="gallery")

# 管理界面本体
app.mount("/admin", StaticFiles(directory=str(STATIC_DIR), html=True), name="admin")


@app.get("/")
def index():
    return RedirectResponse("/admin/")


@app.get("/api/health")
def health():
    return {"ok": True, "app": "nepenthe-cms"}
