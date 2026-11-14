"""Lưu API key DeepSeek vào cài đặt của pyVideoTrans và kiểm tra key."""
import json
from pathlib import Path

import requests

PARAMS = Path(__file__).resolve().parent / "pyvideotrans/videotrans/params.json"
API = "https://api.deepseek.com"


def _doc():
    try:
        return json.loads(PARAMS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _ghi(p):
    PARAMS.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")


def doc_key() -> str:
    return _doc().get("deepseek_key", "").strip()


def kiem_tra(key: str = "") -> dict:
    """Gọi DeepSeek lấy danh sách mô hình + số dư. Trả về dict thông tin, hoặc {'loi': ...}."""
    key = key or doc_key()
    if not key:
        return {"co_key": False}
    h = {"Authorization": f"Bearer {key}"}
    try:
        r = requests.get(f"{API}/models", headers=h, timeout=15)
        if r.status_code == 401:
            return {"co_key": True, "loi": "API key DeepSeek không đúng."}
        r.raise_for_status()
        models = [m["id"] for m in r.json().get("data", [])]
    except Exception as e:
        return {"co_key": True, "loi": f"Không kết nối được DeepSeek: {e}"}
    so_du = ""
    try:
        b = requests.get(f"{API}/user/balance", headers=h, timeout=15).json()
        info = (b.get("balance_infos") or [{}])[0]
        so_du = f"{info.get('total_balance', '?')} {info.get('currency', '')}".strip()
    except Exception:
        pass
    return {"co_key": True, "models": models, "model": _doc().get("deepseek_model", ""), "so_du": so_du}


def luu_key(key: str) -> dict:
    kq = kiem_tra(key)
    if kq.get("loi"):
        return kq
    p = _doc()
    p["deepseek_key"] = key.strip()
    models = kq.get("models", [])
    # chọn mô hình dịch: giữ cái đang đặt nếu hợp lệ, không thì ưu tiên bản nhanh/rẻ
    if p.get("deepseek_model") not in models and models:
        p["deepseek_model"] = next((m for m in models if "flash" in m), None) \
            or next((m for m in models if "chat" in m), models[0])
    p["deepseek_reasoning_effort"] = "none"  # dịch không cần suy luận dài, nhanh và rẻ hơn
    _ghi(p)
    kq["model"] = p.get("deepseek_model", "")
    return kq
