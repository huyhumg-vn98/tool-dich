"""Video 2 người nói: mỗi người 1 giọng lồng tiếng.

1. Bước nghe bật "tách người nói" của pyVideoTrans -> mỗi câu có nhãn nhóm (spk0, spk1...).
   Mô hình hay chia 1 người thành nhiều nhóm, nên KHÔNG tin thẳng nhãn nhóm.
2. Đo độ trầm/cao (tần số giọng) của từng nhóm từ âm thanh video.
3. Chỉ đổi giọng khi 2 nhóm khác hẳn nhau: một bên giọng nam (< NGUONG_NAM_NU Hz), một bên giọng nữ,
   chênh nhau >= CHENH_TOI_THIEU. Video 1 người nói -> luôn giữ 1 giọng.
4. Gán giọng: người giọng trầm -> giọng nam bạn chọn, giọng cao -> giọng nữ (nếu 2 giọng chọn khác giới).
   2 giọng cùng giới -> người nói nhiều hơn dùng giọng chính, người còn lại dùng giọng thứ 2.
Chạy trong môi trường của pyVideoTrans (có librosa).
"""
import json
import subprocess
from pathlib import Path

import numpy as np

# ===== Cài đặt (sửa ở đây) =====
NGUONG_NAM_NU = 165.0      # Hz: dưới là giọng nam, trên là giọng nữ
CHENH_TOI_THIEU = 1.3      # 2 nhóm phải chênh nhau ít nhất 30% mới coi là 2 người khác nhau
# =================================


def gioi_tinh(*ten) -> str:
    """'female'/'Nữ' -> 'nu', 'male'/'Nam' -> 'nam', không rõ -> ''."""
    s = " ".join(t or "" for t in ten).lower()
    if "female" in s or "nữ" in s or "nu " in s:
        return "nu"
    if "male" in s or "nam" in s.replace("nam định", ""):
        return "nam"
    return ""


