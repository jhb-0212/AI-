"""
网易云音乐代理接口
带 cookie，能放完整歌曲，不会跳转
"""
from fastapi import APIRouter, Query
import httpx
import json

router = APIRouter(prefix="/api/music", tags=["music"])

# 你的网易云 cookie
NETEASE_COOKIE = "P_INFO=jhb060214@163.com|1781253013|0|unireg|00&99|null&null&null#gud&440200#10#0#0|&0||jhb060214@163.com; NMTID=00Oa9_8Gepi3r_qyUqLtqg7YhiAs8QAAAGhwBI2gg; MUSIC_U=001B6C5EC7FBB7141DB4ED987CD5F288A2437254564BDB75D107EFDE40256A8DB3BEEACD51559AAA9B30CA07F0BCF5CF1A0F02E41F0FE6FF768DBFA81795FCCBB412D5972C4F26D754D88D6784D54E0606B78CACDB6DAF2304F1483C671CB3708886803AC7AC62FF77E41ACF9281EF87786FB91C4F71C3957F7F19CA94E2145BDE715E2E7012ED32A97A598FE3F31FDE4FEB75F8BD536F8D3869429C5DFFAA3BCAD119D1F23C584E5CAFE26B47B8182B59BFE6B7209593A123A8AAD5EA76E629F0A52147BF045CE8A672FCEC3C4A819F1E8FCCC705DBC9376E16A29E3BCC8A51212FBAF0DF8782ED5AC1368C6F918CF4F69522F53E37AED2596BCD203F6866663D20F7245DFE65C43336A654B69CE629DE2350B5A255DEA0DC7F5DD64A564510454CD5166210776FCCEE34A2D2DF273D8A40A496B5465DB68BCC0A703EBAB8D5ECF6CEC2A431A09394460CD8C4E67C7F9611F134DD5B5FAA41211239B45F43C34F379B94D22158CE4AA9012D3A37D508A3B392EBE3DB11F2C5A88B805E8365502B806F3EF6EE0FDCCF1524A37177ED694B1B838433403AECD7AA1F2BC58CCCCAD1; __csrf=2b0d315309cac5fad087feb504a3b636;"

