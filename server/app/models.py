from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _now() -> datetime:
    return datetime.now()


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Post(Base):
    """文章：一只 .md，文件名即网址 /writing/<slug>/。"""

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    date: Mapped[date] = mapped_column(Date)
    tag: Mapped[str] = mapped_column(String(80), default="")
    read_time: Mapped[str] = mapped_column(String(40), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    draft: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Note(Base):
    """随记：一句话或一小段。"""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    date: Mapped[date] = mapped_column(Date)
    tag: Mapped[str | None] = mapped_column(String(80), nullable=True)
    body: Mapped[str] = mapped_column(Text, default="")
    draft: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Novel(Base):
    """小说作品：一文件 = 一部作品，网址 /novels/<slug>/。"""

    __tablename__ = "novels"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    subtitle: Mapped[str | None] = mapped_column(String(240), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="连载中")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    updated: Mapped[date] = mapped_column(Date)
    body: Mapped[str] = mapped_column(Text, default="")
    draft: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Chapter(Base):
    """章节：src/content/chapters/<novel_slug>/<slug>.md"""

    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(primary_key=True)
    novel_slug: Mapped[str] = mapped_column(String(120), index=True)
    slug: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(200))
    order: Mapped[int] = mapped_column(Integer, default=1)
    date: Mapped[date] = mapped_column(Date)
    body: Mapped[str] = mapped_column(Text, default="")
    draft: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Album(Base):
    __tablename__ = "albums"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(120))
    tone: Mapped[str] = mapped_column(String(12), default="mag")
    note: Mapped[str] = mapped_column(Text, default="")
    sort: Mapped[int] = mapped_column(Integer, default=0)


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    album_slug: Mapped[str] = mapped_column(ForeignKey("albums.slug", ondelete="CASCADE"), index=True)
    src: Mapped[str] = mapped_column(String(300))
    caption: Mapped[str] = mapped_column(String(300), default="")
    date: Mapped[date] = mapped_column(Date)
    span: Mapped[str | None] = mapped_column(String(10), nullable=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(primary_key=True)
    netease_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(160))
    artist: Mapped[str] = mapped_column(String(160), default="")
    dur: Mapped[int] = mapped_column(Integer, default=0)
    why: Mapped[str] = mapped_column(String(300), default="")
    sort: Mapped[int] = mapped_column(Integer, default=0)


class Doing(Base):
    __tablename__ = "doing"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[str] = mapped_column(String(40), default="")
    title: Mapped[str] = mapped_column(String(160))
    sub: Mapped[str] = mapped_column(String(240), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    note_long: Mapped[str] = mapped_column(Text, default="")
    sort: Mapped[int] = mapped_column(Integer, default=0)


class Setting(Base):
    """站点里那些单值配置。现在只一行：key='site'，value 是一整块 JSON。"""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Visit(Base):
    """一次页面访问。站点那侧用 sendBeacon 打进来，只留聚合要用到的东西。

    不存原始 IP：visitor 是 sha256(IP + UA + 当天盐) 的前 16 位，盐每天换，
    所以跨天不可关联。path 已经去掉 query、只留路径。
    """

    __tablename__ = "visits"

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    path: Mapped[str] = mapped_column(String(200), index=True)
    ref: Mapped[str] = mapped_column(String(120), default="")
    ua: Mapped[str] = mapped_column(String(24), default="")
    visitor: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ContentVersion(Base):
    """内容历史版本：每次修改文章/随记/小说/章节前，自动保存旧版本快照。"""

    __tablename__ = "content_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_type: Mapped[str] = mapped_column(String(20), index=True)  # post / note / novel / chapter
    content_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)  # 完整字段快照
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)


__all__ = [
    "AdminUser",
    "Album",
    "Chapter",
    "ContentVersion",
    "Doing",
    "Note",
    "Novel",
    "Photo",
    "Post",
    "Setting",
    "Track",
    "Visit",
    "func",
]
