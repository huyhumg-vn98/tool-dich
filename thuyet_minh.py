"""AI xem video (không có lời nói) và viết lời thuyết minh tiếng Việt kiểu giới thiệu sản phẩm.

    python thuyet_minh.py <video> <ra_vi.srt>

Cách làm: chụp các khung hình rải đều theo thời gian -> gửi DeepSeek (mô hình xem được hình)
kèm mốc giây của từng khung -> nhận lại các câu thuyết minh có thời gian -> ghi ra phụ đề SRT.
Phụ đề này đi tiếp vào bước lồng tiếng như phụ đề đã dịch.
"""
import base64
import json
import re
import sys
from pathlib import Path

import cv2
import requests

GOC = Path(__file__).resolve().parent
PARAMS = GOC / "pyvideotrans" / "videotrans" / "params.json"
API = "https://api.deepseek.com"

# ===== Cài đặt (sửa ở đây) =====
KIEU_LOI = "giới thiệu / bán sản phẩm"
AM_TIET_MOI_GIAY = 4.0     # tốc độ đọc mục tiêu (số chữ tiếng Việt / giây) để giọng đọc không phải đọc nhanh
# =================================

HUONG_DAN = """Bạn là người viết kịch bản lồng tiếng cho video ngắn TikTok/Douyin bán hàng.
Video dài {dai:.1f} giây, KHÔNG có lời nói. Dưới đây là các khung hình theo thời gian (mốc giây ghi trước mỗi ảnh).

Hãy viết lời thuyết minh tiếng Việt kiểu {kieu}:
- Mở đầu thu hút ngay câu đầu, giới thiệu sản phẩm, nêu điểm nổi bật đúng với cảnh đang chiếu, kết bằng 1 câu kêu gọi
  (vd "Mua ngay kẻo lỡ nhé!", "Bấm vào giỏ hàng để sở hữu ngay").
- Giọng tự nhiên, gần gũi, câu ngắn gọn như người Việt nói chuyện. Không dùng ký hiệu, emoji, hashtag.
- Chữ Trung/Anh trên sản phẩm hay trên màn hình: hiểu ý rồi diễn đạt bằng tiếng Việt, không phiên âm.
- KHÔNG bịa giá tiền, thông số, khuyến mãi, thương hiệu nếu không thấy rõ trong video.
- Chia thành các câu khớp với cảnh: mỗi câu 2-6 giây, câu sau bắt đầu sau khi câu trước kết thúc,
  để trống 0.2-0.5 giây giữa các câu, phủ gần hết video (từ khoảng giây 0.3 đến gần cuối).
- Độ dài mỗi câu: tối đa {tg} chữ (tiếng) cho mỗi giây của câu đó, để đọc kịp với tốc độ bình thường.

Ngoài ra chọn 2-4 "điểm nhấn" để máy quay từ từ đẩy cận (zoom chậm) vào CHỖ ĐẸP / HẤP DẪN / NGON MẮT NHẤT
của cảnh: món ăn/đồ uống trông ngon nhất, lúc rót/đổ/cắt, chi tiết sản phẩm đẹp, logo/nhãn sản phẩm rõ nhất.
Mỗi điểm nhấn:
- "t": giây bắt đầu đẩy cận (đầu đoạn cảnh có chi tiết đó), các điểm cách nhau ít nhất 2.5 giây;
- "x", "y": vị trí tâm của chi tiết đẹp nhất đó trong khung hình, tỉ lệ 0-1 tính từ mép trái / mép trên.

Chỉ trả về JSON đúng dạng sau, không thêm gì khác:
{{"cau": [{{"bat_dau": 0.3, "ket_thuc": 3.2, "loi": "..."}}, ...],
  "nhan": [{{"t": 0.3, "x": 0.5, "y": 0.55}}, ...]}}"""


def doc_key():
    p = json.loads(PARAMS.read_text(encoding="utf-8")) if PARAMS.exists() else {}
    key = (p.get("deepseek_key") or "").strip()
    if not key:
        raise SystemExit("LOI: Chưa có API key DeepSeek - nhập key ở ô DeepSeek trên giao diện.")
    return key


def chon_mo_hinh(key):
    """Mô hình DeepSeek xem được hình ảnh."""
    try:
        r = requests.get(f"{API}/models", headers={"Authorization": f"Bearer {key}"}, timeout=20)
        ds = r.json().get("data", [])
        xem_hinh = [m["id"] for m in ds if "image" in (m.get("input_modalities") or [])]
        if xem_hinh:
            return next((m for m in xem_hinh if "flash" in m), xem_hinh[0])
    except Exception:
        pass
    return "deepseek-flash"


