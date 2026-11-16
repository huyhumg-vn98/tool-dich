"""Viết lại lời dịch cho tự nhiên kiểu người Việt + câu mở đầu giữ chân người xem + chọn từ khoá tô màu.

Chạy sau bước dịch, trước khi đổi giá tiền / rút gọn / lồng tiếng (auto_dich.hoan_thien_phu_de).
- AI (DeepSeek) tự nhận ra kiểu video: bán hàng / hướng dẫn / giải trí / kiến thức
  (hoặc dùng kiểu ghi sẵn trong Chu_De/<chủ đề>/kieu.txt).
- Viết lại từng câu theo giọng văn của kiểu đó, giữ đúng ý câu gốc, giữ nguyên con số / giá tiền,
  không dài hơn thời gian của câu (để giọng đọc không bị nhanh).
- Các câu trong 3 giây đầu được viết thành câu mở đầu thu hút (vẫn đúng ý, không bịa).
- Chọn 0-2 từ khoá quan trọng mỗi câu -> che_chu.py tô màu trên phụ đề (giá tiền tự tô, không cần chọn).
Kết quả phụ: <thư mục phụ đề>/viet_lai.json = {"kieu": ..., "tu_khoa": [...]}.
Không có API key DeepSeek hoặc AI lỗi -> giữ nguyên bản dịch.
"""
import json
import re
from pathlib import Path

import gia_tien

# ===== Cài đặt (sửa ở đây) =====
BAT = True              # False = tắt viết lại (giữ bản dịch sát nghĩa)
TOC_DO_DOC = 4.5        # số tiếng / giây tối đa cho mỗi câu viết lại
GIAY_MO_DAU = 3.0       # các câu bắt đầu trong khoảng này được viết thành câu mở đầu thu hút
# =================================

KIEU = {
    "ban_hang": ("bán hàng / giới thiệu sản phẩm",
                 "nhiệt tình, gần gũi như người bán hàng online Việt Nam (xưng mình, gọi mọi người/các bạn), "
                 "nhấn vào lợi ích và điểm nổi bật của sản phẩm"),
    "huong_dan": ("hướng dẫn / mẹo / dạy nghề",
                  "rõ ràng, dứt khoát như thầy hướng dẫn tận tình; dùng đúng thuật ngữ quen thuộc của người Việt "
                  "trong lĩnh vực đó (vd lái xe: đánh hết lái, trả lái, lùi chuồng, ghép ngang, nhả côn)"),
    "giai_tri": ("giải trí / hài / đời sống",
                 "tự nhiên, dí dỏm, bắt trend, như người kể chuyện vui trên TikTok"),
    "kien_thuc": ("kiến thức / kể chuyện / tin tức",
                  "mạch lạc, cuốn hút, như người dẫn chuyện; giữ chính xác thông tin"),
}
TEN_KIEU = {"ban hang": "ban_hang", "huong dan": "huong_dan", "giai tri": "giai_tri", "kien thuc": "kien_thuc"}

PARAMS = Path(__file__).resolve().parent / "pyvideotrans" / "videotrans" / "params.json"
API = "https://api.deepseek.com"