def _am_thanh(video, ffmpeg):
    raw = subprocess.run([ffmpeg, "-v", "error", "-i", str(video), "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.float32)


def do_cao_cau(video, moc, ffmpeg) -> list:
    """Mỗi câu: (tần số từng khung Hz, độ chắc chắn là tiếng nói của từng khung)."""
    import librosa
    y = _am_thanh(video, ffmpeg)
    ds = []
    for a, b in moc:
        seg = y[int(a * 16000):int(b * 16000)]
        if len(seg) < 1600:
            ds.append((np.array([]), np.array([])))
            continue
        f, _, p = librosa.pyin(seg, fmin=75, fmax=400, sr=16000, frame_length=1024)
        ds.append((f, p))
    return ds


def _khung(fp, nguong):
    f, p = fp
    return f[(~np.isnan(f)) & (p > nguong)].tolist() if len(f) else []


def do_cao_nhom(video, moc, nguoi, ffmpeg, cau=None) -> dict:
    """{nhóm: (tần số trung vị Hz, số khung có tiếng)} - gộp mọi khung có tiếng nói của cả nhóm."""
    cau = cau if cau is not None else do_cao_cau(video, moc, ffmpeg)
    gop = {}
    for fp, sp in zip(cau, nguoi):
        gop.setdefault(sp, []).extend(_khung(fp, 0.5))
    return {k: (float(np.median(v)), len(v)) for k, v in gop.items() if len(v) >= 10}


# Dự phòng khi bước tách người nói gộp cả video vào 1 nhóm: xét cao độ TỪNG CÂU
CAU_NAM_TOI_DA = 150.0     # câu có giọng trung vị dưới mức này -> chắc là giọng nam
CAU_NU_TOI_THIEU = 210.0   # trên mức này -> chắc là giọng nữ (ở giữa: không chắc, theo câu bên cạnh)
                           # (nam nói lên giọng có câu tới ~195 Hz -> không đặt thấp hơn)
CHENH_THEO_CAU = 1.6       # 2 nhóm câu phải chênh nhau ít nhất 60%
IT_NHAT_CAU = 2            # mỗi người phải nói ít nhất 2 câu chắc chắn


def chia_theo_cau(cau) -> list:
    """Trả về nhãn 'nam'/'nu' cho từng câu nếu thấy rõ 2 người khác giới, không thì None."""
    # câu ngắn + nhạc nền -> ít khung "rất chắc"; dùng ngưỡng thấp hơn để câu nào cũng đo được
    ds = [_khung(fp, 0.1) for fp in cau]
    hz = [float(np.median(f)) if len(f) >= 8 else None for f in ds]
    nhan = ["nam" if h is not None and h < CAU_NAM_TOI_DA else
            "nu" if h is not None and h > CAU_NU_TOI_THIEU else None for h in hz]
    nam = [h for h, n in zip(hz, nhan) if n == "nam"]
    nu = [h for h, n in zip(hz, nhan) if n == "nu"]
    chac = len(nam) + len(nu)
    can = max(IT_NHAT_CAU, int(0.15 * chac))
    if len(nam) < can or len(nu) < can or np.median(nu) / np.median(nam) < CHENH_THEO_CAU:
        return None
    # câu không chắc chắn: theo câu chắc chắn gần nhất phía trước (đầu video: phía sau)
    for i in range(len(nhan)):
        if nhan[i] is None:
            truoc = next((nhan[j] for j in range(i - 1, -1, -1) if nhan[j]), None)
            nhan[i] = truoc or next(n for n in nhan[i + 1:] if n)
    return nhan


def gan_giong(video, moc, nguoi, giong1, giong2, ffmpeg, ten1="", ten2="") -> dict:
    """Trả về {"vai": [giọng cho từng câu], "ghi_chu": "..."}.

    moc: [(bắt đầu, kết thúc)] mỗi câu; nguoi: nhãn nhóm mỗi câu; giong1 = giọng chính, giong2 = giọng thứ 2."""
    vai = [giong1] * len(nguoi)
    try:
        cau = do_cao_cau(video, moc, ffmpeg)
        cao = do_cao_nhom(video, moc, nguoi, ffmpeg, cau)
    except Exception as e:
        return {"vai": vai, "ghi_chu": f"không đo được giọng ({e})"}
    if not cao:
        return {"vai": vai, "ghi_chu": "không đo được giọng"}
    nguoi = list(nguoi)
    chinh = max(cao, key=lambda k: cao[k][1])            # nhóm nói nhiều nhất
    g1, g2 = gioi_tinh(ten1, giong1), gioi_tinh(ten2, giong2)
    khac_gioi = g1 and g2 and g1 != g2

    def la_nam(hz):
        return hz < NGUONG_NAM_NU

    def giong_cho(hz):
        if khac_gioi:
            muon = "nam" if la_nam(hz) else "nu"
            return giong1 if g1 == muon else giong2
        return giong1

    hz0 = cao[chinh][0]

    def khac_nguoi(hz):
        """Nhóm này chắc chắn là người khác với người nói chính?"""
        ty_le = max(hz, hz0) / min(hz, hz0)
        if khac_gioi:
            return ty_le >= CHENH_TOI_THIEU and la_nam(hz) != la_nam(hz0)
        return ty_le >= 1.5          # 2 giọng cùng giới: chỉ tách khi chênh rất rõ

    khac = {k for k, (hz, _) in cao.items() if k != chinh and khac_nguoi(hz)}
    if not khac and khac_gioi:
        # bước tách người nói không phân biệt được -> xét cao độ từng câu
        nhan = chia_theo_cau(cau)
        if nhan:
            vai = [giong1 if n == g1 else giong2 for n in nhan]
            so_nu = nhan.count("nu")
            return {"vai": vai, "ghi_chu": f"2 người nói (xét từng câu: {so_nu} câu giọng nữ, "
                                          f"{len(nhan) - so_nu} câu giọng nam)"}
    if not khac:
        # chỉ 1 người nói -> giữ đúng giọng chính bạn chọn
        vai = [giong1] * len(nguoi)
    else:
        # 2 người: giọng theo nam/nữ (nếu 2 giọng chọn khác giới), không thì người nói chính dùng giọng chính
        giong_chinh = giong_cho(hz0)
        giong_phu = giong2 if giong_chinh == giong1 else giong1
        vai = [giong_phu if sp in khac else giong_chinh for sp in nguoi]
    giong_chinh = giong1 if not khac else giong_chinh
    so2 = sum(1 for v in vai if v != giong_chinh)
    tom = ", ".join(f"{k}≈{int(h)}Hz" for k, (h, _) in sorted(cao.items()))
    ghi = (f"2 người nói ({so2}/{len(vai)} câu giọng thứ 2; {tom})" if so2 else f"1 người nói ({tom})")
    return {"vai": vai, "ghi_chu": ghi}
