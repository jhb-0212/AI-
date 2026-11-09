"""
网易云音乐代理接口
带 cookie，能放完整歌曲，不会跳转
"""
from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse
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

                # 流式代理音频，边下边传，支持 Range 请求，分段加载更快
                if song_url:
                    async def stream_audio():
                        headers = {}
                        range_header = request.headers.get("range")
                        if range_header:
                            headers["Range"] = range_header
                        async with client.stream("GET", song_url, headers=headers) as resp:
                            async for chunk in resp.aiter_bytes(chunk_size=8192):
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
                    return {"error": "没拿到播放地址", "url": ""}

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
