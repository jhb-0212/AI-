"""把数据库里的内容渲染成仓库里的文件。

这一层是「发布」的实现：数据库是编辑时的唯一数据源，仓库里的
`src/content/**/*.md` 与 `src/data/*.json` 都是它的产物，站点构建时读的是这些文件。
所以后台挂了、数据库丢了，已经发布出去的站照旧能跑。

写过的每个文件都记在 `server/data/generated.json` 里；下次发布时，
「这次没生成、但上次生成过」的文件会被删掉，手动放进仓库的文件不受影响。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import CONTENT_DIR, DATA_DIR, PHOTOS_JSON, ROOT_DIR, SITE_JSON
from .models import Album, Chapter, Doing, Note, Novel, Photo, Post, Setting, Track

MANIFEST = DATA_DIR / "generated.json"
POSTS_DIR = CONTENT_DIR / "posts"
NOTES_DIR = CONTENT_DIR / "notes"
NOVELS_DIR = CONTENT_DIR / "novels"
CHAPTERS_DIR = CONTENT_DIR / "chapters"


def _load_manifest() -> list[str]:
    if not MANIFEST.exists():
        return []
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8")).get("files", [])
    except (json.JSONDecodeError, OSError):
        return []


def _save_manifest(files: list[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({"files": files}, ensure_ascii=False, indent=2), encoding="utf-8")


def _frontmatter(data: dict) -> str:
    body = "---\n" + yaml.dump(
        data,
        Dumper=_Dumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=4096,
    ) + "---\n"
    return body


class _Dumper(yaml.SafeDumper):
    """让列表跟着父键缩进（tags: 下面 - 都市），和仓库里现有手写稿同一个样式。"""

    def increase_indent(self, flow: bool = False, indentless: bool = False):
        return super().increase_indent(flow, False)


def _json_pretty(value, indent: int = 0) -> str:
    """json.dumps 的缩进版，但把「短的、纯标量的对象」压成一行——
    和仓库里 site.data.json 的手写排版一致，发布时 diff 才干净。"""
    pad = "  " * indent
    if isinstance(value, dict):
        flat = json.dumps(value, ensure_ascii=False, separators=(", ", ": "))
        if all(not isinstance(v, (dict, list)) for v in value.values()) and len(flat) + indent * 2 <= 80:
            return flat
        items = ",\n".join(
            f"{pad}  {json.dumps(k, ensure_ascii=False)}: {_json_pretty(v, indent + 1)}" for k, v in value.items()
        )
        return "{\n" + items + "\n" + pad + "}"
    if isinstance(value, list):
        if not value:
            return "[]"
        if all(not isinstance(v, (dict, list)) for v in value):
            flat = json.dumps(value, ensure_ascii=False, separators=(", ", ": "))
            if len(flat) + indent * 2 <= 80:
                return flat
        items = ",\n".join(f"{pad}  {_json_pretty(v, indent + 1)}" for v in value)
        return "[\n" + items + "\n" + pad + "]"
    return json.dumps(value, ensure_ascii=False)


def _write(rel: str, text: str) -> str:
    path = ROOT_DIR / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    # LF 写死，别让 Windows 的换行混进仓库
    path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))
    return rel


def _ensure_blank_line(body: str) -> str:
    body = (body or "").replace("\r\n", "\n").strip("\n")
    # frontmatter 已经以 `---\n` 结尾，这里只补一个空行 + 正文
    return ("\n" + body + "\n") if body else "\n"


def _site_payload(db: Session) -> dict:
    row = db.get(Setting, "site")
    base: dict = dict(row.value) if row and row.value else {}
    tracks = db.scalars(select(Track).order_by(Track.sort, Track.id)).all()
    doing = db.scalars(select(Doing).order_by(Doing.sort, Doing.id)).all()
    return {
        "name": base.get("name", ""),
        "en": base.get("en", ""),
        "mark": base.get("mark", ""),
        "intro": base.get("intro", ""),
        "lead": base.get("lead", ""),
        "desc": base.get("desc", ""),
        "playlistId": base.get("playlistId", ""),
        "musicApi": base.get("musicApi", ""),
        "portfolioUrl": base.get("portfolioUrl", ""),
        "backgroundImage": base.get("backgroundImage", ""),
        "backgroundImageDim": base.get("backgroundImageDim", 0.0),
        "contact": base.get("contact", {}),
        "bio": base.get("bio", []),
        "tracks": [
            {"id": t.netease_id, "name": t.name, "artist": t.artist, "dur": t.dur, "why": t.why}
            for t in tracks
        ],
        "doing": [
            {
                "state": d.state,
                "title": d.title,
                "sub": d.sub,
                "note": d.note,
                "noteLong": d.note_long,
            }
            for d in doing
        ],
        "facts": base.get("facts", []),
    }


def _photos_payload(db: Session) -> dict:
    albums = db.scalars(select(Album).order_by(Album.sort, Album.id)).all()
    out = []
    for album in albums:
        photos = db.scalars(select(Photo).where(Photo.album_slug == album.slug).order_by(Photo.sort, Photo.id)).all()
        out.append(
            {
                "id": album.slug,
                "title": album.title,
                "tone": album.tone,
                "note": album.note,
                "photos": [
                    {
                        "src": p.src,
                        "caption": p.caption,
                        "date": p.date.isoformat(),
                        **({"span": p.span} if p.span else {}),
                    }
                    for p in photos
                ],
            }
        )
    return {"albums": out}


def render_all(db: Session) -> dict:
    """把当前库里的内容全部写成文件，返回这次写了什么。"""
    written: list[str] = []

    # 文章
    for post in db.scalars(select(Post).order_by(Post.date, Post.id)).all():
        fm = {
            "title": post.title,
            "date": post.date,
            "tag": post.tag,
            "readTime": post.read_time,
            "summary": post.summary,
        }
        if post.draft:
            fm["draft"] = True
        written.append(_write(f"src/content/posts/{post.slug}.md", _frontmatter(fm) + _ensure_blank_line(post.body)))

    # 随记
    for note in db.scalars(select(Note).order_by(Note.date, Note.id)).all():
        fm = {"date": note.date}
        if note.tag:
            fm["tag"] = note.tag
        if note.draft:
            fm["draft"] = True
        written.append(_write(f"src/content/notes/{note.slug}.md", _frontmatter(fm) + _ensure_blank_line(note.body)))

    # 小说作品
    for novel in db.scalars(select(Novel).order_by(Novel.updated, Novel.id)).all():
        fm = {"title": novel.title}
        if novel.subtitle:
            fm["subtitle"] = novel.subtitle
        fm.update(
            {
                "summary": novel.summary,
                "status": novel.status,
                "tags": novel.tags or [],
                "updated": novel.updated,
            }
        )
        if novel.draft:
            fm["draft"] = True
        written.append(_write(f"src/content/novels/{novel.slug}.md", _frontmatter(fm) + _ensure_blank_line(novel.body)))

    # 章节
    for chapter in db.scalars(select(Chapter).order_by(Chapter.novel_slug, Chapter.order, Chapter.id)).all():
        fm = {
            "title": chapter.title,
            "order": chapter.order,
            "date": chapter.date,
        }
        if chapter.draft:
            fm["draft"] = True
        rel = f"src/content/chapters/{chapter.novel_slug}/{chapter.slug}.md"
        written.append(_write(rel, _frontmatter(fm) + _ensure_blank_line(chapter.body)))

    # 站点与相册
    written.append(
        _write(
            "src/data/site.data.json",
            _json_pretty(_site_payload(db)) + "\n",
        )
    )
    written.append(
        _write(
            "src/data/photos.data.json",
            _json_pretty(_photos_payload(db)) + "\n",
        )
    )

    # 清掉上一次生成、这次没再生成的（手动加的文件不在 manifest 里，不动）
    removed: list[str] = []
    for rel in _load_manifest():
        if rel in written:
            continue
        path = ROOT_DIR / rel
        if path.exists():
            path.unlink()
            removed.append(rel)
            # 章节被删空后，目录也一起收掉
            parent = path.parent
            while parent != ROOT_DIR and parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent

    _save_manifest(written)
    return {
        "written": len(written),
        "removed": len(removed),
        "files": written,
        "removed_files": removed,
    }


def clear_gallery_orphans(db: Session) -> int:
    """图片上传进 public/gallery 后，库里没人引用的文件清掉，别越堆越多。"""
    if not (ROOT_DIR / "public" / "gallery").exists():
        return 0
    used = {p.src.replace("/gallery/", "") for p in db.scalars(select(Photo)).all()}
    removed = 0
    for f in (ROOT_DIR / "public" / "gallery").iterdir():
        if f.is_file() and f.name not in used:
            f.unlink()
            removed += 1
    return removed


def delete_gallery_file(src: str) -> None:
    name = src.replace("/gallery/", "")
    path = ROOT_DIR / "public" / "gallery" / name
    if path.exists() and path.is_file():
        path.unlink()


__all__ = ["render_all", "clear_gallery_orphans", "delete_gallery_file", "SITE_JSON", "PHOTOS_JSON", "shutil"]
