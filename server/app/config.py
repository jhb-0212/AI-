"""集中配置：路径、数据库地址、管理员凭据、构建命令。

全部可以用环境变量覆盖，方便换机器 / 换数据库，不改代码。
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

# server/app/config.py -> server/ -> 仓库根（nepenthe/）
SERVER_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = SERVER_DIR.parent

DATA_DIR = SERVER_DIR / "data"
STATIC_DIR = SERVER_DIR / "static"
DB_PATH = DATA_DIR / "nepenthe.db"

# 站点里被后台写入的那几处
CONTENT_DIR = ROOT_DIR / "src" / "content"
SRC_DATA_DIR = ROOT_DIR / "src" / "data"
GALLERY_DIR = ROOT_DIR / "public" / "gallery"
SITE_JSON = SRC_DATA_DIR / "site.data.json"
PHOTOS_JSON = SRC_DATA_DIR / "photos.data.json"

# SQLite 起步，换 PostgreSQL 只要把 DATABASE_URL 指过去（SQLAlchemy 同一套 ORM）
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH.as_posix()}")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "nepenthe-admin")

TOKEN_COOKIE = "nepenthe_admin"
TOKEN_TTL_MINUTES = int(os.getenv("TOKEN_TTL_MINUTES", "720"))

BUILD_TIMEOUT = int(os.getenv("BUILD_TIMEOUT", "300"))

# 预览站 / 发布站，后台里给个「去站点看看」的直链
SITE_PREVIEW_URL = os.getenv("SITE_PREVIEW_URL", "http://127.0.0.1:4321")

# 域名买下来之后：站点域名 + 后台域名（可以同一个域的 /admin，也可以 admin.xxx）
# 只影响后台里展示的链接和 CORS 白名单，不改变程序行为
PUBLIC_SITE_URL = os.getenv("PUBLIC_SITE_URL", SITE_PREVIEW_URL)
ADMIN_PUBLIC_URL = os.getenv("ADMIN_PUBLIC_URL", "http://127.0.0.1:8100")

# 线上走 HTTPS 时设 COOKIE_SECURE=1，登录 cookie 就只走加密连接
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"

# 允许跨域访问后台接口的来源（逗号分隔）。同域部署留空即可
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:4321,http://127.0.0.1:4321").split(",") if o.strip()]


def _load_secret() -> str:
    """签名密钥：环境变量优先，否则在 server/data/.secret 里生成一份并复用。"""
    env = os.getenv("SECRET_KEY")
    if env:
        return env
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    f = DATA_DIR / ".secret"
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    value = secrets.token_urlsafe(48)
    f.write_text(value, encoding="utf-8")
    return value


SECRET_KEY = _load_secret()