# QQ 音乐 cookie
TENCENT_COOKIE = "uin=1619095979; qm_keyst=Q_H_L_63k3NAA4RtB9DRRi8LO5FDI-0otknkfvU_RYTIyzVgdZ1aPOynBq8gMB07SYCDGrM_YXqeRTFKvp2giXN0YoPcbGP; qqmusic_key=Q_H_L_63k3NAA4RtB9DRRi8LO5FDI-0otknkfvU_RYTIyzVgdZ1aPOynBq8gMB07SYCDGrM_YXqeRTFKvp2giXN0YoPcbGP; euin=oKC5NKnq7KElNv**; tmeLoginType=2;"

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
    server: str = Query("netease"),
    type: str = Query(...),
    id: str = Query(...),
):
    """
    兼容 Meting 的调用格式：
    /api/music/?server=netease&type=url&id=64638
    /api/music/?server=tencent&type=url&id=xxx
    """
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        try:
            if type == "url":
                from fastapi.responses import StreamingResponse

                if server == "netease":
                    # 网易云：先用官方接口（带 cookie，完整歌曲）
                    url_res = await client.get(
                        "https://music.163.com/api/song/enhance/player/url",
                        params={"ids": f"[{id}]", "br": "999000"},
                        headers=NETEASE_HEADERS,
                    )
                    url_data = url_res.json()
                    song_url = url_data.get("data", [{}])[0].get("url", "")
                elif server == "tencent":
                    # QQ 音乐：用官方接口（带 cookie，完整歌曲）
                    guid = "10000"
                    uin = "1619095979"
                    payload = {
                        "req_0": {
                            "module": "vkey.GetVkeyServer",
                            "method": "CgiGetVkey",
                            "param": {
                                "guid": guid,
                                "songmid": [id],
                                "songtype": [0],
                                "uin": uin,
                                "loginflag": 1,
                                "platform": "qq"
                            }
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
                        purl = midurlinfo[0].get("purl", "")
                        if purl:
                            song_url = f"https://dl.stream.qqmusic.qq.com/{purl}"
                        else:
                            song_url = ""
                    else:
                        song_url = ""
                else:
                    song_url = ""

                # 回退到 Meting
                if not song_url:
                    mt_res = await client.get(
                        f"{METING_API}?server={server}&type=url&id={id}"
                    )
                    mt_data = mt_res.json() if mt_res.text else {}
                    song_url = mt_data.get("url", "")

                # 直接代理音频流，解决跨域问题
                if song_url:
                    audio_resp = await client.get(song_url)
                    return StreamingResponse(
                        audio_resp.iter_bytes(),
                        status_code=audio_resp.status_code,
                        media_type=audio_resp.headers.get("content-type", "audio/mpeg"),
                        headers={
                            "Accept-Ranges": "bytes",
                        },
                    )
                else:
                    return {"error": "没拿到播放地址", "url": ""}

            elif type == "lrc":
                # 拿歌词：走 Meting
                mt_res = await client.get(
                    f"{METING_API}?server={server}&type=lrc&id={id}"
                )
                return mt_res.json() if mt_res.text else {"lrc": {}}

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


@router.get("/song")
async def get_song(
    id: int = Query(..., description="歌曲 ID"),
):
    """
    获取歌曲播放地址
    前端调用：/api/music/song?id=64638
    返回：{ url: "https://...", name: "...", artist: "...", pic: "..." }
    """
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        try:
            # 1. 先从 Meting 拿歌曲基本信息（名字、歌手、封面）
            detail_res = await client.get(
                f"{METING_API}?type=song&id={id}&server=netease"
            )
            detail = detail_res.json() if detail_res.text else []
            song_info = detail[0] if detail else {}

            # 2. 用网易云官方接口拿真实播放地址（带 cookie，完整歌曲）
            url_res = await client.get(
                f"https://music.163.com/api/song/enhance/player/url",
                params={"ids": f"[{id}]", "br": "999000"},
                headers=NETEASE_HEADERS,
            )
            url_data = url_res.json()
            song_url = url_data.get("data", [{}])[0].get("url", "")

            # 如果官方接口没拿到，回退到 Meting 的 url
            if not song_url and song_info.get("url"):
                song_url = song_info["url"]

        except Exception as e:
            return {"error": f"请求失败: {str(e)}", "url": ""}

    return {
        "url": song_url or "",
        "name": song_info.get("name", ""),
        "artist": song_info.get("artist", ""),
        "pic": song_info.get("pic", ""),
    }


@router.get("/playlist")
async def get_playlist(
    id: int = Query(..., description="歌单 ID"),
):
    """
    获取歌单所有歌曲
    前端调用：/api/music/playlist?id=18570165544
    """
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(
            f"{METING_API}?type=playlist&id={id}&server=netease"
        )
        data = res.json()

    return {
        "songs": data,
        "count": len(data),
    }


@router.get("/proxy")
async def proxy_audio(
    url: str = Query(..., description="要代理的音频地址"),
):
    """
    音频代理接口，解决跨域问题
    前端调用：/api/music/proxy?url=https://xxx.mp3
    """
    from fastapi.responses import StreamingResponse
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        try:
            req = client.build_request("GET", url)
            resp = await client.send(req, stream=True)
            return StreamingResponse(
                resp.aiter_bytes(),
                status_code=resp.status_code,
                media_type=resp.headers.get("content-type", "audio/mpeg"),
                headers={
                    "Content-Disposition": "inline",
                    "Accept-Ranges": "bytes",
                },
            )
        except Exception as e:
            return {"error": f"代理失败: {str(e)}"}
