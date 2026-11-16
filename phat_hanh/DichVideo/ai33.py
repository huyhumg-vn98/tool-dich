"""Kết nối API ai33.pro (OpenSpeaker) để lồng tiếng bằng giọng ElevenLabs, Vbee, Minimax...

API key lưu trong file .ai33_key (chỉ nằm trên máy bạn).
"""
import json
import os
import time
from pathlib import Path

import requests

GOC = Path(__file__).resolve().parent
FILE_KEY = GOC / ".ai33_key"
FILE_YEU_THICH = GOC / ".giong_ai33.json"
API = "https://api.ai33.pro"
NHA_CUNG_CAP = ["vbee", "elevenlabs", "minimax", "edge", "clone", "fishaudio", "kokoro"]


class LoiAi33(RuntimeError):
    pass


def doc_key() -> str:
    try:
        return FILE_KEY.read_text().strip()
    except Exception:
        return ""


def luu_key(key: str):
    FILE_KEY.write_text(key.strip())
    os.chmod(FILE_KEY, 0o600)


def _h():
    key = doc_key()
    if not key:
        raise LoiAi33("Chưa nhập API key ai33.")
    return {"xi-api-key": key}


def _json(r):
    try:
        d = r.json()
    except ValueError:
        raise LoiAi33(f"ai33 trả lỗi HTTP {r.status_code}")
    if r.status_code >= 400 or (isinstance(d, dict) and d.get("success") is False):
        msg = d.get("message") or d.get("error") or d.get("detail") or f"HTTP {r.status_code}"
        raise LoiAi33(f"ai33: {msg}")
    return d


def so_credit() -> int:
    return _json(requests.get(f"{API}/v1/credits", headers=_h(), timeout=15)).get("credits", 0)


def tim_giong(provider: str, q: str = "", page: int = 1, chi_tieng_viet: bool = True,
              gioi_tinh: str = "", moi_trang: int = 24) -> dict:
    if chi_tieng_viet and provider == "fishaudio":
        # Fish Audio không lọc được theo tiếng Việt (trả về toàn bộ) -> bỏ nhóm tiếng Việt
        return {"data": [], "pagination": {"total": 0, "has_more": False}}
    params = {"provider": provider, "page": page, "page_size": max(1, min(100, moi_trang))}
    if q:
        params["search"] = q
    if chi_tieng_viet:
        params["language"] = "Vietnamese"
    if gioi_tinh in ("male", "female"):
        params["gender"] = gioi_tinh
    d = _json(requests.get(f"{API}/v3/voices", headers=_h(), params=params, timeout=20))
    return {"data": d.get("data", []), "pagination": d.get("pagination", {})}


class LoiTamThoi(LoiAi33):
    """Lỗi bận / mạng chập chờn: chờ một lúc rồi thử lại là được."""


def _tam_thoi(e: Exception) -> bool:
    if isinstance(e, (requests.RequestException, LoiTamThoi)):
        return True
    s = str(e).lower()
    return any(k in s for k in ("busy", "temporar", "try again", "timeout", "rate limit",
                                "too many", "http 429", "http 50"))


def _gui(text, voice_id, speed) -> str:
    d = _json(requests.post(f"{API}/v3/text-to-speech", headers=_h(), timeout=30,
                            data={"text": text, "voice_id": voice_id, "speed": str(speed),
                                  "with_transcript": "false"}))
    task = d.get("task_id")
    if not task:
        raise LoiTamThoi("ai33 không trả task_id.")
    return task


def _cho_xong(task: str, cho_toi_da: int) -> str:
    bat_dau = time.time()
    cho = 1.0
    loi_hoi = 0
    while time.time() - bat_dau < cho_toi_da:
        time.sleep(cho)
        cho = min(cho * 1.3, 4)
        try:
            t = _json(requests.get(f"{API}/v1/task/{task}", headers=_h(), timeout=20))
        except Exception as e:
            # ai33 hay báo "Task polling temporarily busy": câu vẫn đang làm, chỉ là hỏi bị từ chối -> hỏi lại sau
            if _tam_thoi(e) and loi_hoi < 30:
                loi_hoi += 1
                cho = max(cho, 3)
                continue
            raise
        if t.get("status") == "done":
            url = (t.get("metadata") or {}).get("audio_url")
            if not url:
                raise LoiTamThoi("ai33 xong nhưng không có link âm thanh.")
            return url
        if t.get("status") == "error":
            raise LoiTamThoi(f"ai33 lỗi: {t.get('error_message') or 'không rõ'}")
    raise LoiTamThoi("ai33 xử lý quá lâu.")


def doc_ra(text: str, voice_id: str, speed: float = 1.0, cho_toi_da: int = 300, so_lan: int = 3) -> str:
    """Gửi 1 đoạn văn bản, chờ ai33 làm xong, trả về link file âm thanh. Lỗi tạm thời thì tự thử lại."""
    speed = max(0.5, min(1.5, float(speed or 1)))
    loi = None
    for lan in range(so_lan):
        try:
            return _cho_xong(_gui(text, voice_id, speed), cho_toi_da)
        except Exception as e:
            loi = e
            if not _tam_thoi(e):
                raise
            time.sleep(3 * (lan + 1))
    raise loi


# ----- Giọng yêu thích (hiện trong danh sách chọn giọng) -----
def ds_yeu_thich() -> list:
    try:
        return json.loads(FILE_YEU_THICH.read_text(encoding="utf-8"))
    except Exception:
        return []


def them_yeu_thich(voice_id: str, ten: str):
    ds = [g for g in ds_yeu_thich() if g["voice_id"] != voice_id]
    ds.append({"voice_id": voice_id, "ten": ten})
    FILE_YEU_THICH.write_text(json.dumps(ds, ensure_ascii=False, indent=1), encoding="utf-8")


def bo_yeu_thich(voice_id: str):
    ds = [g for g in ds_yeu_thich() if g["voice_id"] != voice_id]
    FILE_YEU_THICH.write_text(json.dumps(ds, ensure_ascii=False, indent=1), encoding="utf-8")
