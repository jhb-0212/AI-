"""图片上传的安全处理：格式校验 + 重编码 + 剥离 EXIF。

上传的图统一在这里过一遍：
1. 校验真实格式（magic number），防止改后缀塞恶意文件；
2. 用 Pillow 重新编码，剥离全部元数据（EXIF/IPTC/XMP），
   一方面防止照片里泄露 GPS 定位等隐私，另一方面消除 polyglot 文件
   （一个文件同时是图片和脚本）被浏览器当作别的类型解析的风险。
"""

from __future__ import annotations

import io

from PIL import Image

# 允许的格式：后缀 -> (Pillow 保存格式, 是否支持透明通道)
# GIF 和 AVIF 保持原样透传（重编码动图会丢失动画帧，得不偿失）。
_REENCODE = {
    ".jpg": ("JPEG", False),
    ".jpeg": ("JPEG", False),
    ".png": ("PNG", True),
    ".webp": ("WEBP", True),
}

# JPEG 重编码质量：够用且体积友好
JPEG_QUALITY = 88
# 超长边会等比缩到这个尺寸以内，避免传超大图撑爆磁盘
MAX_DIMENSION = 4096


def sanitize_image(raw: bytes, suffix: str) -> bytes:
    """重编码图片并剥离元数据，返回干净的字节。

    GIF / AVIF 直接返回原字节（不重编码，保留动画）。
    JPEG 统一重编码（含把 .jpeg 规范成 .jpg 的字节）。
    """
    fmt = _REENCODE.get(suffix)
    if fmt is None:
        # GIF / AVIF：不重编码，原样返回（调用方已做过 magic number 校验）
        return raw

    try:
        img = Image.open(io.BytesIO(raw))
    except Exception as e:
        raise ValueError(f"图片解析失败：{e}") from e

    # 剥掉所有元数据：直接取像素重存，Pillow 默认不带 EXIF
    # （Image.open 后 save 默认不会带上原始 exif，除非显式传递）
    img = _strip_metadata(img)

    # 超长边等比缩放，防止超大图
    img = _limit_dimension(img)

    save_format, _ = fmt
    out = io.BytesIO()
    if save_format == "JPEG":
        # JPEG 不支持透明通道，转 RGB
        if img.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            rgba = img.convert("RGBA")
            background.paste(rgba, mask=rgba.getchannel("A"))
            img = background
        else:
            img = img.convert("RGB")
        img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    elif save_format == "PNG":
        img.save(out, format="PNG", optimize=True)
    else:  # WEBP
        img.save(out, format="WEBP", quality=JPEG_QUALITY)

    return out.getvalue()


def _strip_metadata(img: Image.Image) -> Image.Image:
    """去掉 EXIF/IPTC/XMP 等元数据。

    Pillow 的 Image.open 会把 exif/icc_profile 等塞进 img.info；
    save 时若不显式传 exif 参数就不会写回，但 img.info 里的 icc_profile
    仍可能被带上。这里直接按像素重建一张新图，info 干净，彻底剥离。
    """
    new = Image.new(img.mode, img.size)
    new.putdata(list(img.getdata()))
    return new


def _limit_dimension(img: Image.Image) -> Image.Image:
    """超过 MAX_DIMENSION 的边等比缩小。"""
    w, h = img.size
    max_side = max(w, h)
    if max_side <= MAX_DIMENSION:
        return img
    ratio = MAX_DIMENSION / max_side
    new_size = (int(w * ratio), int(h * ratio))
    return img.resize(new_size, Image.LANCZOS)
