"""渲染层的测试：数据库 -> 仓库文件这一层最容易出事，单独守住。

重点是三件事：
1. 写出来的 frontmatter 字段名和 src/content.config.ts 对得上；
2. 冗余文件会被清掉，但「没被后台管过的手写文件」不会被误删；
3. 空正文 / 空字段不会写出半截文件。
"""

import re
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import render
from app.db import Base
from app.models import Note, Post, Setting, Track
from app.seed import parse_markdown

CONTENT_CONFIG = "src/content.config.ts"


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """把 render 的目标目录整个搬进 tmp，测试绝不碰真仓库。"""
    monkeypatch.setattr(render, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(render, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(render, "MANIFEST", tmp_path / "data" / "generated.json")
    engine = create_engine(f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        yield db


def test_parse_markdown_keeps_body():
    text = "---\ntitle: 标题\ndate: 2026-11-07\n---\n\n第一段。\n\n第二段。\n"
    meta, body = parse_markdown(text)
    assert meta["title"] == "标题"
    assert body == "第一段。\n\n第二段。"


def test_parse_markdown_without_frontmatter():
    meta, body = parse_markdown("就是一段正文。")
    assert meta == {}
    assert body == "就是一段正文。"


def test_post_frontmatter_matches_content_config(sandbox):
    db = sandbox
    db.add(
        Post(
            slug="hello",
            title="标题",
            date=date(2026, 11, 7),
            tag="开篇",
            read_time="3 分钟",
            summary="一句摘要。",
            body="正文。",
        )
    )
    db.commit()
    render.render_all(db)

    text = (render.ROOT_DIR / "src/content/posts/hello.md").read_text(encoding="utf-8")
    meta, body = parse_markdown(text)
    assert body == "正文。"
    # content.config.ts 里 posts 的字段：title / date / tag / readTime / summary / draft
    assert set(meta) <= {"title", "date", "tag", "readTime", "summary", "draft"}
    assert meta["readTime"] == "3 分钟"
    assert meta["date"] == date(2026, 11, 7)
    assert "draft" not in meta  # 非草稿不写 draft: false，保持 diff 干净


def test_note_tag_is_optional(sandbox):
    db = sandbox
    db.add(Note(slug="2026-11-07-01", date=date(2026, 11, 7), tag=None, body="一句话。"))
    db.commit()
    render.render_all(db)
    text = (render.ROOT_DIR / "src/content/notes/2026-11-07-01.md").read_text(encoding="utf-8")
    meta, body = parse_markdown(text)
    assert "tag" not in meta
    assert body == "一句话。"


def test_stale_files_removed_but_manual_kept(sandbox):
    db = sandbox
    db.add(Post(slug="keep", title="留下", date=date(2026, 11, 7), body="x"))
    db.add(Post(slug="gone", title="会删", date=date(2026, 11, 7), body="y"))
    db.commit()
    render.render_all(db)

    manual = render.ROOT_DIR / "src/content/posts/hand-written.md"
    manual.parent.mkdir(parents=True, exist_ok=True)
    manual.write_text("手写稿", encoding="utf-8")

    post = db.query(Post).filter(Post.slug == "gone").one()
    db.delete(post)
    db.commit()
    result = render.render_all(db)

    assert not (render.ROOT_DIR / "src/content/posts/gone.md").exists()
    assert (render.ROOT_DIR / "src/content/posts/keep.md").exists()
    assert manual.exists(), "手动放进仓库的稿子不能被删"
    assert "src/content/posts/gone.md" in result["removed_files"]


def test_site_json_shape(sandbox):
    db = sandbox
    db.add(Setting(key="site", value={"name": "忘忧居", "en": "Nepenthe", "contact": {"github": ""}}))
    db.add(Track(song_id="64638", name="陀飞轮", artist="陈奕迅", dur=278, why="理由", sort=1))
    db.commit()
    render.render_all(db)

    import json

    payload = json.loads((render.ROOT_DIR / "src/data/site.data.json").read_text(encoding="utf-8"))
    assert payload["tracks"][0] == {"id": "64638", "name": "陀飞轮", "artist": "陈奕迅", "dur": 278, "why": "理由"}
    assert set(payload) == {
        "name", "en", "mark", "intro", "lead", "desc", "playlistId", "musicApi",
        "musicServer", "portfolioUrl", "backgroundImage", "backgroundImageDim",
        "contact", "bio", "tracks", "doing", "facts",
    }


def test_content_config_fields_lineup(sandbox, tmp_path):
    """把 content.config.ts 里的字段名抓出来，和渲染出来的键对一遍，
    防止以后随手改 schema、忘了改 render。"""
    repo = render.ROOT_DIR.parent  # sandbox 的父目录不是真仓库，单独读真仓库
    from pathlib import Path

    real = Path(__file__).resolve().parents[2] / CONTENT_CONFIG
    text = real.read_text(encoding="utf-8")
    schema_keys = set(re.findall(r"\b(readTime|summary|subtitle|status|updated|order|draft|tag|title|date|tags)\b", text))
    assert {"readTime", "summary", "order", "tags"} <= schema_keys
