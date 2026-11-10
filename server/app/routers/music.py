"""
音乐代理接口（网易云音乐）
带 cookie，能放完整歌曲，流式代理 + Range 请求，不会跳转/触发下载。

Cookie 走环境变量 NETEASE_COOKIE，不要写进代码：
- 有 cookie：网易云官方接口返回完整歌曲（.mp3/.flac）
- 无 cookie：退化为公共 Meting 试听片段（30 秒）
"""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
import os
import re
import time
from collections import defaultdict

import httpx
import json

router = APIRouter(prefix="/api/music", tags=["music"])

# 网易云登录 Cookie（环境变量注入）
NETEASE_COOKIE = os.getenv("NETEASE_COOKIE", "")

# id 只认数字（网易云歌曲 ID / 歌单 ID）
_ID_RE = re.compile(r"^\d{1,20}$")

# 简单限流：同一 IP 每分钟 60 次
_RATE_PER_MIN = 60
_hits: dict[str, list[float]] = defaultdict(list)

# 公共 Meting API（拿歌单/详情/歌词回退用）
METING_API = "https://api.injahow.cn/meting/"

# 网易云官方请求头
NETEASE_HEADERS = {
    "Cookie": NETEASE_COOKIE,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://music.163.com/",
}


@router.get("/")
async def meting_compat(
    request: Request,
    type: str = Query(...),
    id: str = Query(...),
):
    """
    兼容 Meting 调用格式（固定网易云源）：
    /api/music/?type=playlist&id=18570165544
    /api/music/?type=url&id=386844
    /api/music/?type=lrc&id=386844
    """
    if not _ID_RE.match(id or ""):
        raise HTTPException(400, detail="id 只能是数字")

    # 限流
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    bucket = [t for t in _hits.get(ip, []) if now - t < 60]
    if len(bucket) >= _RATE_PER_MIN:
        _hits[ip] = bucket
        raise HTTPException(429, detail="请求太频繁，稍后再试")
    bucket.append(now)
    _hits[ip] = bucket

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        try:
            # ---------- 音频地址：流式代理 ----------
            if type == "url":
                song_url = ""

                # 1) 优先走网易云官方接口（有 cookie 给完整歌曲）
                if NETEASE_COOKIE:
                    url_res = await client.get(
                        "https://music.163.com/api/song/enhance/player/url",
                        params={"ids": f"[{id}]", "br": "999000"},
                        headers=NETEASE_HEADERS,
                    )
                    url_data = url_res.json()
                    song_url = url_data.get("data", [{}])[0].get("url", "") or ""

                # 2) 回退到公共 Meting（试听片段）
                if not song_url:
                    mt_res = await client.get(
                        f"{METING_API}?server=netease&type=url&id={id}"
                    )
                    ctype = mt_res.headers.get("content-type", "")
                    # Meting 对 netease 直接返回音频二进制流
                    if ctype.startswith("audio/") and mt_res.content:
                        return StreamingResponse(
                            iter([mt_res.content]),
                            media_type=ctype.split(";")[0].strip() or "audio/mpeg",
                            headers={
                                "Accept-Ranges": "bytes",
                                "Content-Disposition": "inline",
                            },
                        )
                    if "application/json" in ctype and mt_res.text:
                        try:
                            song_url = json.loads(mt_res.text).get("url", "")
                        except json.JSONDecodeError:
                            song_url = ""

                if not song_url:
                    return {"error": "没拿到播放地址", "url": ""}

                # 流式代理音频，支持 Range 分段加载
                stream_headers = {
                    "User-Agent": NETEASE_HEADERS["User-Agent"],
                    "Referer": "https://music.163.com/",
                }

                async def stream_audio():
                    range_header = request.headers.get("range")
                    if range_header:
                        stream_headers["Range"] = range_header
                    async with httpx.AsyncClient(
                        timeout=30, follow_redirects=True
                    ) as sc:
                        async with sc.stream(
                            "GET", song_url, headers=stream_headers
                        ) as resp:
                            async for chunk in resp.aiter_bytes(chunk_size=65536):
                                yield chunk

                return StreamingResponse(
                    stream_audio(),
                    media_type="audio/mpeg",
                    headers={
                        "Accept-Ranges": "bytes",
                        "Content-Disposition": "inline",
                    },
                )

            # ---------- 歌词：纯 LRC 文本 ----------
            elif type == "lrc":
                mt_res = await client.get(
                    f"{METING_API}?server=netease&type=lrc&id={id}"
                )
                if mt_res.text:
                    mt_data = mt_res.json()
                    lrc_text = mt_data.get("lrc", "")
                    if isinstance(lrc_text, dict):
                        lrc_text = lrc_text.get("lrc", "")
                    return PlainTextResponse(lrc_text or "")
                return PlainTextResponse("")

            # ---------- 歌曲详情 ----------
            elif type == "song":
                mt_res = await client.get(
                    f"{METING_API}?server=netease&type=song&id={id}"
                )
                return mt_res.json() if mt_res.text else []

            # ---------- 歌单 ----------
            elif type == "playlist":
                mt_res = await client.get(
                    f"{METING_API}?server=netease&type=playlist&id={id}"
                )
                return mt_res.json() if mt_res.text else []

            else:
                return {"error": f"未知类型: {type}"}

        except Exception as e:
            return {"error": f"请求失败: {str(e)}", "url": ""}
