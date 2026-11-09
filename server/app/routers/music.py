"""
音乐代理接口
带 cookie，能放完整歌曲，不会跳转。

Cookie 一律走环境变量，不要把真实 Cookie 写进代码或提交进 git：
- NETEASE_COOKIE：网易云音乐登录 Cookie
- TENCENT_COOKIE：QQ 音乐登录 Cookie
两个都不设也能用公共 Meting 接口，只是只有 30–45 秒试听。
"""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
import os
import re
import time
from collections import defaultdict

import httpx
import json

router = APIRouter(prefix="/api/music", tags=["music"])

# 网易云音乐 Cookie（环境变量注入，缺省为空 → 退化为试听）
NETEASE_COOKIE = os.getenv("NETEASE_COOKIE", "")

# 参数白名单：server 只认这两种；id 只认数字或 QQ 音乐 songmid（字母数字，最长 32 位）。
ALLOWED_SERVERS = {"netease", "tencent"}
_ID_RE = re.compile(r"^[A-Za-z0-9]{1,32}$")

# 简单限流：同一 IP 每分钟最多 N 次。内存实现，够挡脚本滥用，多进程部署可换 Redis。
_RATE_PER_MIN = 60
_hits: dict[str, list[float]] = defaultdict(list)

# QQ 音乐 Cookie（环境变量注入，缺省为空 → 退化为试听）
TENCENT_COOKIE = os.getenv("TENCENT_COOKIE", "")

# 公共 Meting API 地址（拿歌曲信息用）
METING_API = "https://api.injahow.cn/meting/"

# 网易云请求头
NETEASE_HEADERS = {
    "Cookie": NETEASE_COOKIE,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://music.163.com/",
}

# QQ 音乐请求头
TENCENT_HEADERS = {
    "Cookie": TENCENT_COOKIE,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://y.qq.com/",
}


