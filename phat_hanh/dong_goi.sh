#!/bin/zsh
# Đóng gói bộ cài để gửi người khác: chỉ lấy code của tool, KHÔNG lấy key, video, môi trường Python.
#   zsh phat_hanh/dong_goi.sh   ->  tạo phat_hanh/DichVideo_CaiDat.zip
set -e
GOC="$(cd "$(dirname "$0")/.." && pwd)"
RA="$GOC/phat_hanh"
TAM="$(mktemp -d)/DichVideo"
mkdir -p "$TAM"

for f in auto_dich.py hang_doi.py che_chu.py ai33.py deepseek_cfg.py tai_douyin.py xoa_chu_ai.py thuyet_minh.py hieu_ung.py gia_tien.py rut_gon.py lam_net.py viet_lai.py hai_giong.py chay_vai.py giao_dien.html HUONG_DAN.md cai_dat_cfg.py; do
  cp "$GOC/$f" "$TAM/"
done
for f in CaiDat.command mo_app.applescript DOC_TRUOC.md GIAY_PHEP.md; do
  cp "$RA/$f" "$TAM/"
done
chmod +x "$TAM/CaiDat.command"

# ---- Kiểm tra không lọt key / dữ liệu cá nhân ----
LOI=0
kiem() {  # $1 = chuỗi bí mật, $2 = tên
  [ -n "$1" ] || return 0
  if grep -rqF -- "$1" "$TAM"; then echo "✖ Gói có chứa $2!"; LOI=1; fi
}
kiem "$(cat "$GOC/.ai33_key" 2>/dev/null)" "API key ai33"
kiem "$("$GOC/pyvideotrans/.venv/bin/python" -c "import json;print(json.load(open('$GOC/pyvideotrans/videotrans/params.json')).get('deepseek_key',''))" 2>/dev/null)" "API key DeepSeek"
kiem "$(whoami)" "tên người dùng máy ($(whoami))"
if grep -rqE "sk-[A-Za-z0-9]{20,}" "$TAM"; then echo "✖ Gói có chuỗi giống API key (sk-...)!"; LOI=1; fi
[ "$LOI" = 0 ] || { echo "Dừng đóng gói."; exit 1; }
echo "✔ Không có key hay dữ liệu cá nhân trong gói."

rm -f "$RA/DichVideo_CaiDat.zip"
(cd "$(dirname "$TAM")" && zip -qr "$RA/DichVideo_CaiDat.zip" DichVideo)
rm -rf "$(dirname "$TAM")"
echo "✔ Đã tạo: $RA/DichVideo_CaiDat.zip ($(du -h "$RA/DichVideo_CaiDat.zip" | cut -f1))"
