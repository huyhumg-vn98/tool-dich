"""Che chữ gốc trên video và đặt phụ đề tiếng Việt đúng vào chỗ đó.

    python che_chu.py <video_vào> <phụ_đề.srt> <video_ra>

Cách làm (theo dõi từng dòng chữ gốc):
1. Đọc chữ (OCR) trên các khung hình, lấy các dòng chữ kiểu phụ đề.
2. Gom thành từng "dòng chữ gốc": vị trí, kích thước, lúc hiện - lúc tắt.
3. Tìm chính xác khung hình chữ hiện/tắt (so sánh điểm ảnh trong vùng chữ).
4. Che đúng vùng chữ của từng dòng, chỉ trong lúc nó hiện.
5. Mỗi câu tiếng Việt đặt vào đúng chỗ dòng chữ gốc đang hiện cùng lúc.
"""
import difflib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

_moc_tien_do = {}


def bao_tien_do(viec, k, tong):
    """Ghi % tiến độ ra file (giao diện hàng chờ đọc file này). Chỉ ghi khi chạy từ hàng chờ."""
    f = os.environ.get("TIEN_DO")
    if not f or tong <= 0:
        return
    import time
    bd = _moc_tien_do.setdefault(viec, time.time())
    pt = min(100, int(100 * k / tong))
    chu = f"{viec} {pt}%"
    da = time.time() - bd
    if k > 0 and da > 5 and pt < 100:
        con = da / k * (tong - k)
        chu += f" · còn ~{int(con // 60)} phút" if con >= 90 else f" · còn ~{int(con)} giây"
    try:
        Path(f).write_text(chu, encoding="utf-8")
    except OSError:
        pass

# ===== Cài đặt (sửa ở đây) =====
KIEU_CHE = "ai"            # "ai":  AI xoá sạch chữ gốc (vẽ lại nền) + chữ Việt viền đen, không khung
                           #        (thiếu mô hình/torch thì tự dùng "den")
                           # "den": 1 khung đen kín phủ cả chữ gốc lẫn chữ Việt
                           # "xoa": xoá mờ chữ gốc + chữ Việt viền đen, không khung
FONT = "Avenir Next Bold" if sys.platform == "darwin" else "Arial"   # font đủ dấu tiếng Việt
MAU_CHU = "&H00FFFFFF"     # màu chữ Việt, dạng &H00BBGGRR: trắng &H00FFFFFF, vàng &H0000FFFF
MAU_VIEN = "&H00000000"    # màu viền chữ (đen)
CO_CHU = 0.05              # cỡ chữ = 5% bề ngang video (tự co giãn theo chữ gốc)
MAU_KHUNG = "black"        # (kiểu "den") màu khung che
CRF = 16                   # chất lượng video ra: 16 = gần như không mất chất lượng; 18-20 = file nhẹ hơn
# =================================

WIN = sys.platform == "win32"
if WIN:   # bộ cài Windows để ffmpeg trong thư mục tool
    FFMPEG = str(Path(__file__).resolve().parent / "ffmpeg" / "bin" / "ffmpeg.exe")
    FFPROBE = str(Path(__file__).resolve().parent / "ffmpeg" / "bin" / "ffprobe.exe")
else:
    BREW = "/opt/homebrew" if Path("/opt/homebrew/bin/brew").exists() else "/usr/local"
    FFMPEG = f"{BREW}/opt/ffmpeg-full/bin/ffmpeg"     # ffmpeg đầy đủ (có chèn phụ đề)
    FFPROBE = f"{BREW}/opt/ffmpeg-full/bin/ffprobe"
if not Path(FFMPEG).exists():
    FFMPEG, FFPROBE = "ffmpeg", "ffprobe"
# Font Mac "Avenir Next Bold" đã là kiểu đậm; Windows dùng "Arial" + bật in đậm
IN_DAM = 0 if "Bold" in FONT else 1
# Kích thước chữ để tự khớp cỡ: 1 ký tự rộng bao nhiêu / nét cao bao nhiêu (tính theo cỡ chữ)
RONG_KT, CAO_NET = (0.38, 0.74) if "Avenir" in FONT else (0.46, 0.88)


