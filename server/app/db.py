from __future__ import annotations

import shutil
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import BACKUP_DIR, BACKUP_REMOTE_KEEP_DAYS, DATA_DIR, DATABASE_URL, DB_PATH

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
    """SQLite 数据库自动备份：每天一次，本地保留最近 7 天；异地目录保留更多天。"""
    if not DATABASE_URL.startswith("sqlite"):
        return None  # PostgreSQL 等用自带备份工具
    if not DB_PATH.exists():
        return None

    backup_dir = DATA_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    backup_file = backup_dir / f"db-{today}.sqlite"

    # 今天已经备份过了，跳过（但异地那份若缺失仍会补写）
    already_done = backup_file.exists()

    if not already_done:
        try:
            shutil.copy2(DB_PATH, backup_file)
        except OSError:
            return None

    # 清理本地 7 天前的备份
    _prune_backups(backup_dir, days=7)

    # 异地备份：写一份到 BACKUP_DIR（如挂载的云盘），并清理过期
    if BACKUP_DIR:
        remote_dir = Path(BACKUP_DIR)
        try:
            remote_dir.mkdir(parents=True, exist_ok=True)
            remote_file = remote_dir / f"db-{today}.sqlite"
            if not remote_file.exists():
                shutil.copy2(DB_PATH, remote_file)
            _prune_backups(remote_dir, days=BACKUP_REMOTE_KEEP_DAYS)
        except OSError:
            # 异地不可用时不影响本地备份，静默降级
            pass

    return backup_file


def _prune_backups(directory: Path, days: int) -> None:
    """删除 directory 下超过 days 天的 db-*.sqlite 备份。"""
    cutoff = datetime.now() - timedelta(days=days)
    for f in directory.glob("db-*.sqlite"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
        except OSError:
            pass