def _giay(t):
    h, m, r = t.strip().split(":")
    s, ms = r.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def doc_kieu(chu: str):
    """'Hướng dẫn' / 'huong_dan' / 'hướng dẫn lái xe' -> 'huong_dan' (không nhận ra -> None)."""
    import unicodedata
    s = unicodedata.normalize("NFD", (chu or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d").replace("_", " ")
    return next((v for k, v in TEN_KIEU.items() if k in s), None)


def _so(cau):
    return sorted(re.findall(r"\d+(?:[.,]\d+)?", cau))


def _hoi(key, model, noi_dung):
    import requests
    body = {"model": model, "messages": [{"role": "user", "content": noi_dung}], "reasoning_effort": "none"}
    h = {"Authorization": f"Bearer {key}"}
    r = requests.post(f"{API}/chat/completions", headers=h, json=body, timeout=240)
    if r.status_code == 400:
        body.pop("reasoning_effort")
        r = requests.post(f"{API}/chat/completions", headers=h, json=body, timeout=240)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def viet_lai(vi: Path, goc: Path, kieu: str = None) -> dict:
    """Viết lại vi.srt tại chỗ. Trả về {"kieu", "tu_khoa", "so_cau"} (rỗng nếu bỏ qua)."""
    vi, goc = Path(vi), Path(goc)
    ra = vi.parent / "viet_lai.json"
    try:
        if not BAT or ra.exists():
            return {}
        p = json.loads(PARAMS.read_text(encoding="utf-8"))
        key = (p.get("deepseek_key") or "").strip()
        model = p.get("deepseek_model") or "deepseek-flash"
        if not key:
            return {}
        k_vi = gia_tien._doc_srt(vi)
        k_goc = gia_tien._doc_srt(goc) if goc.exists() else []
        if not k_vi or len(k_goc) != len(k_vi):
            return {}
        if all(a[2].strip() == b[2].strip() for a, b in zip(k_vi, k_goc)):
            return {}        # lời do AI tự viết (video không lời) -> đã tự nhiên sẵn
        dong = []
        toi_da = []
        for i, (_, tg, chu) in enumerate(k_vi):
            a, b = (_giay(x) for x in tg.split("-->"))
            sau = _giay(k_vi[i + 1][1].split("-->")[0]) if i + 1 < len(k_vi) else b + 0.5
            n = max(3, int((max(b, sau) - a) * TOC_DO_DOC))
            toi_da.append(n)
            mo = " [CÂU MỞ ĐẦU]" if a < GIAY_MO_DAU else ""
            dong.append(f'{i + 1}. ({a:.1f}s, tối đa {n} tiếng){mo} gốc: {k_goc[i][2].replace(chr(10), " ")} '
                        f'| dịch: {chu.replace(chr(10), " ")}')
        ds_kieu = "\n".join(f"- {k}: {v[0]}" for k, v in KIEU.items())
        kieu_cho = (f'Kiểu video ĐÃ BIẾT: "{kieu}" ({KIEU[kieu][0]}).' if kieu in KIEU else
                    f"Trước hết xác định kiểu video (chọn 1):\n{ds_kieu}")
        giong = "\n".join(f"  * {k}: {v[1]}" for k, v in KIEU.items())
        noi_dung = f"""Bạn biên tập lời lồng tiếng Việt cho video ngắn TikTok dịch từ tiếng Trung.
Mỗi dòng: số câu, thời điểm, số tiếng tối đa, câu gốc tiếng Trung, bản dịch máy.

{chr(10).join(dong)}

{kieu_cho}

Viết lại TỪNG câu cho tự nhiên như người Việt nói, theo giọng văn của kiểu video:
{giong}
Quy tắc bắt buộc:
- Giữ 1 câu mới cho mỗi câu cũ, đúng ý của câu gốc đó (không dồn ý sang câu khác, không bỏ câu).
- Không dài hơn số tiếng tối đa của câu (1 tiếng = 1 chữ khi đọc).
- Giữ NGUYÊN mọi con số và giá tiền như bản dịch (vd "9,9 tệ", "30 cm"); không bịa thông tin mới.
- Các câu đánh dấu [CÂU MỞ ĐẦU]: viết thành câu mở đầu thu hút, khiến người xem muốn xem tiếp
  (câu hỏi gợi tò mò, điều bất ngờ, lợi ích rõ ràng...), nhưng vẫn đúng ý câu gốc.
- Không dùng emoji, ký hiệu, hashtag.
Chọn TỪ KHOÁ để tô màu trên phụ đề: CHỈ những cụm thật sự quan trọng (tối đa 1 cụm mỗi câu, cả video
khoảng 1 cụm cho mỗi 3 câu), mỗi cụm 2-4 chữ, chép NGUYÊN VĂN từ câu mới
(bán hàng: tên/ưu điểm nổi bật của sản phẩm; hướng dẫn: thuật ngữ, thao tác quan trọng; giải trí/kiến thức: điểm nhấn).
Không chọn giá tiền (đã tự tô). Câu không có gì nổi bật thì để trống.

Chỉ trả về JSON:
{{"kieu": "<ban_hang|huong_dan|giai_tri|kien_thuc>", "cau": {{"1": "...", "2": "..."}}, "tu_khoa": {{"1": ["..."], "2": []}}}}"""
        m = re.search(r"\{.*\}", _hoi(key, model, noi_dung), re.S)
        kq = json.loads(m.group(0)) if m else {}
        moi = kq.get("cau") or {}
        doi = 0
        tu_khoa = set()
        for i, (_, _, cu) in enumerate(k_vi):
            v = str(moi.get(str(i + 1), "")).strip()
            v = re.sub(r"[#*_~`\"“”]|[\U0001F000-\U0001FFFF☀-➿]", "", v).strip()
            # bỏ câu viết lại nếu: rỗng, dài quá, hoặc làm mất/đổi con số (giá tiền...)
            if not v or len(re.findall(r"\w+", v)) > toi_da[i] + 2 or _so(v) != _so(cu):
                continue
            if v != cu:
                k_vi[i][2] = v
                doi += 1
            for t in (kq.get("tu_khoa") or {}).get(str(i + 1)) or []:
                t = str(t).strip()
                if 2 <= len(t.split()) <= 5 and t in v and not re.search(r"\d", t):
                    tu_khoa.add(t)
        if doi:
            gia_tien._ghi_srt(vi, k_vi)
        k = kieu if kieu in KIEU else (kq.get("kieu") if kq.get("kieu") in KIEU else "")
        out = {"kieu": k, "ten_kieu": KIEU[k][0] if k else "", "tu_khoa": sorted(tu_khoa), "so_cau": doi}
        ra.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        return out
    except Exception:
        return {}


if __name__ == "__main__":
    import sys
    print(viet_lai(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else None))
