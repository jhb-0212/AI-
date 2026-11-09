"""首次启动时把仓库里现有的内容灌进数据库。

顺序：先建管理员，再按「库里是空的就导入」补齐每一类。
这样老内容一条都不丢，而且之后改成「数据库说了算」，发布时才写回文件。
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import CONTENT_DIR, PHOTOS_JSON, ADMIN_PASSWORD, ADMIN_USERNAME, SITE_JSON
from .models import AdminUser, Album, Chapter, Doing, Note, Novel, Photo, Post, Setting, Track
from .security import hash_password


def parse_markdown(text: str) -> tuple[dict, str]:
    """把 `---` 包起来的那段 YAML 和后面的正文拆开。"""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---"):
        return {}, text.strip()
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text.strip()
    meta = yaml.safe_load(parts[1]) or {}
    return meta, parts[2].lstrip("\n").strip("\n")


def _read_md(path: Path) -> tuple[dict, str]:
    return parse_markdown(path.read_text(encoding="utf-8"))


def _as_date(value) -> object:
    if hasattr(value, "isoformat"):
        return value
    return value


def seed_if_empty(db: Session) -> dict:
    report = {"user": False, "posts": 0, "notes": 0, "novels": 0, "chapters": 0, "albums": 0, "tracks": 0, "doing": 0}

    if db.scalar(select(func.count()).select_from(AdminUser)) == 0:
        db.add(AdminUser(username=ADMIN_USERNAME, password_hash=hash_password(ADMIN_PASSWORD)))
        report["user"] = True

    if db.scalar(select(func.count()).select_from(Post)) == 0:
        for path in sorted((CONTENT_DIR / "posts").glob("*.md")):
            meta, body = _read_md(path)
            db.add(
                Post(
                    slug=path.stem,
                    title=str(meta.get("title", path.stem)),
                    date=_as_date(meta.get("date")),
                    tag=str(meta.get("tag", "")),
                    read_time=str(meta.get("readTime", "")),
                    summary=str(meta.get("summary", "")),
                    body=body,
                    draft=bool(meta.get("draft", False)),
                )
            )
            report["posts"] += 1

    if db.scalar(select(func.count()).select_from(Note)) == 0:
        for path in sorted((CONTENT_DIR / "notes").glob("*.md")):
            meta, body = _read_md(path)
            tag = meta.get("tag")
            db.add(
                Note(
                    slug=path.stem,
                    date=_as_date(meta.get("date")),
                    tag=str(tag) if tag else None,
                    body=body,
                    draft=bool(meta.get("draft", False)),
                )
            )
            report["notes"] += 1

    if db.scalar(select(func.count()).select_from(Novel)) == 0:
        for path in sorted((CONTENT_DIR / "novels").glob("*.md")):
            meta, body = _read_md(path)
            db.add(
                Novel(
                    slug=path.stem,
                    title=str(meta.get("title", path.stem)),
                    subtitle=str(meta.get("subtitle", "") or ""),
                    summary=str(meta.get("summary", "")),
                    status=str(meta.get("status", "连载中")),
                    tags=list(meta.get("tags") or []),
                    updated=_as_date(meta.get("updated")),
                    body=body,
                    draft=bool(meta.get("draft", False)),
                )
            )
            report["novels"] += 1

    if db.scalar(select(func.count()).select_from(Chapter)) == 0:
        for novel_dir in sorted((CONTENT_DIR / "chapters").glob("*")):
            if not novel_dir.is_dir():
                continue
            for path in sorted(novel_dir.glob("*.md")):
                meta, body = _read_md(path)
                db.add(
                    Chapter(
                        novel_slug=novel_dir.name,
                        slug=path.stem,
                        title=str(meta.get("title", path.stem)),
                        order=int(meta.get("order", 1) or 1),
                        date=_as_date(meta.get("date")),
                        body=body,
                        draft=bool(meta.get("draft", False)),
                    )
                )
                report["chapters"] += 1

    if db.scalar(select(func.count()).select_from(Album)) == 0 and PHOTOS_JSON.exists():
        payload = json.loads(PHOTOS_JSON.read_text(encoding="utf-8"))
        for i, album in enumerate(payload.get("albums", [])):
            db.add(
                Album(
                    slug=album["id"],
                    title=album["title"],
                    tone=album.get("tone", "mag"),
                    note=album.get("note", ""),
                    sort=i,
                )
            )
            for j, photo in enumerate(album.get("photos", [])):
                db.add(
                    Photo(
                        album_slug=album["id"],
                        src=photo["src"],
                        caption=photo.get("caption", ""),
                        date=_as_date(photo.get("date")),
                        span=photo.get("span"),
                        sort=j,
                    )
                )
            report["albums"] += 1

    if SITE_JSON.exists():
        payload = json.loads(SITE_JSON.read_text(encoding="utf-8"))
        if db.get(Setting, "site") is None:
            db.add(
                Setting(
                    key="site",
                    value={
                        k: payload.get(k, "")
                        for k in (
                            "name",
                            "en",
                            "mark",
                            "intro",
                            "lead",
                            "desc",
                            "playlistId",
                            "musicApi",
                            "portfolioUrl",
                        )
                    }
                    | {
                        "contact": payload.get("contact", {}),
                        "bio": payload.get("bio", []),
                        "facts": payload.get("facts", []),
                    },
                )
            )
        if db.scalar(select(func.count()).select_from(Track)) == 0:
            for i, track in enumerate(payload.get("tracks", [])):
                db.add(
                    Track(
                        netease_id=int(track["id"]),
                        name=track["name"],
                        artist=track.get("artist", ""),
                        dur=int(track.get("dur", 0)),
                        why=track.get("why", ""),
                        sort=i,
                    )
                )
                report["tracks"] += 1
        if db.scalar(select(func.count()).select_from(Doing)) == 0:
            for i, item in enumerate(payload.get("doing", [])):
                db.add(
                    Doing(
                        state=item.get("state", ""),
                        title=item["title"],
                        sub=item.get("sub", ""),
                        note=item.get("note", ""),
                        note_long=item.get("noteLong", ""),
                        sort=i,
                    )
                )
                report["doing"] += 1

    db.commit()
    return report
