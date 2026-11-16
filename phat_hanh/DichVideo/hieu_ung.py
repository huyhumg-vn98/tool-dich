"""Hiệu ứng zoom chậm (kiểu Ken Burns) vào chỗ đẹp / ngon nhất - cho video không lời có thuyết minh AI.

Điểm nhấn do AI chọn khi viết lời (thuyet_minh.py ghi ra hieu_ung.json):
    [{"t": 2.5, "x": 0.5, "y": 0.6}, ...]   t = giây bắt đầu, (x, y) = chỗ đẹp nhất (tỉ lệ 0-1)

Ở mỗi điểm: khung hình từ từ đẩy cận vào (x, y) trong vài giây, chuyển động mềm.
- Gặp chỗ chuyển cảnh -> trả về bình thường đúng lúc chuyển cảnh (mắt không thấy).
- Cảnh còn dài -> giữ một chút rồi lùi ra thật chậm. Không bao giờ giật.

Chạy riêng (cho video không gắn phụ đề):  python hieu_ung.py <video_vào> <hieu_ung.json> <video_ra>
"""
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

# ===== Cài đặt (sửa ở đây) =====
MUC_ZOOM = 1.18       # phóng to tối đa 18% (1.12 = rất nhẹ, 1.25 = rõ hơn)
TG_ZOOM = 3.0         # thời gian từ từ đẩy cận (giây) - càng lớn càng chậm
TG_GIU = 1.5          # giữ ở mức cận (giây)
TG_LUI = 2.0          # thời gian từ từ lùi ra (giây)
CHONG_RUNG = 0        # chống rung tay khi zoom (số khung làm mượt, vd 12; 0 = tắt)
CACH_NHAU = 2.0       # 2 điểm nhấn cách nhau tối thiểu (giây)
# =================================


def phan_tich(video):
    """1 lượt đọc video: tìm chuyển cảnh + đo rung tay từng khung.

    Trả về (các mốc giây chuyển cảnh, độ bù chống rung từng khung [(dx, dy) theo điểm ảnh gốc], fps)."""
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1
    tl = 270 / W
    lech, dich, truoc, truoc_g = [], [(0.0, 0.0)], None, None
    while True:
        ok, f = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(cv2.resize(f, None, fx=tl, fy=tl, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        nho = cv2.resize(g, (64, 112)).astype(np.float32)
        if truoc is not None:
            lech.append(float(np.abs(nho - truoc).mean()))
            d = (0.0, 0.0)
            diem = cv2.goodFeaturesToTrack(truoc_g, 200, 0.01, 8)
            if diem is not None and len(diem) >= 8:
                moi, st, _ = cv2.calcOpticalFlowPyrLK(truoc_g, g, diem, None)
                ok_ = st.reshape(-1) == 1
                if ok_.sum() >= 8:
                    m, _ = cv2.estimateAffinePartial2D(diem[ok_], moi[ok_])
                    if m is not None:
                        d = (m[0, 2] / tl, m[1, 2] / tl)
            dich.append(d)
        truoc, truoc_g = nho, g
    cap.release()
    if not lech:
        return [], np.zeros((len(dich), 2)), fps
    nguong = max(25.0, 6 * float(np.median(lech)))
    cat_k = [k + 1 for k, a in enumerate(lech) if a > nguong]      # khung đầu tiên của cảnh mới
    dich = np.array(dich, dtype=np.float64)
    bu = np.zeros_like(dich)
    if CHONG_RUNG > 0:
        # theo từng cảnh: đường đi của máy quay -> làm mượt -> độ bù = đường mượt - đường thật
        moc = [0] + cat_k + [len(dich)]
        for a, b in zip(moc, moc[1:]):
            if b - a < 3:
                continue
            duong = np.cumsum(np.vstack([[0, 0], dich[a + 1:b]]), axis=0)
            r = int(3 * CHONG_RUNG)
            nhan = np.exp(-0.5 * (np.arange(-r, r + 1) / CHONG_RUNG) ** 2)
            nhan /= nhan.sum()
            muot = np.stack([np.convolve(np.pad(duong[:, i], r, mode="edge"), nhan, mode="valid")
                             for i in range(2)], axis=1)
            bu[a:b] = muot - duong
    return [k / fps for k in cat_k], bu, fps


def tim_chuyen_canh(video):
    return phan_tich(video)[0]


def doc(duong_dan, video=None):
    """Đọc điểm nhấn + tính sẵn kế hoạch zoom cho từng đoạn."""
    try:
        ds = json.loads(Path(duong_dan).read_text(encoding="utf-8"))
    except Exception:
        return []
    diem = []
    for d in ds if isinstance(ds, list) else []:
        try:
            t = float(d["t"])
            x = min(0.8, max(0.2, float(d.get("x", 0.5))))
            y = min(0.8, max(0.2, float(d.get("y", 0.5))))
        except (KeyError, TypeError, ValueError):
            continue
        if t >= 0:
            diem.append((t, x, y))
    diem.sort()
    loc = []
    for d in diem:
        if not loc or d[0] - loc[-1][0] >= CACH_NHAU:
            loc.append(d)
    cat, bu, fps = phan_tich(video) if video else ([], None, 30)
    dai_video = 1e9
    if video:
        cap = cv2.VideoCapture(video)
        dai_video = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 30)
        cap.release()

    ke_hoach = []
    for t, x, y in loc:
        # bắt đầu từ đầu cảnh chứa điểm nhấn (nếu cảnh vừa mới bắt đầu)
        truoc = [c for c in cat if t - 1.0 <= c <= t]
        if truoc:
            t = truoc[-1]
        if ke_hoach and t < ke_hoach[-1]["het"] + 0.3:
            continue            # đoạn trước chưa lùi ra xong -> bỏ điểm này, không zoom chồng
        if dai_video - t < 1.5:
            continue
        vao = min(TG_ZOOM, dai_video - t)
        het = t + vao + TG_GIU + TG_LUI
        lui = TG_LUI
        if het > dai_video:     # gần hết video: dừng ở cận cảnh, không cần lùi ra
            het, lui = dai_video + 1, 0.0
        ke_hoach.append({"t": t, "het": het, "vao": vao, "lui": lui, "x": x, "y": y, "muc": MUC_ZOOM})
    if not ke_hoach:
        return {}
    return {"doan": ke_hoach, "bu": bu, "fps": fps}


def _mem(u):
    """Chuyển động mềm: chậm - nhanh - chậm."""
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)




