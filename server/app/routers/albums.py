from __future__ import annotations

import uuid
from datetime import date as date_cls
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import GALLERY_DIR
from ..db import get_db
from ..imaging import sanitize_image
from ..models import Album, Photo
from ..render import delete_gallery_file
from ..schemas import AlbumIn, AlbumOut, PhotoOut, PhotoPatch
from ..security import current_user
from .auth import check_slug

router = APIRouter(prefix="/api", tags=["albums"], dependencies=[Depends(current_user)])

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
MAX_BYTES = 12 * 1024 * 1024

# 真实图片格式校验：文件头 magic number
IMAGE_MAGIC = {
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG\r\n\x1a\n": ".png",
    b"RIFF": ".webp",  # 还需要后面 4 字节是 WEBP
    b"GIF87a": ".gif",
    b"GIF89a": ".gif",
    b"RIFF": ".webp",
}


def _detect_image_type(raw: bytes) -> str | None:
    """读文件头判断真实图片格式，返回后缀（小写带点）。"""
    if len(raw) < 12:
        return None
    if raw[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return ".webp"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    # AVIF 简单判断 ftyp box
    if raw[4:8] == b"ftyp" and raw[8:12] == b"avif":
        return ".avif"
    return None


def _album_out(db: Session, album: Album) -> AlbumOut:
    photos = db.scalars(
        select(Photo).where(Photo.album_slug == album.slug).order_by(Photo.sort, Photo.id)
    ).all()
    return AlbumOut(
        id=album.id,
        slug=album.slug,
        title=album.title,
        tone=album.tone,
        note=album.note,
        sort=album.sort,
        photos=[PhotoOut.model_validate(p) for p in photos],
    )


@router.get("/albums", response_model=list[AlbumOut])
def list_albums(db: Session = Depends(get_db)):
    albums = db.scalars(select(Album).order_by(Album.sort, Album.id)).all()
    return [_album_out(db, a) for a in albums]


@router.post("/albums", response_model=AlbumOut, status_code=201)
def create_album(payload: AlbumIn, db: Session = Depends(get_db)):
    slug = check_slug(payload.slug)
    if db.scalar(select(Album).where(Album.slug == slug)):
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"相册「{slug}」已经存在")
    album = Album(**{**payload.model_dump(), "slug": slug})
    db.add(album)
    db.commit()
    db.refresh(album)
    return _album_out(db, album)


@router.put("/albums/{album_id}", response_model=AlbumOut)
def update_album(album_id: int, payload: AlbumIn, db: Session = Depends(get_db)):
    album = db.get(Album, album_id)
    if not album:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="相册不存在")
    new_slug = check_slug(payload.slug)
    if new_slug != album.slug:
        if db.scalar(select(Album).where(Album.slug == new_slug)):
            raise HTTPException(status.HTTP_409_CONFLICT, detail=f"相册「{new_slug}」已经存在")
        for photo in db.scalars(select(Photo).where(Photo.album_slug == album.slug)).all():
            photo.album_slug = new_slug
    for key, value in payload.model_dump().items():
        setattr(album, key, value)
    album.slug = new_slug
    db.commit()
    db.refresh(album)
    return _album_out(db, album)


@router.delete("/albums/{album_id}", status_code=204)
def delete_album(album_id: int, db: Session = Depends(get_db)):
    album = db.get(Album, album_id)
    if not album:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="相册不存在")
    for photo in db.scalars(select(Photo).where(Photo.album_slug == album.slug)).all():
        delete_gallery_file(photo.src)
        db.delete(photo)
    db.delete(album)
    db.commit()


@router.post("/albums/{album_slug}/photos", response_model=PhotoOut, status_code=201)
async def upload_photo(
    album_slug: str,
    file: UploadFile = File(...),
    caption: str = Form(""),
    date: str | None = Form(None),
    span: str | None = Form(None),
    db: Session = Depends(get_db),
):
    album = db.scalar(select(Album).where(Album.slug == album_slug))
    if not album:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="相册不存在")

    suffix = "." + (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if suffix not in ALLOWED_EXT:
        raise HTTPException(400, detail=f"只收 {', '.join(sorted(ALLOWED_EXT))} 这几种图片")

    raw = await file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(400, detail="图片超过 12MB，先压一下再传")
    if not raw:
        raise HTTPException(400, detail="文件是空的")

    # 校验真实图片格式
    real_type = _detect_image_type(raw)
    if not real_type:
        raise HTTPException(400, detail="文件不是有效的图片格式")
    # 后缀和真实格式不一致时，以真实格式为准（防止改后缀上传恶意文件）
    if real_type == ".jpg" and suffix not in (".jpg", ".jpeg"):
        suffix = ".jpg"
    elif real_type != ".jpg" and real_type != suffix:
        suffix = real_type

    # 重编码 + 剥离 EXIF（防 GPS 泄露、防 polyglot 文件）
    try:
        raw = sanitize_image(raw, suffix)
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e

    try:
        photo_date = date_cls.today() if not date else date_cls.fromisoformat(date)
    except ValueError:
        raise HTTPException(400, detail="日期格式要 YYYY-MM-DD") from None

    GALLERY_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex[:12]}{suffix}"
    file_path = GALLERY_DIR / name

    # 先写文件，数据库提交失败时清理文件
    try:
        file_path.write_bytes(raw)
    except OSError as e:
        raise HTTPException(500, detail=f"图片保存失败：{e}") from e

    try:
        max_sort = db.scalar(
            select(Photo.sort).where(Photo.album_slug == album_slug).order_by(Photo.sort.desc()).limit(1)
        )
        photo = Photo(
            album_slug=album_slug,
            src=f"/gallery/{name}",
            caption=caption,
            date=photo_date,
            span=span if span in ("wide", "tall") else None,
            sort=(max_sort or 0) + 1,
        )
        db.add(photo)
        db.commit()
        db.refresh(photo)
    except Exception:
        # 数据库失败，清理刚写的文件
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    return PhotoOut.model_validate(photo)


@router.patch("/photos/{photo_id}", response_model=PhotoOut)
def patch_photo(photo_id: int, payload: PhotoPatch, db: Session = Depends(get_db)):
    photo = db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="照片不存在")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(photo, key, value)
    db.commit()
    db.refresh(photo)
    return PhotoOut.model_validate(photo)


@router.delete("/photos/{photo_id}", status_code=204)
def delete_photo(photo_id: int, db: Session = Depends(get_db)):
    photo = db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="照片不存在")
    delete_gallery_file(photo.src)
    db.delete(photo)
    db.commit()
