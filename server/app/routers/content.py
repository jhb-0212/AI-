from __future__ import annotations

import uuid
from datetime import date as date_cls

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import GALLERY_DIR
from ..db import get_db
from ..imaging import sanitize_image
from ..models import ContentVersion, Note, Post
from ..schemas import NoteIn, NoteOut, PostIn, PostOut
from ..security import current_user
from .albums import _detect_image_type
from .auth import check_slug

router = APIRouter(prefix="/api", tags=["content"], dependencies=[Depends(current_user)])

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
MAX_BYTES = 12 * 1024 * 1024


def _save_version(db: Session, content_type: str, content_id: int, title: str, body: str, snapshot: dict) -> None:
    """保存内容历史版本。每次修改前调用。"""
    version = ContentVersion(
        content_type=content_type,
        content_id=content_id,
        title=title,
        body=body,
        snapshot=snapshot,
    )
    db.add(version)
    # 每个内容最多保留 20 个版本，超出删最旧的
    versions = db.scalars(
        select(ContentVersion)
        .where(ContentVersion.content_type == content_type, ContentVersion.content_id == content_id)
        .order_by(ContentVersion.created_at.desc())
    ).all()
    for v in versions[20:]:
        db.delete(v)


# ---------- 文章 ----------


@router.get("/posts", response_model=list[PostOut])
def list_posts(db: Session = Depends(get_db)):
    return db.scalars(select(Post).order_by(Post.date.desc(), Post.id.desc())).all()


@router.get("/posts/{post_id}", response_model=PostOut)
def get_post(post_id: int, db: Session = Depends(get_db)):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="文章不存在")
    return post


def _ensure_unique(db: Session, model, slug: str, exclude_id: int | None = None) -> None:
    row = db.scalar(select(model).where(model.slug == slug))
    if row and row.id != exclude_id:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"slug「{slug}」已经被用了")


@router.post("/posts", response_model=PostOut, status_code=201)
def create_post(payload: PostIn, db: Session = Depends(get_db)):
    slug = check_slug(payload.slug)
    _ensure_unique(db, Post, slug)
    post = Post(**{**payload.model_dump(), "slug": slug})
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


@router.put("/posts/{post_id}", response_model=PostOut)
def update_post(post_id: int, payload: PostIn, db: Session = Depends(get_db)):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="文章不存在")
    # 保存旧版本
    _save_version(
        db, "post", post_id,
        title=post.title,
        body=post.body,
        snapshot={
            "slug": post.slug, "title": post.title, "date": post.date.isoformat(),
            "tag": post.tag, "read_time": post.read_time, "summary": post.summary,
            "body": post.body, "draft": post.draft,
        },
    )
    slug = check_slug(payload.slug)
    _ensure_unique(db, Post, slug, exclude_id=post_id)
    for key, value in payload.model_dump().items():
        setattr(post, key, value)
    post.slug = slug
    db.commit()
    db.refresh(post)
    return post


@router.delete("/posts/{post_id}", status_code=204)
def delete_post(post_id: int, db: Session = Depends(get_db)):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="文章不存在")
    db.delete(post)
    db.commit()


# ---------- 随记 ----------


@router.get("/notes", response_model=list[NoteOut])
def list_notes(db: Session = Depends(get_db)):
    return db.scalars(select(Note).order_by(Note.date.desc(), Note.id.desc())).all()


@router.get("/notes/{note_id}", response_model=NoteOut)
def get_note(note_id: int, db: Session = Depends(get_db)):
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="随记不存在")
    return note


@router.post("/notes", response_model=NoteOut, status_code=201)
def create_note(payload: NoteIn, db: Session = Depends(get_db)):
    slug = check_slug(payload.slug)
    _ensure_unique(db, Note, slug)
    note = Note(**{**payload.model_dump(), "slug": slug})
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.put("/notes/{note_id}", response_model=NoteOut)
def update_note(note_id: int, payload: NoteIn, db: Session = Depends(get_db)):
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="随记不存在")
    slug = check_slug(payload.slug)
    _ensure_unique(db, Note, slug, exclude_id=note_id)
    for key, value in payload.model_dump().items():
        setattr(note, key, value)
    note.slug = slug
    db.commit()
    db.refresh(note)
    return note


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int, db: Session = Depends(get_db)):
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="随记不存在")
    db.delete(note)
    db.commit()


# ---------- 内容版本历史 ----------


@router.get("/versions/{content_type}/{content_id}")
def list_versions(content_type: str, content_id: int, db: Session = Depends(get_db)):
    versions = db.scalars(
        select(ContentVersion)
        .where(ContentVersion.content_type == content_type, ContentVersion.content_id == content_id)
        .order_by(ContentVersion.created_at.desc())
    ).all()
    return [
        {
            "id": v.id,
            "title": v.title,
            "created_at": v.created_at.strftime("%Y-%m-%d %H:%M"),
            "body_preview": v.body[:200],
        }
        for v in versions
    ]


@router.get("/versions/{content_type}/{content_id}/{version_id}")
def get_version(content_type: str, content_id: int, version_id: int, db: Session = Depends(get_db)):
    v = db.get(ContentVersion, version_id)
    if not v or v.content_type != content_type or v.content_id != content_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="版本不存在")
    return {"id": v.id, "title": v.title, "body": v.body, "snapshot": v.snapshot, "created_at": v.created_at}


# ---------- 通用图片上传（文章插图用） ----------

@router.post("/upload-image", status_code=201, dependencies=[Depends(current_user)])
async def upload_image(file: UploadFile = File(...)):
    """上传图片，返回可访问的 URL，供文章/随记 Markdown 插图用。"""
    suffix = "." + (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if suffix not in ALLOWED_EXT:
        raise HTTPException(400, detail=f"只收 {', '.join(sorted(ALLOWED_EXT))} 这几种图片")

    raw = await file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(400, detail="图片超过 12MB，先压一下再传")
    if not raw:
        raise HTTPException(400, detail="文件是空的")

    real_type = _detect_image_type(raw)
    if not real_type:
        raise HTTPException(400, detail="文件不是有效的图片格式")
    if real_type == ".jpg" and suffix not in (".jpg", ".jpeg"):
        suffix = ".jpg"
    elif real_type != ".jpg" and real_type != suffix:
        suffix = real_type

    # 重编码 + 剥离 EXIF
    try:
        raw = sanitize_image(raw, suffix)
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e

    GALLERY_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex[:12]}{suffix}"
    file_path = GALLERY_DIR / name

    try:
        file_path.write_bytes(raw)
    except OSError as e:
        raise HTTPException(500, detail=f"图片保存失败：{e}") from e

    return {"url": f"/gallery/{name}", "filename": name}