@router.get("/")
async def meting_compat(
    request: Request,
    server: str = Query("netease"),
    type: str = Query(...),
    id: str = Query(...),
):
    """
    兼容 Meting 的调用格式：
    /api/music/?server=netease&type=url&id=64638
    /api/music/?server=tencent&type=url&id=xxx
    """
    # 参数校验：server 白名单，id 只收数字或 songmid，拦掉畸形/恶意输入。
    if server not in ALLOWED_SERVERS:
        raise HTTPException(400, detail="server 只支持 netease 或 tencent")
    if not _ID_RE.match(id or ""):
        raise HTTPException(400, detail="id 只能是数字或歌曲标识")

    # 简单限流：防止外部拿这个无鉴权接口当免费代理刷
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
            if type == "url":
                from fastapi.responses import StreamingResponse

                song_url = ""
                fail_reason = ""

                if server == "netease":
                    # 网易云：官方接口（有 cookie 给完整歌曲，无 cookie 给试听）
                    url_res = await client.get(
                        "https://music.163.com/api/song/enhance/player/url",
                        params={"ids": f"[{id}]", "br": "999000"},
                        headers=NETEASE_HEADERS,
                    )
                    url_data = url_res.json()
                    song_url = url_data.get("data", [{}])[0].get("url", "")

                elif server == "tencent":
                    # QQ 音乐：官方 vkey 接口。
                    # loginflag：有登录 Cookie 用 1（完整歌曲），否则用 0（更宽松，能拿到试听）。
                    loginflag = 1 if TENCENT_COOKIE else 0
                    payload = {
                        "req_0": {
                            "module": "vkey.GetVkeyServer",
                            "method": "CgiGetVkey",
                            "param": {
                                "guid": "10000",
                                "songmid": [id],
                                "songtype": [0],
                                "uin": "0" if not TENCENT_COOKIE else "1619095979",
                                "loginflag": loginflag,
                                "platform": "qq",
                            },
                        }
                    }
                    vkey_res = await client.post(
                        "https://u.y.qq.com/cgi-bin/musicu.fcg",
                        json=payload,
                        headers=TENCENT_HEADERS,
                    )
                    vkey_data = vkey_res.json()
                    req_0 = vkey_data.get("req_0", {})
                    data = req_0.get("data", {})
                    midurlinfo = data.get("midurlinfo", [{}])
                    if midurlinfo:
                        info = midurlinfo[0]
                        purl = info.get("purl", "")
                        # result 104003 表示 VIP/版权限制，无登录态拿不到
                        if purl:
                            # 用返回的播放服务器（sip 列表第一个），没有则用默认域名
                            sips = data.get("sip") or []
                            host = sips[0] if sips else "https://dl.stream.qqmusic.qq.com"
                            song_url = f"{host.rstrip('/')}/{purl}"
                        else:
                            code = info.get("result", "")
                            if code == 104003:
                                fail_reason = "这首歌受版权/VIP 限制，需登录 QQ 音乐（配 TENCENT_COOKIE）才能播"
                            else:
                                fail_reason = f"没拿到播放地址（错误码 {code}）"

                # 回退到 Meting：注意 Meting 的 url 接口对 netease 直接返回音频二进制流
                # （Content-Type: audio/mpeg），对 tencent 返回 JSON 或空。这里只当它返回
                # JSON 且带 url 字段时才当作 URL 用，避免把音频流误当 URL。
                if not song_url:
                    mt_res = await client.get(
                        f"{METING_API}?server={server}&type=url&id={id}"
                    )
                    ctype = mt_res.headers.get("content-type", "")
                    if "application/json" in ctype and mt_res.text:
                        try:
                            mt_data = json.loads(mt_res.text)
                            song_url = mt_data.get("url", "")
                        except json.JSONDecodeError:
                            song_url = ""
                    # Meting 直接回音频流的情况：透传（当作后备的完整音频）
                    elif ctype.startswith("audio/") and mt_res.content:
                        return StreamingResponse(
                            iter([mt_res.content]),
                            media_type=ctype.split(";")[0].strip() or "audio/mpeg",
                            headers={"Accept-Ranges": "bytes", "Content-Disposition": "inline"},
                        )

                # 流式代理音频，边下边传，支持 Range 请求，分段加载更快
                if song_url:
                    # 注意：不能用外层那个 client——它在函数返回后就关了。
                    # 这里单独开一个，供这个惰性生成器在整个流式过程中使用。
                    stream_headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                        "Referer": "https://y.qq.com/" if server == "tencent" else "https://music.163.com/",
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
                        media_type="audio/m4a",
                        headers={
                            "Accept-Ranges": "bytes",
                            "Content-Disposition": "inline",
                        },
                    )
                else:
                    return {"error": fail_reason or "没拿到播放地址", "url": ""}

            elif type == "lrc":
                # 拿歌词：走 Meting，直接返回纯 LRC 文本
                mt_res = await client.get(
                    f"{METING_API}?server={server}&type=lrc&id={id}"
                )
                if mt_res.text:
                    mt_data = mt_res.json()
                    # Meting 返回 { "lrc": "歌词文本..." }，提取出来直接返回
                    lrc_text = mt_data.get("lrc", "")
                    if isinstance(lrc_text, dict):
                        lrc_text = lrc_text.get("lrc", "")
                    return PlainTextResponse(lrc_text)
                else:
                    return PlainTextResponse("")

            elif type == "song":
                # 拿歌曲详情：走 Meting
                mt_res = await client.get(
                    f"{METING_API}?server={server}&type=song&id={id}"
                )
                return mt_res.json() if mt_res.text else []

            elif type == "playlist":
                # 拿歌单：走 Meting
                mt_res = await client.get(
                    f"{METING_API}?server={server}&type=playlist&id={id}"
                )
                return mt_res.json() if mt_res.text else []

            else:
                return {"error": f"未知类型: {type}"}

        except Exception as e:
            return {"error": f"请求失败: {str(e)}", "url": ""}
