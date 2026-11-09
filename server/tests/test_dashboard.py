"""仪表盘那块的数据：stats 里新加的几个字段，以及构建历史的滚动与落盘。"""

from __future__ import annotations

import json


def test_stats_has_dashboard_fields(admin):
    s = admin.get("/api/stats").json()
    for key in ("recent", "draft_items", "tags", "builds", "drafts"):
        assert key in s, key
    assert isinstance(s["recent"], list)
    assert isinstance(s["builds"], list)


def test_stats_recent_is_sorted_and_labelled(admin):
    s = admin.get("/api/stats").json()
    dates = [x["date"] for x in s["recent"]]
    assert dates == sorted(dates, reverse=True)
    for item in s["recent"]:
        assert set(("kind", "title", "slug", "date", "draft")) <= set(item)
        assert item["kind"] in {"文章", "随记", "章节", "作品"}


def test_draft_items_only_drafts(admin):
    s = admin.get("/api/stats").json()
    assert all(x["draft"] is True for x in s["draft_items"])


def test_build_history_trim_and_persist(tmp_path, monkeypatch):
    """历史最多留 10 条，而且会写到 build-history.json 里。"""
    from app import builder

    monkeypatch.setattr(builder, "DATA_DIR", tmp_path)
    monkeypatch.setattr(builder, "_HISTORY_PATH", tmp_path / "build-history.json")
    monkeypatch.setattr(builder, "_history", [])

    for i in range(13):
        builder._history.append({"finished_at": f"2026-11-07 10:00:{i:02d}", "state": "ok", "pages": "16"})
        del builder._history[: -builder._HISTORY_MAX]
    builder._save_history()

    data = json.loads((tmp_path / "build-history.json").read_text(encoding="utf-8"))
    assert len(data) == builder._HISTORY_MAX
    assert data[-1]["finished_at"] == "2026-11-07 10:00:12"


def test_history_returns_newest_first(admin, monkeypatch):
    from app import builder

    monkeypatch.setattr(builder, "_history", [{"finished_at": "a"}, {"finished_at": "b"}])
    assert [x["finished_at"] for x in builder.history()] == ["b", "a"]
