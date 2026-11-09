from __future__ import annotations

import shutil
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DATA_DIR, DATABASE_URL, DB_PATH

DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    # SQLite 在多个线程里复用连接需要这个；PostgreSQL 会忽略它
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def backup_database() -> Path | None:
    """SQLite 数据库自动备份：每天一次，保留最近 7 天。"""
    if not DATABASE_URL.startswith("sqlite"):
        return None  # PostgreSQL 等用自带备份工具
    if not DB_PATH.exists():
        return None

    backup_dir = DATA_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    backup_file = backup_dir / f"db-{today}.sqlite"

    # 今天已经备份过了，跳过
    if backup_file.exists():
        return backup_file

    try:
        shutil.copy2(DB_PATH, backup_file)
    except OSError:
        return None

    # 清理 7 天前的备份
    cutoff = datetime.now() - timedelta(days=7)
    for f in backup_dir.glob("db-*.sqlite"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
        except OSError:
            pass

    return backup_file
