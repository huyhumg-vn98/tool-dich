"""Tải video Douyin (MP4) từ link chia sẻ.

Dựa theo code trong "tool affiliate của huy/DOUYIN_DOWNLOAD.md":
  1. Lọc link từ đoạn chữ chia sẻ, đổi link rút gọn thành douyin.com/video/<id>.
  2. Hỏi SaveTik link MP4 rồi tải về.
  3. SaveTik lỗi thì thử yt-dlp (cần file cookies.txt, xem DOUYIN_COOKIES_FILE bên dưới).

    python tai_douyin.py <thư_mục_lưu> "<đoạn chữ có link>"
Tải xong in ra:  FILE:<đường dẫn>
"""
import html
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

SAVETIK_SEARCH_URL = "https://savetik.io/api/ajaxSearch"
# Tuỳ chọn: đường dẫn file cookies.txt (Netscape) xuất từ trình duyệt đã mở douyin.com,
# chỉ dùng khi SaveTik không tải được. Để trống nếu không cần.
DOUYIN_COOKIES_FILE = ""
MAX_BYTES = 500 * 1024 * 1024


class LoiTai(RuntimeError):
    pass


def loc_link(chu: str) -> list:
    ds = []
    for l in re.findall(r"https?://[^\s，。！？、\"'<>]+", chu):
        l = l.rstrip(".,;:)]}")
        if l not in ds:
            ds.append(l)
    return ds


def la_douyin(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in ("douyin.com", "iesdouyin.com"))


def id_video(url: str):
    p = urlparse(url)
    m = re.search(r"/(?:share/)?video/(\d+)", p.path)
    if m:
        return m.group(1)
    modal = parse_qs(p.query).get("modal_id", [""])[0]
    return modal if modal.isdigit() else None


def link_day_du(url: str) -> str:
    """Đổi link rút gọn v.douyin.com thành https://www.douyin.com/video/<id>."""
    vid = id_video(url)
    if vid is None:
        try:
            r = requests.get(url, allow_redirects=True, timeout=(10, 20),
                             headers={"User-Agent": "Mozilla/5.0"}, stream=True)
            r.close()
        except requests.RequestException as e:
            raise LoiTai("Không mở được link Douyin. Kiểm tra link còn hoạt động.") from e
        if not la_douyin(r.url):
            raise LoiTai("Link rút gọn không dẫn tới video Douyin.")
        vid = id_video(r.url)
    if vid is None:
        raise LoiTai("Không tìm thấy mã video trong link Douyin.")
    return f"https://www.douyin.com/video/{vid}"


def tai_file(url: str, dich: Path):
    with requests.get(url, stream=True, timeout=(10, 120),
                      headers={"User-Agent": "Mozilla/5.0"}) as r:
        r.raise_for_status()
        da_tai = 0
        with dich.open("wb") as f:
            for chunk in r.iter_content(256 * 1024):
                if chunk:
                    da_tai += len(chunk)
                    if da_tai > MAX_BYTES:
                        raise LoiTai("Video quá lớn.")
                    f.write(chunk)
    if dich.stat().st_size < 50 * 1024:
        raise LoiTai("File tải về không phải video.")


def qua_savetik(url: str, thu_muc: Path) -> Path:
    payload = None
    for lan in range(3):   # SaveTik hay chậm/quá tải, mạng chập chờn -> thử lại
        try:
            r = requests.post(
                SAVETIK_SEARCH_URL,
                data={"q": url, "lang": "vi", "cursor": "0", "page": "0"},
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://savetik.io/vi/douyin-video-downloader",
                    "X-Requested-With": "XMLHttpRequest",
                },
                timeout=(10, 45),
            )
            r.raise_for_status()
            payload = r.json()
            break
        except (requests.RequestException, ValueError) as e:
            if lan == 2:
                raise LoiTai(f"SaveTik không phản hồi - mạng tới savetik.io lỗi hoặc trang quá tải ({type(e).__name__})") from e
            import time
            time.sleep(5)
    trang = payload.get("data") if isinstance(payload, dict) else None
    if payload.get("status") != "ok" or not isinstance(trang, str):
        raise LoiTai("SaveTik không phân tích được video này.")

    links = re.findall(r'<a[^>]*href="(https://[^"]+)"[^>]*>(.*?)</a>', trang, re.S)
    mp4 = [(html.unescape(l), nhan) for l, nhan in links if "MP4" in nhan]
    # ưu tiên bản HD, rồi tới bản thường
    mp4.sort(key=lambda x: 0 if "HD" in x[1] else 1)
    if not mp4:
        raise LoiTai("SaveTik không trả về link MP4.")
    m = re.search(r'id="TikTokId" value="(\d+)"', trang)
    vid = m.group(1) if m else (id_video(url) or "douyin")
    dich = thu_muc / f"douyin_{vid}.mp4"
    loi_tai = ""
    for link, _ in mp4:
        try:
            tai_file(link, dich)
            return dich
        except (requests.RequestException, LoiTai, OSError) as e:
            loi_tai = type(e).__name__
            dich.unlink(missing_ok=True)
    raise LoiTai(f"Không tải được file MP4 (mạng đứt khi tải: {loi_tai})")


