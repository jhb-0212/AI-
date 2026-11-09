from __future__ import annotations

from datetime import date as Date
from datetime import datetime as DateTime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- 登录 ----------


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class MeOut(ORM):
    username: str
    needs_password_change: bool = False


class PasswordChangeIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# ---------- 文章 ----------


class PostIn(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    date: Date
    tag: str = ""
    read_time: str = ""
    summary: str = ""
    body: str = ""
    draft: bool = False


class PostOut(ORM):
    id: int
    slug: str
    title: str
    date: Date
    tag: str
    read_time: str
    summary: str
    body: str
    draft: bool
    updated_at: DateTime


# ---------- 随记 ----------


class NoteIn(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    date: Date
    tag: str | None = None
    body: str = ""
    draft: bool = False


class NoteOut(ORM):
    id: int
    slug: str
    date: Date
    tag: str | None
    body: str
    draft: bool
    updated_at: DateTime


# ---------- 小说 ----------


class NovelIn(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    subtitle: str | None = None
    summary: str = ""
    status: Literal["筹备中", "连载中", "已完结"] = "连载中"
    tags: list[str] = Field(default_factory=list)
    updated: Date
    body: str = ""
    draft: bool = False


class NovelOut(ORM):
    id: int
    slug: str
    title: str
    subtitle: str | None
    summary: str
    status: str
    tags: list[str]
    updated: Date
    body: str
    draft: bool
    updated_at: DateTime


class ChapterIn(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    order: int = 1
    date: Date
    body: str = ""
    draft: bool = False


class ChapterOut(ORM):
    id: int
    novel_slug: str
    slug: str
    title: str
    order: int
    date: Date
    body: str
    draft: bool
    updated_at: DateTime


# ---------- 相册 ----------


class AlbumIn(BaseModel):
    slug: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    tone: Literal["mag", "vio", "cyan", "amber"] = "mag"
    note: str = ""
    sort: int = 0


class PhotoOut(ORM):
    id: int
    album_slug: str
    src: str
    caption: str
    date: Date
    span: str | None
    sort: int


class AlbumOut(ORM):
    id: int
    slug: str
    title: str
    tone: str
    note: str
    sort: int
    photos: list[PhotoOut] = Field(default_factory=list)


class PhotoPatch(BaseModel):
    caption: str | None = None
    date: Date | None = None
    span: Literal["wide", "tall"] | None = None
    sort: int | None = None


# ---------- 音乐 ----------


class TrackIn(BaseModel):
    song_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    artist: str = ""
    dur: int = 0
    why: str = ""
    sort: int = 0


class TrackOut(ORM):
    id: int
    song_id: str
    name: str
    artist: str
    dur: int
    why: str
    sort: int


# ---------- 在做的事 ----------


class DoingIn(BaseModel):
    state: str = ""
    title: str = Field(min_length=1, max_length=160)
    sub: str = ""
    note: str = ""
    note_long: str = ""
    sort: int = 0


class DoingOut(ORM):
    id: int
    state: str
    title: str
    sub: str
    note: str
    note_long: str
    sort: int


# ---------- 站点 ----------


class SiteIn(BaseModel):
    name: str = ""
    en: str = ""
    mark: str = ""
    intro: str = ""
    lead: str = ""
    desc: str = ""
    playlistId: str = ""
    musicApi: str = ""
    musicServer: str = ""
    portfolioUrl: str = ""
    backgroundImage: str = ""
    backgroundImageDim: float = 0.0
    contact: dict[str, str] = Field(default_factory=dict)
    bio: list[str] = Field(default_factory=list)
    facts: list[dict[str, str]] = Field(default_factory=list)


class SiteOut(BaseModel):
    name: str = ""
    en: str = ""
    mark: str = ""
    intro: str = ""
    lead: str = ""
    desc: str = ""
    playlistId: str = ""
    musicApi: str = ""
    musicServer: str = ""
    portfolioUrl: str = ""
    backgroundImage: str = ""
    backgroundImageDim: float = 0.0
    contact: dict[str, str] = Field(default_factory=dict)
    bio: list[str] = Field(default_factory=list)
    facts: list[dict[str, str]] = Field(default_factory=list)
    tracks: list[TrackOut] = Field(default_factory=list)
    doing: list[DoingOut] = Field(default_factory=list)


# ---------- 发布 ----------


class PublishIn(BaseModel):
    message: str | None = None
    git_commit: bool = False


class BuildStatus(BaseModel):
    state: Literal["idle", "running", "ok", "failed"] = "idle"
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    pages: str | None = None
    log: str = ""
    git: dict[str, Any] | None = None
