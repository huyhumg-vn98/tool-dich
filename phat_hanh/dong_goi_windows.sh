#!/bin/zsh
# Đóng gói bộ cài WINDOWS: chỉ lấy code của tool, KHÔNG lấy key, video, môi trường Python.
#   zsh phat_hanh/dong_goi_windows.sh   ->  tạo phat_hanh/DichVideo_Windows_CaiDat.zip
set -e
GOC="$(cd "$(dirname "$0")/.." && pwd)"
RA="$GOC/phat_hanh"
TAM="$(mktemp -d)/DichVideo"
mkdir -p "$TAM"

for f in auto_dich.py hang_doi.py che_chu.py ai33.py deepseek_cfg.py tai_douyin.py xoa_chu_ai.py thuyet_minh.py hieu_ung.py gia_tien.py rut_gon.py lam_net.py viet_lai.py giao_dien.html \
         HUONG_DAN.md cai_dat_cfg.py; do
  cp "$GOC/$f" "$TAM/"
done
cp "$RA/GIAY_PHEP.md" "$TAM/"
cp "$RA/windows/DOC_TRUOC.md" "$RA/windows/CaiDat.bat" "$RA/windows/Dich Video.bat" "$RA/windows/CaiDat.ps1" "$TAM/"

# File của Windows: xuống dòng kiểu CRLF; PowerShell cần UTF-8 có BOM để hiện đúng tiếng Việt
"$GOC/.venv_tool/bin/python" - "$TAM" <<'PY'
import sys
from pathlib import Path
d = Path(sys.argv[1])
for p in list(d.glob("*.bat")) + list(d.glob("*.ps1")) + list(d.glob("*.md")):
    t = p.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\n", "\r\n")
    p.write_bytes((b"\xef\xbb\xbf" if p.suffix == ".ps1" else b"") + t.encode("utf-8"))
    if p.suffix == ".bat":
        t.encode("ascii")   # .bat phải thuần ASCII (cmd không đọc tốt tiếng Việt)
print("✔ Đã chuyển định dạng file cho Windows")
PY

# ---- Kiểm tra không lọt key / dữ liệu cá nhân ----
LOI=0
kiem() {
  [ -n "$1" ] || return 0
  if grep -rqF -- "$1" "$TAM"; then echo "✖ Gói có chứa $2!"; LOI=1; fi
}
kiem "$(cat "$GOC/.ai33_key" 2>/dev/null)" "API key ai33"
kiem "$("$GOC/pyvideotrans/.venv/bin/python" -c "import json;print(json.load(open('$GOC/pyvideotrans/videotrans/params.json')).get('deepseek_key',''))" 2>/dev/null)" "API key DeepSeek"
kiem "$(whoami)" "tên người dùng máy ($(whoami))"
if grep -rqE "sk-[A-Za-z0-9]{20,}" "$TAM"; then echo "✖ Gói có chuỗi giống API key (sk-...)!"; LOI=1; fi
[ "$LOI" = 0 ] || { echo "Dừng đóng gói."; exit 1; }
echo "✔ Không có key hay dữ liệu cá nhân trong gói."

rm -f "$RA/DichVideo_Windows_CaiDat.zip"
(cd "$(dirname "$TAM")" && zip -qr "$RA/DichVideo_Windows_CaiDat.zip" DichVideo)
rm -rf "$(dirname "$TAM")"
echo "✔ Đã tạo: $RA/DichVideo_Windows_CaiDat.zip ($(du -h "$RA/DichVideo_Windows_CaiDat.zip" | cut -f1))"
