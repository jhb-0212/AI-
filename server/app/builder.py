"""触发 npm run build 并记住这一次的结果。

构建放在后台线程里跑：接口先返回「已开始」，前端轮询 /api/publish/status 拿日志。
同一时间只允许一个构建，避免两次 npm 抢同一个 dist/ 目录。

除了「这一次」，还留一份最近几次的发布历史（落盘在 server/data/build-history.json），
仪表盘上可以看什么时候发过、发了几页、花了多久。历史读不出来只影响那一个卡片，不挡发布。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime

from .config import BUILD_TIMEOUT, DATA_DIR, ROOT_DIR

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07")
_HISTORY_PATH = DATA_DIR / "build-history.json"
_HISTORY_MAX = 10

_lock = threading.Lock()
_state: dict = {
    "state": "idle",
    "started_at": None,
    "finished_at": None,
    "duration_ms": None,
    "pages": None,
    "log": "",
    "git": None,
}


def _load_history() -> list[dict]:
    try:
        data = json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
        return [x for x in data if isinstance(x, dict)][-_HISTORY_MAX:]
    except FileNotFoundError:
        return []
    except Exception:  # noqa: BLE001 - 历史坏了不该挡住服务启动
        return []


_history: list[dict] = _load_history()


def _save_history() -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _HISTORY_PATH.write_text(
            json.dumps(_history[-_HISTORY_MAX:], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001 - 写不进去最多是没历史，不能影响发布结果
        pass


def status() -> dict:
    with _lock:
        return dict(_state)


def history() -> list[dict]:
    """最近几次发布，新的在前。"""
    with _lock:
        return list(reversed(_history))


def is_running() -> bool:
    with _lock:
        return _state["state"] == "running"


def start(git_commit: bool = False, message: str | None = None) -> dict:
    with _lock:
        if _state["state"] == "running":
            raise RuntimeError("上一次构建还没结束")
        _state.update(
            state="running",
            started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            finished_at=None,
            duration_ms=None,
            pages=None,
            log="",
            git=None,
        )
    threading.Thread(target=_work, args=(git_commit, message), daemon=True).start()
    return status()


def _run(cmd: list[str]) -> tuple[int, str]:
    env = dict(os.environ, NO_COLOR="1", FORCE_COLOR="0")
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT_DIR),
        shell=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=BUILD_TIMEOUT,
        env=env,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    # 彩色输出进数据库没意义，日志里只留字
    return proc.returncode, _ANSI.sub("", output)


def _work(git_commit: bool, message: str | None) -> None:
    t0 = time.perf_counter()
    git_info: dict | None = None

    dist_dir = ROOT_DIR / "dist"
    dist_backup = ROOT_DIR / "dist.bak"

    # 备份当前 dist
    had_old_dist = dist_dir.exists()
    if had_old_dist:
        try:
            if dist_backup.exists():
                import shutil
                shutil.rmtree(dist_backup)
            dist_dir.rename(dist_backup)
        except OSError:
            pass

    try:
        code, log = _run(["npm", "run", "build"])
        ok = code == 0
        pages = None
        m = re.search(r"(\d+) page\(s\) built", log)
        if m:
            pages = m.group(1)

        if ok:
            # 构建成功，清理旧备份
            if dist_backup.exists():
                import shutil
                shutil.rmtree(dist_backup, ignore_errors=True)
            if git_commit:
                git_info = _commit(message)
            state = "ok"
        else:
            # 构建失败，恢复旧版本
            if had_old_dist and dist_backup.exists():
                if dist_dir.exists():
                    import shutil
                    shutil.rmtree(dist_dir)
                dist_backup.rename(dist_dir)
            state = "failed"
    except subprocess.TimeoutExpired:
        log = f"构建超过 {BUILD_TIMEOUT} 秒，已放弃。"
        state = "failed"
        pages = None
        ok = False
        # 超时也要恢复
        if had_old_dist and dist_backup.exists() and not dist_dir.exists():
            dist_backup.rename(dist_dir)
    except Exception as exc:  # noqa: BLE001 - 构建线程里任何异常都要落成状态，不能静默
        log = f"构建失败：{exc}"
        state = "failed"
        pages = None
        ok = False
        # 异常也要恢复
        if had_old_dist and dist_backup.exists() and not dist_dir.exists():
            try:
                dist_backup.rename(dist_dir)
            except OSError:
                pass

    with _lock:
        _state.update(
            state=state,
            finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            duration_ms=int((time.perf_counter() - t0) * 1000),
            pages=pages,
            log=log[-8000:],
            git=git_info,
        )
        _history.append(
            {
                "finished_at": _state["finished_at"],
                "state": state,
                "pages": pages,
                "duration_ms": _state["duration_ms"],
                "git": bool(git_info and git_info.get("ok")),
            }
        )
        del _history[:-_HISTORY_MAX]
        _save_history()


def _commit(message: str | None) -> dict:
    msg = message or "chore: 后台发布"
    code, log = _run(["git", "add", "-A"])
    if code != 0:
        return {"ok": False, "output": log[-2000:]}
    code, log = _run(["git", "commit", "-m", msg])
    if code != 0 and ("nothing to commit" in log or "null" in log or "无文件要提交" in log):
        return {"ok": True, "output": "没有改动，未提交。"}
    if code == 0:
        code2, log2 = _run(["git", "log", "--oneline", "-1"])
        return {"ok": True, "output": (log + log2)[-2000:]}
    return {"ok": False, "output": log[-2000:]}
