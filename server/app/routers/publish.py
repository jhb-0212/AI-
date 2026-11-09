from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import builder
from ..config import ADMIN_PUBLIC_URL, PUBLIC_SITE_URL
from ..db import get_db
from ..models import Album, Chapter, Doing, Note, Novel, Photo, Post, Track
from ..render import clear_gallery_orphans, render_all
from ..schemas import BuildStatus, PublishIn
from ..security import current_user

router = APIRouter(prefix="/api/publish", tags=["publish"], dependencies=[Depends(current_user)])


@router.post("", status_code=202)
def publish(payload: PublishIn, db: Session = Depends(get_db)):
    """把库里的内容写成仓库文件，然后开始构建。"""
    if builder.is_running():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="上一次构建还没结束，等一下再点")
    rendered = render_all(db)
    cleared = clear_gallery_orphans(db)
    state = builder.start(git_commit=payload.git_commit, message=payload.message)
    return {"render": rendered, "cleared_orphans": cleared, "build": state}


@router.get("/status", response_model=BuildStatus)
def build_status():
    return BuildStatus(**builder.status())


@router.get("/preview")
def preview_links():
    """后台里那几个「去站点看看」的链接，域名换了只改环境变量。"""
    return {"site": PUBLIC_SITE_URL, "admin": ADMIN_PUBLIC_URL}


stats_router = APIRouter(prefix="/api/stats", tags=["stats"], dependencies=[Depends(current_user)])


@stats_router.get("")
def stats(db: Session = Depends(get_db)):
    def count(model) -> int:
        return db.scalar(select(func.count()).select_from(model)) or 0

    photos = count(Photo)
    drafts = (db.scalar(select(func.count()).select_from(Post).where(Post.draft.is_(True))) or 0) + (
        db.scalar(select(func.count()).select_from(Note).where(Note.draft.is_(True))) or 0
    )

    # 仪表盘：把「最近改了什么、还有什么没发、标签怎么分布」直接算好给前端
    items: list[dict] = []
    for p in db.scalars(select(Post)).all():
        items.append(
            {"kind": "文章", "title": p.title, "slug": p.slug, "date": p.date, "tag": p.tag, "draft": p.draft}
        )
    for n in db.scalars(select(Note)).all():
        text = (n.body or "").strip().replace("\n", " ")
        items.append(
            {
                "kind": "随记",
                "title": text[:28] + ("…" if len(text) > 28 else "") or "（空随记）",
                "slug": n.slug,
                "date": n.date,
                "tag": n.tag or "",
                "draft": n.draft,
            }
        )
    for c in db.scalars(select(Chapter)).all():
        items.append(
            {
                "kind": "章节",
                "title": f"{c.novel_slug} / {c.title}",
                "slug": c.slug,
                "date": c.date,
                "tag": "",
                "draft": c.draft,
            }
        )
    for w in db.scalars(select(Novel)).all():
        items.append(
            {"kind": "作品", "title": w.title, "slug": w.slug, "date": w.updated, "tag": w.status, "draft": w.draft}
        )

    items.sort(key=lambda x: (str(x["date"]), x["title"]), reverse=True)

    tags: dict[str, int] = {}
    for p in db.scalars(select(Post)).all():
        if p.tag:
            tags[p.tag] = tags.get(p.tag, 0) + 1

    return {
        "posts": count(Post),
        "notes": count(Note),
        "novels": count(Novel),
        "chapters": count(Chapter),
        "albums": count(Album),
        "photos": photos,
        "tracks": count(Track),
        "doing": count(Doing),
        "drafts": drafts,
        "draft_items": [x for x in items if x["draft"]][:20],
        "recent": items[:8],
        "tags": sorted(tags.items(), key=lambda kv: (-kv[1], kv[0]))[:8],
        "builds": builder.history(),
        "build": builder.status(),
        "urls": {"site": PUBLIC_SITE_URL, "admin": ADMIN_PUBLIC_URL},
    }
