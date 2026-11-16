"""Xoá sạch chữ gốc bằng AI (mô hình LaMa) - vẽ lại phần nền phía sau chữ.

Chỉ xử lý đúng vùng chữ chính mà che_chu.py đã dò được, chỉ ở các khung hình chữ đang hiện,
nên chữ trong cảnh (trên sản phẩm, biển hiệu...) và phần còn lại của video giữ nguyên.

Mô hình: big-lama.pt (LaMa, giấy phép Apache-2.0), đặt ở thư mục mo_hinh/.
"""
from pathlib import Path

import cv2
import numpy as np

GOC = Path(__file__).resolve().parent
MO_HINH = GOC / "mo_hinh" / "big-lama.pt"

# ===== Tăng tốc (sửa ở đây) =====
# Nền quanh chữ gần như không đổi so với lần AI vẽ gần nhất -> dùng lại phần đã vẽ (nhanh hơn nhiều,
# nền còn đứng yên hơn). Cứ tối đa DUNG_LAI_TOI_DA khung thì bắt buộc AI vẽ mới 1 lần.
NGUONG_GIONG = 1.5     # độ lệch điểm ảnh trung bình coi như "giống" (0 = tắt dùng lại)
DUNG_LAI_TOI_DA = 8
LE_NEN = 1.0           # vùng nền quanh chữ cho AI nhìn (tính theo chiều cao chữ)
# =================================
URL_MO_HINH = "https://github.com/Sanster/models/releases/download/add_big_lama/big-lama.pt"


def san_sang():
    """Có đủ thư viện + mô hình để xoá bằng AI không."""
    if not MO_HINH.exists():
        return False
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


class XoaChu:
    def __init__(self):
        import torch
        self.torch = torch
        if torch.backends.mps.is_available():
            self.thiet_bi = torch.device("mps")        # GPU Mac M1-M4
        elif torch.cuda.is_available():
            self.thiet_bi = torch.device("cuda")       # GPU NVIDIA (Windows)
        else:
            self.thiet_bi = torch.device("cpu")
        self.mo_hinh = torch.jit.load(str(MO_HINH), map_location=self.thiet_bi).eval()
        self.nho = {}           # hộp chữ -> (nền xung quanh lúc vẽ, ảnh đã vẽ, số khung đã dùng lại)
        self.so_ve = self.so_dung_lai = 0

    def _ve_lai(self, anh_rgb, mat_na):
        """Chạy LaMa trên 1 ảnh cắt nhỏ. anh_rgb: HxWx3 uint8, mat_na: HxW (0/1)."""
        torch = self.torch
        h, w = mat_na.shape
        ph, pw = (-h) % 8, (-w) % 8
        anh = np.pad(anh_rgb, ((0, ph), (0, pw), (0, 0)), mode="symmetric")
        mn = np.pad(mat_na, ((0, ph), (0, pw)), mode="symmetric")
        t_anh = torch.from_numpy(anh).permute(2, 0, 1)[None].float().div(255).to(self.thiet_bi)
        t_mn = torch.from_numpy((mn > 0).astype(np.float32))[None, None].to(self.thiet_bi)
        with torch.inference_mode():
            kq = self.mo_hinh(t_anh, t_mn)[0].permute(1, 2, 0).cpu().numpy()
        return np.clip(kq * 255, 0, 255).astype(np.uint8)[:h, :w]

    def xoa(self, khung_bgr, cac_hop):
        """Xoá chữ trong các hộp [(x1, y1, x2, y2, cao_dong)] của 1 khung hình (BGR)."""
        if not cac_hop:
            return khung_bgr
        H, W = khung_bgr.shape[:2]
        ra = khung_bgr
        for x1, y1, x2, y2, cao in cac_hop:
            # vùng chữ nới thêm chút để ăn hết viền/bóng chữ
            dx, dy = 0.45 * cao, 0.3 * cao
            mx1, my1 = max(0, int(x1 - dx)), max(0, int(y1 - dy))
            mx2, my2 = min(W, int(x2 + dx)), min(H, int(y2 + dy))
            if mx2 <= mx1 or my2 <= my1:
                continue
            # vùng cắt ra cho AI xem: rộng hơn để có đủ nền xung quanh mà vẽ lại
            le = int(max(48, LE_NEN * cao))
            cx1, cy1 = max(0, mx1 - le), max(0, my1 - le)
            cx2, cy2 = min(W, mx2 + le), min(H, my2 + le)
            cat = ra[cy1:cy2, cx1:cx2]
            mn = np.zeros(cat.shape[:2], np.uint8)
            mn[my1 - cy1:my2 - cy1, mx1 - cx1:mx2 - cx1] = 1
            # nền xung quanh (ngoài vùng chữ), thu nhỏ để so nhanh
            nen = cv2.resize(cv2.cvtColor(cat, cv2.COLOR_BGR2GRAY), None, fx=0.25, fy=0.25,
                             interpolation=cv2.INTER_AREA).astype(np.float32)
            ngoai = cv2.resize(1 - mn, (nen.shape[1], nen.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
            khoa = (cx1, cy1, cx2, cy2, mx1, my1, mx2, my2)
            cu = self.nho.get(khoa)
            lech = np.abs(nen - cu[0])[ngoai] if cu and NGUONG_GIONG > 0 else None
            # giống cả trung bình lẫn từng chỗ nhỏ (tay/vật lướt qua cạnh chữ -> vẽ mới)
            if (lech is not None and lech.size and cu[2] < DUNG_LAI_TOI_DA
                    and float(lech.mean()) < NGUONG_GIONG and float(np.percentile(lech, 99)) < 8 * NGUONG_GIONG):
                moi = cu[1]
                self.nho[khoa] = (cu[0], cu[1], cu[2] + 1)
                self.so_dung_lai += 1
            else:
                moi = None
            if moi is None:
                # thu nhỏ để chữ cao ~48 điểm ảnh rồi mới cho AI vẽ (nhanh gấp ~4 lần, nền vẫn đẹp)
                tl = min(1.0, max(0.5, 48 / max(cao, 1)))
                rgb = cv2.cvtColor(cat, cv2.COLOR_BGR2RGB)
                if tl < 1:
                    nho = cv2.resize(rgb, None, fx=tl, fy=tl, interpolation=cv2.INTER_AREA)
                    mn_nho = cv2.resize(mn, (nho.shape[1], nho.shape[0]), interpolation=cv2.INTER_NEAREST)
                    moi = cv2.resize(self._ve_lai(nho, cv2.dilate(mn_nho, np.ones((3, 3), np.uint8))),
                                     (cat.shape[1], cat.shape[0]), interpolation=cv2.INTER_CUBIC)
                else:
                    moi = self._ve_lai(rgb, mn)
                moi = cv2.cvtColor(moi, cv2.COLOR_RGB2BGR)
                self.nho[khoa] = (nen, moi, 0)
                self.so_ve += 1
            # ghép lại: trong vùng chữ lấy ảnh mới, mép chuyển mềm vài điểm ảnh
            a = cv2.GaussianBlur(cv2.dilate(mn.astype(np.float32), np.ones((5, 5), np.uint8)), (7, 7), 0)
            a = np.maximum(a, mn)[..., None]
            ra = ra.copy() if ra is khung_bgr else ra
            ra[cy1:cy2, cx1:cx2] = (moi * a + cat * (1 - a)).astype(np.uint8)
        return ra
