from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Chapter, Novel
from ..schemas import ChapterIn, ChapterOut, NovelIn, NovelOut
from ..security import current_user
from .auth import check_slug
from .content import _ensure_unique

router = APIRouter(prefix="/api/novels", tags=["novels"], dependencies=[Depends(current_user)])


@router.get("", response_model=list[NovelOut])
def list_novels(db: Session = Depends(get_db)):
    return db.scalars(select(Novel).order_by(Novel.updated.desc(), Novel.id.desc())).all()


@router.get("/{novel_id}", response_model=NovelOut)
def get_novel(novel_id: int, db: Session = Depends(get_db)):
    novel = db.get(Novel, novel_id)
    if not novel:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="作品不存在")
    return novel


@router.post("", response_model=NovelOut, status_code=201)
def create_novel(payload: NovelIn, db: Session = Depends(get_db)):
    slug = check_slug(payload.slug)
    _ensure_unique(db, Novel, slug)
    novel = Novel(**{**payload.model_dump(), "slug": slug})
    db.add(novel)
    db.commit()
    db.refresh(novel)
    return novel


@router.put("/{novel_id}", response_model=NovelOut)
def update_novel(novel_id: int, payload: NovelIn, db: Session = Depends(get_db)):
    novel = db.get(Novel, novel_id)
    if not novel:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="作品不存在")
    slug = check_slug(payload.slug)
    _ensure_unique(db, Novel, slug, exclude_id=novel_id)
    old_slug = novel.slug
    for key, value in payload.model_dump().items():
        setattr(novel, key, value)
    novel.slug = slug
    if old_slug != slug:
        # 作品改网址，章节目录跟着改，不然章节就散了
        for chapter in db.scalars(select(Chapter).where(Chapter.novel_slug == old_slug)).all():
            chapter.novel_slug = slug
    db.commit()
    db.refresh(novel)
    return novel


@router.delete("/{novel_id}", status_code=204)
def delete_novel(novel_id: int, db: Session = Depends(get_db)):
    novel = db.get(Novel, novel_id)
    if not novel:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="作品不存在")
    for chapter in db.scalars(select(Chapter).where(Chapter.novel_slug == novel.slug)).all():
        db.delete(chapter)
    db.delete(novel)
    db.commit()


# ---------- 章节 ----------


@router.get("/{novel_slug}/chapters", response_model=list[ChapterOut])
def list_chapters(novel_slug: str, db: Session = Depends(get_db)):
    return db.scalars(
        select(Chapter).where(Chapter.novel_slug == novel_slug).order_by(Chapter.order, Chapter.id)
    ).all()


@router.get("/{novel_slug}/chapters/{chapter_id}", response_model=ChapterOut)
def get_chapter(novel_slug: str, chapter_id: int, db: Session = Depends(get_db)):
    chapter = db.get(Chapter, chapter_id)
    if not chapter or chapter.novel_slug != novel_slug:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="章节不存在")
    return chapter


@router.post("/{novel_slug}/chapters", response_model=ChapterOut, status_code=201)
def create_chapter(novel_slug: str, payload: ChapterIn, db: Session = Depends(get_db)):
    slug = check_slug(payload.slug)
    exists = db.scalar(
        select(Chapter).where(Chapter.novel_slug == novel_slug, Chapter.slug == slug)
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"这个作品下已经有章节「{slug}」了")
    chapter = Chapter(**{**payload.model_dump(), "slug": slug, "novel_slug": novel_slug})
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return chapter


@router.put("/{novel_slug}/chapters/{chapter_id}", response_model=ChapterOut)
def update_chapter(novel_slug: str, chapter_id: int, payload: ChapterIn, db: Session = Depends(get_db)):
    chapter = db.get(Chapter, chapter_id)
    if not chapter or chapter.novel_slug != novel_slug:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="章节不存在")
    slug = check_slug(payload.slug)
    for key, value in payload.model_dump().items():
        setattr(chapter, key, value)
    chapter.slug = slug
    db.commit()
    db.refresh(chapter)
    return chapter


@router.delete("/{novel_slug}/chapters/{chapter_id}", status_code=204)
def delete_chapter(novel_slug: str, chapter_id: int, db: Session = Depends(get_db)):
    chapter = db.get(Chapter, chapter_id)
    if not chapter or chapter.novel_slug != novel_slug:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="章节不存在")
    db.delete(chapter)
    db.commit()
