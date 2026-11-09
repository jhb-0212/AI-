"""访客采集：入库、UV 去重、bot 与后台路径过滤、聚合口径。"""

from __future__ import annotations

import json

import pytest

HEADER = {"content-type": "text/plain;charset=UTF-8"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"


@pytest.fixture(autouse=True)
def clean():
    from app.db import SessionLocal
    from app.models import Visit

    with SessionLocal() as db:
        db.query(Visit).delete()
        db.commit()


def hit(client, path="/posts/opening/", ref="", ua=UA):
    return client.post(
        "/api/hit",
        content=json.dumps({"path": path, "ref": ref}),
        headers={**HEADER, "user-agent": ua},
    )


def test_hit_returns_204_and_records(client):
    assert hit(client).status_code == 204

    from app.db import SessionLocal
    from app.models import Visit

    with SessionLocal() as db:
        rows = db.query(Visit).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.path == "/posts/opening/"
        assert row.ua.startswith("Chrome")
        # 存的是哈希，不是 IP，也不是 UA 原文
        assert len(row.visitor) == 16
        assert "127.0.0.1" not in row.visitor


def test_pv_counts_twice_uv_once(client, admin):
    hit(client)
    hit(client)
    v = admin.get("/api/visits").json()
    assert v["today"]["pv"] == 2
    assert v["today"]["uv"] == 1
    assert v["pv_total"] == 2


def test_query_string_and_assets_ignored(client, admin):
    hit(client, "/posts/opening/?utm_source=x")
    hit(client, "/_astro/app.js")
    v = admin.get("/api/visits").json()
    assert [p["path"] for p in v["top_pages"]] == ["/posts/opening/"]
    assert v["pv_total"] == 1


def test_bot_and_admin_paths_are_dropped(client, admin):
    hit(client, ua="Googlebot/2.1 (+http://www.google.com/bot.html)")
    hit(client, ua="curl/8.4.0")
    hit(client, path="/admin/")
    hit(client, path="/api/stats")
    assert admin.get("/api/visits").json()["pv_total"] == 0


def test_referrer_and_browser_breakdown(client, admin):
    hit(client, ref="www.google.com")
    hit(client, ref="www.google.com")
    hit(client)
    hit(client, ua="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15")
    v = admin.get("/api/visits").json()
    refs = {x["ref"]: x["pv"] for x in v["top_refs"]}
    assert refs["www.google.com"] == 2
    assert refs["直接访问"] == 2
    uas = {x["ua"]: x["pv"] for x in v["browsers"]}
    assert uas.get("Safari / iOS") == 1


def test_summary_needs_login():
    """另开一个没带 cookie 的客户端；共享的 client 已经登录过了。"""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as fresh:
        assert fresh.get("/api/visits").status_code == 401


def test_series_covers_every_day(client, admin):
    hit(client)
    v = admin.get("/api/visits").json()
    assert v["days"] == 30
    assert len(v["series"]) == 30
    assert v["series"][-1]["pv"] == 1
    assert sum(x["pv"] for x in v["series"]) == 1