def qua_ytdlp(url: str, thu_muc: Path) -> Path:
    from yt_dlp import YoutubeDL
    opts = {
        "outtmpl": str(thu_muc / "douyin_%(id)s.%(ext)s"),
        "format": "bv*+ba/b", "merge_output_format": "mp4",
        "noplaylist": True, "quiet": True, "no_warnings": True,
    }
    if DOUYIN_COOKIES_FILE:
        opts["cookiefile"] = DOUYIN_COOKIES_FILE
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            p = Path(ydl.prepare_filename(info))
    except Exception as e:
        if "cookie" in str(e).lower():
            raise LoiTai("Douyin cần cookies (đặt DOUYIN_COOKIES_FILE trong tai_douyin.py).") from e
        raise LoiTai("yt-dlp không tải được video này.") from e
    mp4 = p.with_suffix(".mp4")
    return mp4 if mp4.exists() else p


def la_link_truc_tiep(url: str) -> bool:
    """Link thẳng tới file video (vd .../douyinvod.com/... hoặc ...mp4)."""
    p = urlparse(url)
    host = (p.hostname or "").lower()
    return (host.endswith("douyinvod.com") or p.path.lower().endswith((".mp4", ".mov", ".webm"))
            or "mime_type=video_mp4" in p.query)


def tai_truc_tiep(url: str, thu_muc: Path) -> Path:
    import hashlib
    ten = "douyin_" + hashlib.md5(urlparse(url).path.encode()).hexdigest()[:12] + ".mp4"
    dich = thu_muc / ten
    try:
        with requests.get(url, stream=True, timeout=(10, 120),
                          headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.douyin.com/"}) as r:
            if r.status_code in (403, 404, 410):
                raise LoiTai("Link video đã hết hạn hoặc không còn. Hãy lấy link mới.")
            r.raise_for_status()
            with dich.open("wb") as f:
                for chunk in r.iter_content(256 * 1024):
                    f.write(chunk)
    except requests.RequestException as e:
        dich.unlink(missing_ok=True)
        raise LoiTai("Không tải được link video trực tiếp.") from e
    if dich.stat().st_size < 50 * 1024:
        dich.unlink(missing_ok=True)
        raise LoiTai("Link không trả về file video.")
    return dich


def tai(link: str, thu_muc: Path) -> Path:
    thu_muc.mkdir(parents=True, exist_ok=True)
    if la_link_truc_tiep(link):
        return tai_truc_tiep(link, thu_muc)
    url = link_day_du(link) if la_douyin(link) else link
    try:
        return qua_savetik(url, thu_muc)
    except LoiTai as e:
        print(f"    SaveTik lỗi ({e}), thử yt-dlp...", flush=True)
    return qua_ytdlp(url, thu_muc)


def main():
    thu_muc = Path(sys.argv[1])
    links = loc_link(" ".join(sys.argv[2:]))
    if not links:
        print("Không tìm thấy link nào.")
        return
    for i, l in enumerate(links, 1):
        print(f"  Đang tải [{i}/{len(links)}]: {l}", flush=True)
        try:
            f = tai(l, thu_muc)
            print(f"  ✔ Đã tải: {f.name}", flush=True)
            print(f"FILE:{f.resolve()}", flush=True)
        except Exception as e:
            print(f"  ✖ Không tải được: {e}", flush=True)
            print(f"LOI:{l}", flush=True)


if __name__ == "__main__":
    main()
