"""Làm nét video bằng AI (Real-ESRGAN, mô hình realesr-general-x4v3 - giấy phép BSD-3).

    python lam_net.py <video_vào> <video_ra>

- Video độ phân giải thấp (vd 576x1024): AI phóng to + làm nét lên chiều ngang DICH_NGANG (1080).
- Video đã đủ nét (>= DICH_NGANG): giữ nguyên, không làm gì (chép thẳng) - tránh tốn thời gian vô ích.
Tiếng giữ nguyên. Chạy trên GPU Mac (M1-M4) / NVIDIA nếu có.
"""
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

GOC = Path(__file__).resolve().parent
MO_HINH = GOC / "mo_hinh" / "realesr-general-x4v3.pth"
URL_MO_HINH = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth"

# ===== Cài đặt (sửa ở đây) =====
DICH_NGANG = 1080      # chiều ngang mục tiêu; video nhỏ hơn mới làm nét
CRF = 16               # chất lượng mã hoá (16 = rất nét)
MUC_NET = 0.85         # 1.0 = toàn bộ ảnh AI; thấp hơn = trộn với ảnh gốc cho tự nhiên (chữ nhỏ đỡ "vẽ lại")
# =================================


def san_sang():
    if not MO_HINH.exists():
        return False
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def can_lam(video) -> bool:
    cap = cv2.VideoCapture(str(video))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return 0 < min(w, h) < DICH_NGANG * 0.95


class LamNet:
    def __init__(self):
        import torch
        from torch import nn
        self.torch = torch

        class SRVGGNetCompact(nn.Module):
            def __init__(self, n_feat=64, n_conv=32, up=4):
                super().__init__()
                self.up = up
                body = [nn.Conv2d(3, n_feat, 3, 1, 1), nn.PReLU(num_parameters=n_feat)]
                for _ in range(n_conv):
                    body += [nn.Conv2d(n_feat, n_feat, 3, 1, 1), nn.PReLU(num_parameters=n_feat)]
                body.append(nn.Conv2d(n_feat, 3 * up * up, 3, 1, 1))
                self.body = nn.ModuleList(body)
                self.ps = nn.PixelShuffle(up)

            def forward(self, x):
                y = x
                for m in self.body:
                    y = m(y)
                return self.ps(y) + nn.functional.interpolate(x, scale_factor=self.up, mode="nearest")

        if torch.backends.mps.is_available():
            self.tb = torch.device("mps")
        elif torch.cuda.is_available():
            self.tb = torch.device("cuda")
        else:
            self.tb = torch.device("cpu")
        m = SRVGGNetCompact()
        sd = torch.load(str(MO_HINH), map_location="cpu")
        m.load_state_dict(sd.get("params", sd))
        self.nua = self.tb.type in ("mps", "cuda")
        self.m = (m.half() if self.nua else m).to(self.tb).eval()

    def lam(self, khung_bgr, ra_wh):
        """1 khung BGR -> khung đã làm nét, kích thước ra_wh (rộng, cao)."""
        torch = self.torch
        x = torch.from_numpy(cv2.cvtColor(khung_bgr, cv2.COLOR_BGR2RGB)).permute(2, 0, 1)[None]
        x = x.to(self.tb).half() if self.nua else x.to(self.tb).float()
        with torch.inference_mode():
            y = self.m(x / 255.0)
            y = (y.float().clamp(0, 1) * 255).round().byte()[0].permute(1, 2, 0).cpu().numpy()
        y = cv2.cvtColor(cv2.resize(y, ra_wh, interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2BGR)
        if MUC_NET < 1:
            thuong = cv2.resize(khung_bgr, ra_wh, interpolation=cv2.INTER_CUBIC)
            y = cv2.addWeighted(y, MUC_NET, thuong, 1 - MUC_NET, 0)
        return y


def lam(video, ra, bao=None):
    """Làm nét cả video. Trả về True nếu đã làm nét, False nếu không cần (video đã đủ nét)."""
    sys.path.insert(0, str(GOC))
    from che_chu import FFMPEG, FFPROBE, bao_tien_do
    if not can_lam(video) or not san_sang():
        return False
    cap = cv2.VideoCapture(str(video))
    W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    tong = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    tl = DICH_NGANG / min(W, H)
    rw, rh = int(round(W * tl / 2)) * 2, int(round(H * tl / 2)) * 2
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                        "-of", "csv=p=0", os.path.abspath(video)], capture_output=True, text=True)
    nhip = r.stdout.strip().split("\n")[0] or "30"
    ai = LamNet()
    p = subprocess.Popen([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{rw}x{rh}",
                          "-framerate", nhip, "-i", "-", "-i", os.path.abspath(video), "-map", "0:v", "-map", "1:a?",
                          "-c:v", "libx264", "-crf", str(CRF), "-preset", "slow", "-pix_fmt", "yuv420p",
                          "-c:a", "copy", "-movflags", "+faststart", os.path.abspath(ra)],
                         stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    k = 0
    try:
        while True:
            ok, f = cap.read()
            if not ok:
                break
            p.stdin.write(np.ascontiguousarray(ai.lam(f, (rw, rh))).tobytes())
            k += 1
            if k % 15 == 0:
                bao_tien_do("Làm nét", k, tong)
            if bao and k % 30 == 0:
                bao(k, tong)
    finally:
        cap.release()
        p.stdin.close()
    loi = p.stderr.read().decode(errors="ignore")
    if p.wait() != 0:
        raise RuntimeError(loi[-1500:])
    return True


if __name__ == "__main__":
    import time
    t = time.time()
    da = lam(sys.argv[1], sys.argv[2], bao=lambda k, n: print(f"  {k}/{n} khung", flush=True))
    print(f"Đã làm nét ({time.time() - t:.0f} giây)." if da else "Video đã đủ nét, không cần làm.")
