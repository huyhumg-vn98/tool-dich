"""Rút gọn câu dịch quá dài so với thời gian của nó, để giọng đọc không phải tăng tốc (nghe bị nhanh).

Mỗi câu có "chỗ trống" = từ lúc câu bắt đầu đến lúc câu sau bắt đầu. Câu nào có nhiều tiếng hơn
TOC_DO_TOI_DA x chỗ trống thì nhờ DeepSeek viết lại ngắn hơn (giữ ý, giữ giá tiền).
Không có API key DeepSeek thì bỏ qua, giữ nguyên câu.
"""
import json
import re
from pathlib import Path

import gia_tien

# ===== Cài đặt (sửa ở đây) =====
TOC_DO_TOI_DA = 5.0     # số tiếng mỗi giây tối đa (đọc bình thường ~4-5 tiếng/giây)
TOC_DO_DOC = 4.5        # tốc độ đọc ước tính để chia lại thời gian giữa các câu
LECH_TOI_DA = 0.6       # mỗi câu được dời sớm/muộn tối đa bao nhiêu giây so với gốc
# =================================

PARAMS = Path(__file__).resolve().parent / "pyvideotrans" / "videotrans" / "params.json"
API = "https://api.deepseek.com"


def _giay(t):
    h, m, r = t.strip().split(":")
    s, ms = r.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def so_tieng(cau: str) -> int:
    """Số tiếng khi đọc (con số tính theo cách đọc thành chữ)."""
    return len(re.findall(r"\w+", gia_tien.chuan_hoa_doc(cau)))


def cau_qua_dai(khoi) -> dict:
    """{chỉ số: số tiếng tối đa} cho các câu quá dài."""
    ra = {}
    for i, (_, tg, chu) in enumerate(khoi):
        try:
            a, b = (_giay(x) for x in tg.split("-->"))
            sau = _giay(khoi[i + 1][1].split("-->")[0]) if i + 1 < len(khoi) else b + 0.5
        except Exception:
            continue
        cho = max(b, sau) - a
        toi_da = max(2, int(cho * TOC_DO_TOI_DA))
        if so_tieng(chu) > toi_da:
            ra[i] = toi_da
    return ra


def _hoi(key, model, noi_dung):
    import requests
    body = {"model": model, "messages": [{"role": "user", "content": noi_dung}], "reasoning_effort": "none"}
    r = requests.post(f"{API}/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=body, timeout=120)
    if r.status_code == 400:
        body.pop("reasoning_effort")
        r = requests.post(f"{API}/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=body, timeout=120)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def rut_gon(vi: Path) -> int:
    """Viết lại ngắn hơn các câu quá dài trong vi.srt (tại chỗ). Trả về số câu đã rút gọn."""
    try:
        p = json.loads(PARAMS.read_text(encoding="utf-8"))
        key = (p.get("deepseek_key") or "").strip()
        model = p.get("deepseek_model") or "deepseek-flash"
        if not key:
            return 0
        khoi = gia_tien._doc_srt(vi)
        dai = cau_qua_dai(khoi)
        if not dai:
            return 0
        ds = "\n".join(f"{i + 1}. {c.replace(chr(10), ' ')}" for i, (_, _, c) in enumerate(khoi))
        yeu_cau = "\n".join(f'- Câu {i + 1}: tối đa {n} tiếng (hiện {so_tieng(khoi[i][2])} tiếng): "{khoi[i][2]}"'
                            for i, n in dai.items())
        noi_dung = f"""Đây là lời lồng tiếng Việt của 1 video bán hàng ngắn (mỗi dòng 1 câu, đọc theo thứ tự):
{ds}

Một số câu quá dài so với thời gian, giọng đọc phải đọc rất nhanh. Viết lại NGẮN HƠN các câu sau,
đúng số tiếng tối đa (1 tiếng = 1 chữ khi đọc; con số tính theo cách đọc, vd "269 cành" = 5 tiếng):
{yeu_cau}

Quy tắc: giữ ý chính và giọng văn nói tự nhiên, nối mạch với câu trước/sau; bỏ chữ thừa, dùng từ ngắn hơn;
giữ nguyên giá tiền cụ thể (vd "270 cành"); riêng khoảng giá ước lượng (vd "380 đến 770 cành") nếu quá dài
thì được nói gọn kiểu "vài trăm cành", "mấy trăm cành", "gần nghìn cành"; không thêm ý mới.
Chỉ trả về JSON: {{"<số câu>": "<câu mới>", ...}}"""
        da = 0
        for _ in range(2):
            m = re.search(r"\{.*\}", _hoi(key, model, noi_dung), re.S)
            moi = json.loads(m.group(0)) if m else {}
            for k, v in moi.items():
                try:
                    i = int(k) - 1
                except ValueError:
                    continue
                v = str(v).strip()
                if i in dai and v and so_tieng(v) < so_tieng(khoi[i][2]):
                    khoi[i][2] = v
                    da += 1
            if da:
                break
        if da:
            gia_tien._ghi_srt(vi, khoi)
        return da
    except Exception:
        return 0


def _tg(x):
    ms = int(round(max(0, x) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def chia_lai_thoi_gian(vi: Path) -> int:
    """Câu còn chật thì mượn thời gian của câu bên cạnh đang dư (dời đầu câu sớm/muộn tối đa LECH_TOI_DA giây).
    Trả về số câu đã dời."""
    try:
        khoi = gia_tien._doc_srt(vi)
        n = len(khoi)
        if n < 2:
            return 0
        goc = [_giay(k[1].split("-->")[0]) for k in khoi]
        het = [_giay(k[1].split("-->")[1]) for k in khoi]
        t = goc[:]
        cuoi = max(het[-1], goc[-1]) + 0.3
        can = [so_tieng(k[2]) / TOC_DO_DOC + 0.1 for k in khoi]

        def cho(i):
            return (t[i + 1] if i + 1 < n else cuoi) - t[i]

        for _ in range(4):
            for i in range(n):
                thieu = can[i] - cho(i)
                if thieu <= 0.02:
                    continue
                # 1) dời câu sau muộn hơn (nếu câu sau còn dư)
                if i + 1 < n:
                    du_sau = cho(i + 1) - can[i + 1]
                    d = min(thieu, max(0, du_sau), LECH_TOI_DA - (t[i + 1] - goc[i + 1]))
                    if d > 0:
                        t[i + 1] += d
                        thieu -= d
                # 2) bắt đầu câu này sớm hơn (nếu câu trước còn dư)
                if thieu > 0.02 and i > 0:
                    du_truoc = cho(i - 1) - can[i - 1]
                    d = min(thieu, max(0, du_truoc), LECH_TOI_DA - (goc[i] - t[i]))
                    if d > 0:
                        t[i] -= d
        doi = sum(1 for a, b in zip(t, goc) if abs(a - b) > 0.01)
        if doi:
            for i in range(n):
                # giữ độ dài hiện chữ như cũ, không đè lên câu sau
                ket = max(het[i] + (t[i] - goc[i]), t[i] + can[i])
                if i + 1 < n:
                    ket = min(ket, t[i + 1])
                khoi[i][1] = f"{_tg(t[i])} --> {_tg(ket)}"
            gia_tien._ghi_srt(vi, khoi)
        return doi
    except Exception:
        return 0


if __name__ == "__main__":
    import sys
    print("Đã rút gọn", rut_gon(Path(sys.argv[1])), "câu")