def chup_khung(video):
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    tong = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    dai = tong / fps
    n = int(min(20, max(6, round(dai / 2))))
    khung = []
    for i in range(n):
        t = dai * (i + 0.5) / n
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
        ok, f = cap.read()
        if not ok:
            continue
        h, w = f.shape[:2]
        tl = 512 / max(h, w)
        if tl < 1:
            f = cv2.resize(f, None, fx=tl, fy=tl, interpolation=cv2.INTER_AREA)
        ok, b = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 80])
        khung.append((t, base64.b64encode(b).decode()))
    cap.release()
    return dai, khung


def hoi_ai(key, dai, khung):
    noi_dung = [{"type": "text", "text": HUONG_DAN.format(dai=dai, kieu=KIEU_LOI, tg=AM_TIET_MOI_GIAY)}]
    for t, b64 in khung:
        noi_dung.append({"type": "text", "text": f"Giây {t:.1f}:"})
        noi_dung.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    mo_hinh = chon_mo_hinh(key)
    loi_cuoi = ""
    for _ in range(3):
        try:
            r = requests.post(f"{API}/chat/completions", headers={"Authorization": f"Bearer {key}"},
                              json={"model": mo_hinh, "messages": [{"role": "user", "content": noi_dung}],
                                    "reasoning_effort": "low"}, timeout=180)
            if r.status_code == 401:
                raise SystemExit("LOI: API key DeepSeek không đúng.")
            if r.status_code == 402:
                raise SystemExit("LOI: Tài khoản DeepSeek hết tiền.")
            r.raise_for_status()
            chu = r.json()["choices"][0]["message"]["content"]
            m = re.search(r"\{.*\}", chu, re.S)
            kq = json.loads(m.group(0)) if m else {}
            cau = kq.get("cau") or []
            if cau:
                return cau, kq.get("nhan") or []
            loi_cuoi = "AI trả về không đúng dạng"
        except SystemExit:
            raise
        except Exception as e:
            loi_cuoi = str(e)
    raise SystemExit(f"LOI: Không viết được lời thuyết minh ({loi_cuoi[:200]})")


def don_dep(cau, dai):
    """Sắp xếp, cắt trùng giờ, giữ trong độ dài video."""
    ra = []
    for c in cau:
        try:
            a, b, loi = float(c["bat_dau"]), float(c["ket_thuc"]), str(c["loi"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        loi = re.sub(r"[#*_~`\"“”]|[\U0001F000-\U0001FFFF☀-➿]", "", loi).strip()
        if loi:
            ra.append([max(0.0, a), min(dai, b), loi])
    ra.sort()
    for n in range(1, len(ra)):
        if ra[n][0] < ra[n - 1][1] + 0.1:
            ra[n][0] = ra[n - 1][1] + 0.1
    return [c for c in ra if c[1] - c[0] >= 0.8]


def tg(x):
    ms = int(round(x * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def viet(video, ra):
    key = doc_key()
    dai, khung = chup_khung(video)
    if not khung:
        raise SystemExit("LOI: Không đọc được hình trong video.")
    cau, nhan = hoi_ai(key, dai, khung)
    cau = don_dep(cau, dai)
    if not cau:
        raise SystemExit("LOI: AI không viết được câu nào.")
    # điểm nhấn phóng to / thu nhỏ (hieu_ung.py); AI không chọn thì tự đặt: câu mở đầu, giữa, câu kêu gọi
    def hop_le(d):
        try:
            return 0 <= float(d["t"]) < dai - 0.5
        except (KeyError, TypeError, ValueError):
            return False
    nhan = [d for d in nhan if isinstance(d, dict) and hop_le(d)]
    if not nhan:
        giua = cau[len(cau) // 2]
        nhan = [{"t": cau[0][0], "x": 0.5, "y": 0.5}, {"t": giua[0], "x": 0.5, "y": 0.5},
                {"t": cau[-1][0], "x": 0.5, "y": 0.5}]
    (Path(ra).parent / "hieu_ung.json").write_text(json.dumps(nhan, ensure_ascii=False), encoding="utf-8")
    Path(ra).write_text("\n\n".join(f"{n}\n{tg(a)} --> {tg(b)}\n{loi}" for n, (a, b, loi) in enumerate(cau, 1)) + "\n",
                        encoding="utf-8")
    print(f"Đã viết {len(cau)} câu thuyết minh, {len(nhan)} điểm nhấn.")


if __name__ == "__main__":
    viet(sys.argv[1], sys.argv[2])
