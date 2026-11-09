"""访客统计：站点里一个 beacon 打到 /api/hit，落到 visits 表；后台读 /api/visits 出图。

口径（写在这里，免得以后自己都记不清）：

- **PV**：每一条命中都算。同一个人同一天把同一页看两遍，是 2 次浏览。
- **UV**：`visitor = sha256(IP + UA + 当天盐)` 取前 16 位，按天去重。盐每天换，
  所以跨天不可关联；「近 7 日 UV」是这 7 天各自独立人数的和，不是七天内去重后的人数。
- bot 直接丢；`/admin`、`/api`、静态资源、后台自己的请求都不记。
- 原始 IP 不进库，也不进日志。

采集端在 `src/scripts/visit.js`（站点构建时静态注入），只在正式域名下才发。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
import time
from collections import defaultdict
from datetime import date, timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import ALLOWED_ORIGINS, ADMIN_PUBLIC_URL, PUBLIC_SITE_URL, SECRET_KEY, TRUST_PROXY
from ..db import get_db
from ..models import Visit
from ..security import current_user

_BOT = re.compile(
    r"bot|spider|crawl|scraper|curl|wget|python-requests|httpclient|headless|monitor|"
    r"preview|facebookexternalhit|slurp|bingpreview|google-inspectiontool|lighthouse",
    re.I,
)

_SKIP_PREFIX = ("/admin", "/api", "/gallery", "/pagefind", "/_astro", "/rss.xml")
_SKIP_SUFFIX = (".js", ".css", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico", ".xml", ".json", ".woff2", ".txt")

_MAX_PATH = 200
_MAX_BODY = 1024
# 同一 IP 每分钟最多这么多条，防止有人拿它当写库接口刷
_RATE_PER_MIN = 120

_hits: dict[str, list[float]] = defaultdict(list)
_hits_lock = threading.Lock()


def _origin(url: str) -> str:
    parts = urlparse(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.netloc else ""


_ALLOWED_ORIGINS = {o.rstrip("/") for o in ALLOWED_ORIGINS if o}
_ALLOWED_ORIGINS.add(_origin(PUBLIC_SITE_URL))
_ALLOWED_ORIGINS.add(_origin(ADMIN_PUBLIC_URL))
_ALLOWED_ORIGINS.discard("")


def _daily_salt(day: date) -> str:
    return hmac.new(SECRET_KEY.encode(), f"visit-{day.isoformat()}".encode(), hashlib.sha256).hexdigest()


def _visitor(ip: str, ua: str, day: date) -> str:
    raw = f"{ip}|{ua}|{_daily_salt(day)}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def _ua_family(ua: str) -> str:
    """粗分就够：不引 device-detector，正则分六七类，够仪表盘看清大致构成。"""
    low = ua.lower()
    if "iphone" in low or "ipad" in low or "ios" in low:
        base = "iOS"
    elif "android" in low:
        base = "Android"
    elif "windows" in low:
        base = "Windows"
    elif "mac os" in low or "macintosh" in low:
        base = "macOS"
    elif "linux" in low:
        base = "Linux"
    else:
        base = "其他"

    if "edg/" in low:
        return f"Edge / {base}"
    if "firefox" in low:
        return f"Firefox / {base}"
    if "chrome" in low or "chromium" in low:
        return f"Chrome / {base}"
    if "safari" in low:
        return f"Safari / {base}"
    return base


def _clean_path(raw: str) -> str:
    path = (raw or "").split("?")[0].split("#")[0][:_MAX_PATH]
    if not path.startswith("/"):
        path = "/" + path
    return path


def _is_noise(path: str) -> bool:
    if path.startswith(_SKIP_PREFIX):
        return True
    return path.lower().endswith(_SKIP_SUFFIX)


def _rate_ok(ip: str) -> bool:
    now = time.time()
    with _hits_lock:
        bucket = [t for t in _hits.get(ip, []) if now - t < 60]
        if len(bucket) >= _RATE_PER_MIN:
            _hits[ip] = bucket
            return False
        bucket.append(now)
        _hits[ip] = bucket
    return True


router = APIRouter(prefix="/api/hit", tags=["visits"])


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
async def hit(request: Request, db: Session = Depends(get_db)):
    """站点那侧每打开一个页面打一条。永远回 204，不让采集影响前台体验。

    采集端用 `sendBeacon` 发 `text/plain` 的 JSON 字符串（这样跨域也不触发预检），
    所以这里自己读原始 body 解析，不走 FastAPI 的 Body 模型。
    """
    raw = (await request.body())[:_MAX_BODY]
    try:
        payload = json.loads(raw.decode("utf-8", "ignore")) if raw else {}
    except (ValueError, UnicodeDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    # 只有在显式配置 TRUST_PROXY=1 时才信任反向代理传来的 XFF；
    # 否则用连接对端 IP，防止伪造 XFF 绕过限流 / 污染 UV 统计。
    if TRUST_PROXY:
        ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (
            request.client.host if request.client else ""
        )
    else:
        ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")[:300]

    if _BOT.search(ua):
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    origin = (request.headers.get("origin") or "").rstrip("/")
    if origin and _ALLOWED_ORIGINS and origin not in _ALLOWED_ORIGINS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="this origin is not allowed")

    if not _rate_ok(ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="too many hits")

    path = _clean_path(str(payload.get("path", "")))
    if _is_noise(path):
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    day = date.today()
    db.add(
        Visit(
            day=day,
            path=path,
            ref=str(payload.get("ref", ""))[:120],
            ua=_ua_family(ua)[:24],
            visitor=_visitor(ip, ua, day),
        )
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


admin_router = APIRouter(prefix="/api/visits", tags=["visits"], dependencies=[Depends(current_user)])


@admin_router.get("")
def summary(days: int = 30, db: Session = Depends(get_db)):
    days = max(1, min(days, 180))
    today = date.today()
    start = today - timedelta(days=days - 1)

    rows = db.execute(
        select(
            Visit.day,
            func.count().label("pv"),
            func.count(func.distinct(Visit.visitor)).label("uv"),
        )
        .where(Visit.day >= start)
        .group_by(Visit.day)
    ).all()
    by_day = {r.day: (r.pv, r.uv) for r in rows}

    series = []
    for i in range(days):
        d = start + timedelta(days=i)
        pv, uv = by_day.get(d, (0, 0))
        series.append({"day": d.isoformat(), "pv": pv, "uv": uv})

    def sum_uv(n: int) -> int:
        return sum(x["uv"] for x in series[-n:])

    top_pages = [
        {"path": r.path, "pv": r.pv}
        for r in db.execute(
            select(Visit.path, func.count().label("pv"))
            .where(Visit.day >= start)
            .group_by(Visit.path)
            .order_by(func.count().desc())
            .limit(8)
        ).all()
    ]
    top_refs = [
        {"ref": r.ref or "直接访问", "pv": r.pv}
        for r in db.execute(
            select(Visit.ref, func.count().label("pv"))
            .where(Visit.day >= start)
            .group_by(Visit.ref)
            .order_by(func.count().desc())
            .limit(8)
        ).all()
    ]
    browsers = [
        {"ua": r.ua or "其他", "pv": r.pv}
        for r in db.execute(
            select(Visit.ua, func.count().label("pv"))
            .where(Visit.day >= start)
            .group_by(Visit.ua)
            .order_by(func.count().desc())
            .limit(6)
        ).all()
    ]

    return {
        "days": days,
        "series": series,
        "today": {"pv": series[-1]["pv"], "uv": series[-1]["uv"]},
        "uv7": sum_uv(min(7, days)),
        "uv30": sum_uv(min(30, days)),
        "pv_period": sum(x["pv"] for x in series),
        "pv_total": db.scalar(select(func.count()).select_from(Visit)) or 0,
        "top_pages": top_pages,
        "top_refs": top_refs,
        "browsers": browsers,
    }
