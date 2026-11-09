"""一次性迁移：把 tracks 表的 netease_id 列改名为 song_id 并转成 TEXT。

背景：站点从网易云迁到 QQ 音乐，歌曲标识从纯数字 id 变成字符串 songmid
（如 "001if23h0TDFmD"）。旧库的 tracks.netease_id 是 INTEGER，需要改成 TEXT 的
song_id，并把数据对齐到 src/data/site.data.json 里的 songmid。

做法：SQLite 的 RENAME COLUMN 不改列类型，所以用「重建表」的方式，确保
song_id 真正是 TEXT，杜绝后续 render 输出数字/字符串混杂的类型漂移。

幂等：song_id 已经是 TEXT 类型时跳过；否则重建。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "nepenthe.db"
SITE_JSON = Path(__file__).parent.parent / "src" / "data" / "site.data.json"

NEW_COLUMNS = [
    ("id", "INTEGER PRIMARY KEY"),
    ("song_id", "TEXT"),
    ("name", "VARCHAR(160)"),
    ("artist", "VARCHAR(160)"),
    ("dur", "INTEGER"),
    ("why", "VARCHAR(300)"),
    ("sort", "INTEGER"),
]


def _column_names(conn: sqlite3.Connection) -> list[str]:
    return [r[1] for r in conn.execute("PRAGMA table_info(tracks)")]


def _column_types(conn: sqlite3.Connection) -> dict[str, str]:
    return {r[1]: (r[2] or "").upper() for r in conn.execute("PRAGMA table_info(tracks)")}


def _load_songmid_by_name() -> dict[str, str]:
    if not SITE_JSON.exists():
        return {}
    payload = json.loads(SITE_JSON.read_text(encoding="utf-8"))
    return {t["name"]: str(t["id"]) for t in payload.get("tracks", [])}


def migrate() -> None:
    if not DB_PATH.exists():
        print("没有找到数据库，跳过。")
        return

    conn = sqlite3.connect(str(DB_PATH))
    try:
        cols = _column_names(conn)
        types = _column_types(conn)

        # 已经是正确结构（song_id 且 TEXT），跳过
        if "song_id" in cols and types.get("song_id", "").startswith("TEXT"):
            print("已经迁移过（song_id 为 TEXT），跳过。")
            return

        # 旧结构：netease_id（INTEGER）
        if "netease_id" not in cols and "song_id" not in cols:
            print("tracks 表结构异常，跳过。")
            return

        songmid_by_name = _load_songmid_by_name()

        # 读出现有数据（兼容两种列名）
        id_col = "song_id" if "song_id" in cols else "netease_id"
        rows = conn.execute(f"SELECT id, {id_col}, name, artist, dur, why, sort FROM tracks").fetchall()

        # 重建表：先改名旧表，再建新表，导数据，最后删旧表
        conn.execute("ALTER TABLE tracks RENAME TO tracks_old")
        conn.execute(
            "CREATE TABLE tracks (" + ", ".join(f"{n} {t}" for n, t in NEW_COLUMNS) + ")"
        )
        for row in rows:
            rid, raw_id, name, artist, dur, why, sort = row
            # 优先用 site.data.json 里的 songmid，其次保留原值转字符串
            song_id = songmid_by_name.get(name, str(raw_id))
            conn.execute(
                "INSERT INTO tracks (id, song_id, name, artist, dur, why, sort) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (rid, song_id, name, artist, dur, why, sort),
            )
        conn.execute("DROP TABLE tracks_old")
        conn.commit()
        print(f"重建完成：tracks 现有 {len(rows)} 首，song_id 已统一为 TEXT。")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