def muc_zoom(ke_hoach, t):
    """Mức zoom (>= 1) và tâm (x, y theo tỉ lệ) tại thời điểm t."""
    for d in ke_hoach.get("doan", []):
        if not (d["t"] <= t < d["het"]):
            continue
        u = t - d["t"]
        giu_den = d["het"] - d["lui"]
        if u < d["vao"]:
            m = _mem(u / d["vao"])
        elif t < giu_den or d["lui"] <= 0:
            m = 1.0
        else:
            m = 1.0 - _mem((t - giu_den) / d["lui"])
        s = 1 + (d["muc"] - 1) * m
        return s, d["x"], d["y"]      # tâm đứng yên ở chỗ đẹp nhất (không trôi -> không chòng chành)
    return 1.0, 0.5, 0.5


def ap_dung(khung, ke_hoach, t):
    """Zoom quanh tâm (x, y) + chống rung tay bằng phần hình dư ra khi zoom (không bao giờ lộ viền)."""
    s, x, y = muc_zoom(ke_hoach, t)
    if s <= 1.0005:
        return khung
    H, W = khung.shape[:2]
    cx, cy = x * W, y * H
    bx = by = 0.0
    bu = ke_hoach.get("bu")
    if bu is not None and len(bu):
        k = min(len(bu) - 1, max(0, int(round(t * ke_hoach["fps"]))))
        # độ bù bị giới hạn trong phần dư của khung zoom -> zoom càng sâu chống rung càng mạnh
        bx = float(np.clip(bu[k, 0], -(s - 1) * (W - cx) / s, (s - 1) * cx / s))
        by = float(np.clip(bu[k, 1], -(s - 1) * (H - cy) / s, (s - 1) * cy / s))
    M = np.float32([[s, 0, s * bx + (1 - s) * cx], [0, s, s * by + (1 - s) * cy]])
    return cv2.warpAffine(khung, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)


def lam(video, json_hu, ra, crf=16):
    """Áp hiệu ứng cho cả video (giữ nguyên tiếng, chất lượng cao)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from che_chu import FFMPEG, FFPROBE, bao_tien_do
    ke_hoach = doc(json_hu, video)
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=r_frame_rate", "-of", "csv=p=0", os.path.abspath(video)], capture_output=True, text=True)
    nhip = r.stdout.strip().split("\n")[0] or "30"
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    tong = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    p = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                          "-framerate", nhip, "-i", "-", "-i", os.path.abspath(video), "-map", "0:v", "-map", "1:a?",
                          "-c:v", "libx264", "-crf", str(crf), "-preset", "slow", "-profile:v", "high",
                          "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", os.path.abspath(ra)],
                         stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    k = 0
    try:
        while True:
            ok, f = cap.read()
            if not ok:
                break
            p.stdin.write(np.ascontiguousarray(ap_dung(f, ke_hoach, k / fps)).tobytes())
            k += 1
            if k % 15 == 0:
                bao_tien_do("Thêm zoom", k, tong)
    finally:
        cap.release()
        p.stdin.close()
    loi = p.stderr.read().decode(errors="ignore")
    if p.wait() != 0:
        raise RuntimeError(loi[-1500:])
    print(f"Đã thêm {len(ke_hoach.get('doan', []))} đoạn zoom chậm.")


if __name__ == "__main__":
    lam(sys.argv[1], sys.argv[2], sys.argv[3])