# ---------- 1. Đọc chữ ----------
def doc_chu(video: str):
    from rapidocr import RapidOCR
    ocr = RapidOCR(params={"Global.log_level": "error"})
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    tong = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    mau = 2 if tong / fps <= 90 else 1          # số khung đọc mỗi giây
    buoc = max(1, int(round(fps / mau)))
    ti_le = min(1.0, 720 / W)
    mau_thu = []                                 # [(frame, [hộp chữ])]
    for i in range(0, tong, buoc):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = cap.read()
        if not ok:
            break
        nho = cv2.resize(frame, None, fx=ti_le, fy=ti_le) if ti_le < 1 else frame
        kq = ocr(nho)
        hop = []
        if kq is not None and kq.boxes is not None:
            for box, txt, diem in zip(kq.boxes, kq.txts, kq.scores):
                txt = txt.strip()
                if diem < 0.6 or len(re.sub(r"[\W\d_]", "", txt)) < 2:
                    continue
                xs = [p[0] / ti_le for p in box]
                ys = [p[1] / ti_le for p in box]
                hop.append([min(xs), min(ys), max(xs), max(ys), txt])
        mau_thu.append((i, hop))
        bao_tien_do("Tìm chữ gốc", i, tong)
    cap.release()
    return W, H, fps, buoc, tong, mau_thu


# ---------- 2. Lọc chữ kiểu phụ đề, gom dòng ----------
def la_phu_de(h, W, H):
    """Chữ có dáng phụ đề: cỡ vừa phải, dòng ngang, nằm chính giữa bề ngang."""
    x1, y1, x2, y2, _ = h
    cao, rong, tam_x = y2 - y1, x2 - x1, (x1 + x2) / 2
    if cao < 0.018 * H or cao > 0.09 * H:      # quá nhỏ (chữ trên sản phẩm) hoặc quá to
        return False
    if rong < cao * 1.5:                        # chữ dọc / logo
        return False
    return abs(tam_x - W / 2) < 0.06 * W        # phụ đề được căn giữa; chữ trong cảnh thì lệch


