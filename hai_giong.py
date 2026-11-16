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


def do_cao_nhom(video, moc, nguoi, ffmpeg) -> dict:
    """{nhóm: (tần số trung vị Hz, số khung có tiếng)} - gộp mọi khung có tiếng nói của cả nhóm."""
    import librosa
    y = _am_thanh(video, ffmpeg)
    gop = {}
    for (a, b), sp in zip(moc, nguoi):
        seg = y[int(a * 16000):int(b * 16000)]
        if len(seg) < 1600:
            continue
        f, _, p = librosa.pyin(seg, fmin=75, fmax=400, sr=16000, frame_length=1024)
        ok = (~np.isnan(f)) & (p > 0.5)
        gop.setdefault(sp, []).extend(f[ok].tolist())
    return {k: (float(np.median(v)), len(v)) for k, v in gop.items() if len(v) >= 10}


def gan_giong(video, moc, nguoi, giong1, giong2, ffmpeg, ten1="", ten2="") -> dict:
    """Trả về {"vai": [giọng cho từng câu], "ghi_chu": "..."}.

    moc: [(bắt đầu, kết thúc)] mỗi câu; nguoi: nhãn nhóm mỗi câu; giong1 = giọng chính, giong2 = giọng thứ 2."""
    vai = [giong1] * len(nguoi)
    try:
        cao = do_cao_nhom(video, moc, nguoi, ffmpeg)
    except Exception as e:
        return {"vai": vai, "ghi_chu": f"không đo được giọng ({e})"}
    if not cao:
        return {"vai": vai, "ghi_chu": "không đo được giọng"}
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