def tim_lan(mau_thu, W, H):
    """Tìm các 'làn phụ đề': độ cao nơi chữ căn giữa xuất hiện lặp lại nhiều lần.

    Trả về [(tâm_y, chiều_cao_dòng)]. Chữ trong cảnh (biển số, chữ trên xe...) hiếm khi
    lặp lại đúng một chỗ, nên bị loại.
    """
    o = H / 100
    dem, cao = {}, {}
    for _, hop in mau_thu:
        da = set()
        for h in hop:
            if not la_phu_de(h, W, H):
                continue
            k = int(((h[1] + h[3]) / 2) // o)
            if k in da:
                continue
            da.add(k)
            dem[k] = dem.get(k, 0) + 1
            cao.setdefault(k, []).append(h[3] - h[1])
    can = max(3, 0.05 * len(mau_thu))
    lan = []
    for k in sorted(dem, key=dem.get, reverse=True):
        so = dem[k] + dem.get(k - 1, 0) + dem.get(k + 1, 0)
        if so < can:
            break
        cac = cao[k] + cao.get(k - 1, []) + cao.get(k + 1, [])
        c_k = float(np.median(cac))
        if any(abs((k + 0.5) * o - y) < 0.8 * max(c, c_k) for y, c in lan):
            continue       # trùng làn đã có
        lan.append(((k + 0.5) * o, c_k))
    if lan:
        # làn chữ nhỏ hơn hẳn làn chính (vd chữ in trên xe) -> không phải phụ đề
        chinh = lan[0][1]
        # làn chữ to hơn hẳn làn chính (vd tên sản phẩm in to) -> cũng không phải phụ đề
        lan = [(y, c) for y, c in lan if 0.75 * chinh <= c <= 1.3 * chinh]
    return lan


def trong_lan(h, lan):
    tam_y, cao = (h[1] + h[3]) / 2, h[3] - h[1]
    return any(abs(tam_y - y) < 0.7 * c and 0.6 * c < cao < 1.7 * c for y, c in lan)


def gop_nhieu_dong(hop, W):
    """Gộp các dòng chữ sát nhau theo chiều dọc (phụ đề 2 dòng) thành 1 khối."""
    hop = sorted(hop, key=lambda h: h[1])
    khoi = []
    for h in hop:
        if khoi:
            k = khoi[-1]
            cao = min(h[3] - h[1], k[3] - k[1])
            cung_cot = min(h[2], k[2]) - max(h[0], k[0]) > -0.05 * W
            if h[1] - k[3] < 0.6 * cao and cung_cot:
                khoi[-1] = [min(k[0], h[0]), k[1], max(k[2], h[2]), max(k[3], h[3]), k[4] + h[4],
                            min(k[5], h[3] - h[1])]
                continue
        khoi.append(list(h) + [h[3] - h[1]])     # phần tử cuối: chiều cao 1 dòng
    return khoi


def theo_doi(mau_thu, W, H, buoc, tong):
    """Nối các khối chữ giống nhau ở các khung liên tiếp thành 'dòng chữ gốc'."""
    dong = []      # mỗi dòng: dict(bat_dau, ket_thuc (frame), hop=[x1,y1,x2,y2], chu, cao_dong)
    dang_mo = []
    lan = tim_lan(mau_thu, W, H)
    for i, hop in mau_thu:
        pd = [h for h in hop if la_phu_de(h, W, H)]
        chinh = [h for h in pd if trong_lan(h, lan)]
        # dòng thứ 2 của phụ đề 2 dòng: căn giữa, cùng cỡ, sát ngay trên/dưới dòng trong làn
        phu = [h for h in pd if h not in chinh and any(
            abs(h[3] - h[1] - (c[3] - c[1])) < 0.35 * (c[3] - c[1]) and
            min(abs(h[1] - c[3]), abs(c[1] - h[3])) < 0.6 * (c[3] - c[1]) for c in chinh)]
        khoi = gop_nhieu_dong(chinh + phu, W)
        con_mo = []
        da_dung = set()
        for d in dang_mo:
            tot, chon = 0, None
            for n, k in enumerate(khoi):
                if n in da_dung:
                    continue
                chong_y = min(k[3], d["hop"][3]) - max(k[1], d["hop"][1])
                if chong_y <= 0.5 * min(k[3] - k[1], d["hop"][3] - d["hop"][1]):
                    continue
                giong = difflib.SequenceMatcher(None, k[4], d["chu"]).ratio()
                if giong > 0.6 and giong > tot:
                    tot, chon = giong, n
            if chon is not None:
                k = khoi[chon]
                da_dung.add(chon)
                # chữ bị trôi (chạy theo camera) -> không phải phụ đề
                if abs((k[0] + k[2]) / 2 - (d["hop"][0] + d["hop"][2]) / 2) > 0.8 * d["cao_dong"]:
                    d["troi"] = True
                d["ket_thuc"] = i
                d["hop"] = [min(d["hop"][0], k[0]), min(d["hop"][1], k[1]),
                            max(d["hop"][2], k[2]), max(d["hop"][3], k[3])]
                con_mo.append(d)
            else:
                dong.append(d)
        for n, k in enumerate(khoi):
            if n not in da_dung:
                con_mo.append({"bat_dau": i, "ket_thuc": i, "hop": k[:4], "chu": k[4], "cao_dong": k[5]})
        dang_mo = con_mo
    dong.extend(dang_mo)
    # bỏ chữ đứng yên gần cả video (logo, tiêu đề cố định)
    return [d for d in dong if not d.get("troi") and
            ((d["ket_thuc"] - d["bat_dau"]) < 0.6 * tong or tong < 10 * buoc)]


# ---------- 3. Tìm chính xác lúc chữ hiện / tắt ----------
def tinh_chinh(video, dong, buoc, tong):
    """So điểm ảnh vùng chữ giữa khung có chữ và khung không chữ để tìm đúng khung chuyển."""
    cap = cv2.VideoCapture(video)

    def cat(f, hop):
        x1, y1, x2, y2 = [int(v) for v in hop]
        return cv2.cvtColor(f[max(0, y1):y2, max(0, x1):x2], cv2.COLOR_BGR2GRAY).astype(np.float32)

    def tim(co_chu, khong_chu, hop):
        """Đi từ khung không chữ về phía khung có chữ, trả về khung đầu tiên đã có chữ."""
        dau, cuoi = min(co_chu, khong_chu), max(co_chu, khong_chu)
        cap.set(cv2.CAP_PROP_POS_FRAMES, dau)
        khung = {}
        for k in range(dau, cuoi + 1):
            ok, f = cap.read()
            if not ok:
                break
            khung[k] = cat(f, hop)
        if co_chu not in khung or khong_chu not in khung:
            return None
        mau_co, mau_khong = khung[co_chu], khung[khong_chu]
        nguong = np.abs(mau_co - mau_khong).mean() / 2
        if nguong < 3:
            return None
        huong = 1 if co_chu > khong_chu else -1
        for k in range(khong_chu, co_chu + huong, huong):
            if np.abs(khung[k] - mau_co).mean() < nguong:
                return k
        return None

    for d in dong:
        if d["bat_dau"] - buoc >= 0:
            k = tim(d["bat_dau"], d["bat_dau"] - buoc, d["hop"])
            d["bd_chinh"] = k if k is not None else d["bat_dau"] - buoc + 1
        else:
            d["bd_chinh"] = 0
        if d["ket_thuc"] + buoc < tong:
            k = tim(d["ket_thuc"], d["ket_thuc"] + buoc, d["hop"])
            d["kt_chinh"] = k if k is not None else d["ket_thuc"] + buoc - 1
        else:
            d["kt_chinh"] = tong
    cap.release()


# ---------- 4-5. Che chữ + đặt phụ đề Việt ----------
def doc_srt(srt: Path):
    def giay(s):
        h, m, r = s.strip().split(":")
        sec, ms = r.split(",")
        return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000
    cau = []
    for k in re.split(r"\n\s*\n", srt.read_text(encoding="utf-8-sig").strip()):
        ls = k.strip().splitlines()
        i = next((n for n, l in enumerate(ls) if "-->" in l), None)
        if i is None:
            continue
        a, b = ls[i].split("-->")
        chu = "\\N".join(l.strip() for l in ls[i + 1:] if l.strip())
        if chu:
            cau.append((giay(a), giay(b), chu))
    return cau


def tg_ass(s):
    cs = int(round(s * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def vi_tri(W, H, dong, cau):
    """Chọn chỗ đặt từng câu Việt + danh sách dòng chữ gốc cần che."""
    vi_tri_chung = None
    if dong:
        tong_tg = {}
        for d in dong:
            k = round(((d["hop"][1] + d["hop"][3]) / 2) / (H / 40))
            tong_tg[k] = tong_tg.get(k, 0) + d["t1"] - d["t0"]
        k = max(tong_tg, key=tong_tg.get)
        mau = [d for d in dong if round(((d["hop"][1] + d["hop"][3]) / 2) / (H / 40)) == k]
        vi_tri_chung = (W / 2, float(np.median([(d["hop"][1] + d["hop"][3]) / 2 for d in mau])),
                        float(np.median([d["cao_dong"] for d in mau])))
    su_kien = []
    for a, b, chu in cau:
        trung = [(min(b, d["t1"]) - max(a, d["t0"]), n) for n, d in enumerate(dong)]
        trung = [x for x in trung if x[0] > 0.05]
        if trung:
            n = max(trung)[1]
        else:
            gan = [(min(abs(a - d["t1"]), abs(d["t0"] - b)), n) for n, d in enumerate(dong)]
            gan = [x for x in gan if x[0] < 2.0]
            n = min(gan)[1] if gan else None
        if n is not None:
            d = dong[n]
            d.setdefault("cau", []).append((a, b, chu))
            x, y, cao = (d["hop"][0] + d["hop"][2]) / 2, (d["hop"][1] + d["hop"][3]) / 2, d["cao_dong"]
            rong = d["hop"][2] - d["hop"][0]
            hop = d
        elif vi_tri_chung:
            x, y, cao = vi_tri_chung
            rong, hop = 0, None
        else:
            x, y, cao = W / 2, H * 0.82, H * 0.03
            rong, hop = 0, None
        su_kien.append((a, b, chu, x, y, cao, rong, hop))
    # chỉ che dòng chữ gốc hiện cùng lúc có lời nói (tránh khung đen trống)
    che = [d for d in dong if any(min(b, d["t1"]) - max(a, d["t0"]) > 0.05 for a, b, _ in cau)]

    # Lấp chỗ trống: chữ gốc còn hiện mà không có câu Việt nào -> giữ câu Việt tương ứng hiện tiếp
    for d in che:
        x, y = (d["hop"][0] + d["hop"][2]) / 2, (d["hop"][1] + d["hop"][3]) / 2
        cua_no = sorted(d.get("cau") or [])
        if not cua_no:   # câu trùng thời gian nhiều nhất với dòng này
            tot = max(cau, key=lambda c: min(c[1], d["t1"]) - max(c[0], d["t0"]))
            cua_no = [tot]
        dang_hien = sorted((a, b) for a, b, *_ in su_kien if b > d["t0"] and a < d["t1"])
        t = d["t0"]
        trong = []
        for a, b in dang_hien + [(d["t1"], d["t1"])]:
            if a - t > 0.03:
                trong.append((t, min(a, d["t1"])))
            t = max(t, b)
        for a, b in trong:
            # câu Việt gần nhất về thời gian trong số câu gắn với dòng này
            chu = min(cua_no, key=lambda c: min(abs(c[0] - b), abs(c[1] - a)))[2]
            su_kien.append((a, b, chu, x, y, d["cao_dong"], d["hop"][2] - d["hop"][0], d))
    return su_kien, che, vi_tri_chung


def lam(video: str, srt: str, ra: str, kieu: str = None, hieu_ung: str = None):
    print("  Đang tìm vị trí chữ gốc trên video...", flush=True)
    W, H, fps, buoc, tong, mau_thu = doc_chu(video)
    dong = theo_doi(mau_thu, W, H, buoc, tong)
    tinh_chinh(video, dong, buoc, tong)
    for d in dong:
        d["t0"], d["t1"] = d["bd_chinh"] / fps, (d["kt_chinh"] + 1) / fps
    cau = doc_srt(Path(srt))
    su_kien, che, vi_tri_chung = vi_tri(W, H, dong, cau)
    kc = kieu or KIEU_CHE
    if kc == "ai":
        sys.path.insert(0, str(Path(__file__).resolve().parent))   # chạy với -I vẫn tìm thấy module
        import xoa_chu_ai
        if not xoa_chu_ai.san_sang():
            print("  (Chưa có mô hình AI xoá chữ -> dùng khung đen)", flush=True)
            kc = "den"
    print(f"  Thấy {len(dong)} dòng chữ gốc, che {len(che)} dòng.", flush=True)

    def vung_goc(d):
        """Vùng chữ gốc nới rộng: thêm ~1 ký tự 2 bên để che luôn icon/emoji cạnh chữ (vd ✅)."""
        x1, y1, x2, y2 = d["hop"]
        dem, ngang = 0.25 * d["cao_dong"], 1.1 * d["cao_dong"]
        return max(0, int(x1 - ngang)), max(0, int(y1 - dem)), min(W, int(x2 + ngang)), min(H, int(y2 + dem))

    loc = []
    for d in che:
        x1, y1, x2, y2 = vung_goc(d)
        bat = f":enable='between(t,{d['t0']:.3f},{d['t1']:.3f})'"
        if kc == "xoa":
            # delogo lấy màu nền xung quanh lấp vào chỗ chữ (vùng phải cách mép ảnh >= 1px)
            x1, y1 = max(1, x1), max(1, y1)
            x2, y2 = min(W - 2, x2), min(H - 2, y2)
            loc.append(f"delogo=x={x1}:y={y1}:w={x2 - x1}:h={y2 - y1}{bat}")
        # Kiểu "den": KHÔNG che riêng chữ gốc. Chỉ khi câu Việt hiện mới có khung đen + chữ Việt,
        # khung đủ lớn để phủ dòng chữ chính bên dưới (vẽ ở phần phụ đề bên dưới).

    with tempfile.TemporaryDirectory() as tmp:
        rong_toi_da = W * 0.88

        def co_chu(cao, rong=0, chu=""):
            """Cỡ chữ Việt để phủ kín vùng chữ gốc.

            - Nét chữ Việt cao bằng chữ gốc (câu ngắn nhìn to tương đương chữ gốc).
            - 1 dòng mà hẹp hơn chữ gốc -> phóng to thêm (tối đa 1.3 lần).
            - Câu dài: tối đa 3 dòng, cỡ lớn nhất có thể nhưng không nhỏ hơn 4.5% bề ngang.
            """
            n = len(chu.replace("\\N", " ")) or 10
            fs = min(max(cao / CAO_NET, W * CO_CHU), W * 0.12)
            so_dong = RONG_KT * fs * n / rong_toi_da
            if so_dong <= 1 and rong and RONG_KT * fs * n < rong:
                fs = min(rong / (RONG_KT * n), fs * 1.3)
            elif so_dong > 2:
                fs = min(fs, 3 * rong_toi_da / (RONG_KT * n))
            return int(max(fs, W * 0.045))
        co_md = co_chu(vi_tri_chung[2] if vi_tri_chung else H * 0.03)
        if kc in ("xoa", "ai"):   # chữ trắng đậm, viền đen dày, bóng nhẹ (kiểu phụ đề Douyin)
            kieu = f"{MAU_CHU},{MAU_CHU},{MAU_VIEN},&H64000000,{IN_DAM},0,0,0,100,100,0,0,1,{max(2, co_md // 8)},{max(1, co_md // 20)}"
        else:                   # chữ trắng trên khung đen (khung vẽ riêng bằng drawbox)
            kieu = f"{MAU_CHU},{MAU_CHU},&H00000000,&H00000000,{IN_DAM},0,0,0,100,100,0,0,1,0,0"
        dau = (
            "[Script Info]\nScriptType: v4.00+\n"
            f"PlayResX: {W}\nPlayResY: {H}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Default,{FONT},{co_md},{kieu},5,{int(W * 0.06)},{int(W * 0.06)},0,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )
        dong_ass = []
        khung_viet = []
        for a, b, chu, x, y, cao, rong, d in su_kien:
            co = co_chu(cao, rong, chu)
            x = min(max(x, W * 0.3), W * 0.7)   # giữ chữ trong khung hình
            vien = max(2, co // 8) if kc in ("xoa", "ai") else 0
            if kc == "den":
                # 1 khung đen duy nhất = vùng chữ Việt (ước lượng) gộp với vùng chữ gốc
                n = len(chu.replace("\\N", " ")) or 1
                dai = RONG_KT * co * n * 1.06
                so = max(1, int(np.ceil(dai / rong_toi_da)))
                rk = dai if so == 1 else min(dai / so * 1.1, rong_toi_da)
                ck = so * co * 1.2
                kx1, ky1 = x - rk / 2 - 0.45 * co, y - ck / 2 - 0.25 * co
                kx2, ky2 = x + rk / 2 + 0.45 * co, y + ck / 2 + 0.25 * co
                if d is not None:
                    gx1, gy1, gx2, gy2 = vung_goc(d)
                    kx1, ky1, kx2, ky2 = min(kx1, gx1), min(ky1, gy1), max(kx2, gx2), max(ky2, gy2)
                kx1, ky1 = max(0, int(kx1)), max(0, int(ky1))
                kx2, ky2 = min(W, int(kx2)), min(H, int(ky2))
                khung_viet.append(f"drawbox=x={kx1}:y={ky1}:w={kx2 - kx1}:h={ky2 - ky1}:color={MAU_KHUNG}@1:t=fill"
                                  f":enable='between(t,{a:.3f},{b:.3f})'")
            dong_ass.append(f"Dialogue: 0,{tg_ass(a)},{tg_ass(b)},Default,,0,0,0,,"
                            f"{{\\an5\\pos({int(x)},{int(y)})\\fs{co}\\bord{vien}}}{chu}")
        (Path(tmp) / "sub.ass").write_text(dau + "\n".join(dong_ass) + "\n", encoding="utf-8")
        loc.extend(khung_viet)
        if WIN:
            # ffmpeg trên Windows tìm font kém -> chép font Arial vào thư mục tạm cho chắc đủ dấu tiếng Việt
            (Path(tmp) / "fonts").mkdir()
            for ten in ("arial.ttf", "arialbd.ttf"):
                f = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / ten
                if f.exists():
                    (Path(tmp) / "fonts" / ten).write_bytes(f.read_bytes())
            loc.append("subtitles=sub.ass:fontsdir=fonts")
        else:
            loc.append("subtitles=sub.ass")
        f_loc = Path(tmp) / "loc.txt"
        f_loc.write_text(",".join(loc), encoding="utf-8")  # nhiều dòng che -> ghi bộ lọc ra file
        # Ưu tiên CHẤT LƯỢNG: libx264 CRF thấp = gần như không mất chất lượng so với bản gốc
        # (file nặng hơn). Giữ nguyên độ phân giải, số khung hình/giây, tiếng gốc.
        ma_hoa = ["-c:v", "libx264", "-crf", str(CRF), "-preset", "slow", "-profile:v", "high",
                  "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", os.path.abspath(ra)]
        if kc == "ai":
            xoa_ai(video, dong, W, H, tmp, f_loc, ma_hoa, hieu_ung)
        else:
            lenh = [FFMPEG, "-v", "error", "-y", "-i", os.path.abspath(video), "-/filter:v", str(f_loc)] + ma_hoa
            r = subprocess.run(lenh, cwd=tmp, capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(r.stderr[-1500:])
    print("  Đã che chữ gốc và gắn phụ đề tiếng Việt.", flush=True)


def xoa_ai(video, dong, W, H, tmp, f_loc, ma_hoa, hieu_ung=None):
    """Đọc từng khung hình, AI xoá chữ gốc ở khung có chữ, (nếu có) zoom ở điểm nhấn, rồi đẩy thẳng
    sang ffmpeg để gắn chữ Việt và mã hoá 1 lần (không nén 2 lần). Chữ Việt gắn sau nên không bị zoom."""
    import xoa_chu_ai
    ai = xoa_chu_ai.XoaChu()
    diem = []
    if hieu_ung:
        import hieu_ung as hu
        diem = hu.doc(hieu_ung, video)
        print(f"  Thêm {len(diem.get('doan', []))} đoạn zoom chậm vào chỗ đẹp (có chống rung).", flush=True)
    fps = cv2.VideoCapture(video).get(cv2.CAP_PROP_FPS) or 30
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=r_frame_rate", "-of", "csv=p=0", os.path.abspath(video)],
                       capture_output=True, text=True)
    nhip = r.stdout.strip().split("\n")[0] or "30"
    # khung có chữ: nới 1 khung mỗi đầu cho chắc khi chữ hiện/tắt dần
    cac = [(d["bd_chinh"] - 1, d["kt_chinh"] + 1, (*d["hop"], d["cao_dong"])) for d in dong]
    lenh = [FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
            "-framerate", nhip, "-i", "-", "-i", os.path.abspath(video),
            "-map", "0:v", "-map", "1:a?", "-/filter:v", str(f_loc)] + ma_hoa
    p = subprocess.Popen(lenh, cwd=tmp, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    cap = cv2.VideoCapture(video)
    tong = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    k, da_xoa = 0, 0
    try:
        while True:
            ok, f = cap.read()
            if not ok:
                break
            hop = [h for a, b, h in cac if a <= k <= b]
            if hop:
                f = ai.xoa(f, hop)
                da_xoa += 1
            if diem:
                f = hu.ap_dung(f, diem, k / fps)
            p.stdin.write(np.ascontiguousarray(f).tobytes())
            k += 1
            if k % 15 == 0:
                bao_tien_do("Xoá chữ", k, tong)
            if k % 150 == 0:
                print(f"  AI xoá chữ: {k} khung...", flush=True)
    finally:
        cap.release()
        p.stdin.close()
    loi = p.stderr.read().decode(errors="ignore")
    if p.wait() != 0:
        raise RuntimeError(loi[-1500:])
    print(f"  AI đã xoá chữ ở {da_xoa}/{k} khung hình.", flush=True)


if __name__ == "__main__":
    lam(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None,
        sys.argv[5] if len(sys.argv) > 5 else None)
