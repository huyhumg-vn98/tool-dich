#!/bin/zsh
# ============================================================
#  CÀI ĐẶT TOOL DỊCH VIDEO DOUYIN -> TIẾNG VIỆT (macOS)
#  Bấm đúp file này. Cài lần đầu mất khoảng 15-30 phút.
# ============================================================
set -e
GOC="$(cd "$(dirname "$0")" && pwd)"
cd "$GOC"
PVT_COMMIT="370a65ca391022e32355413bd6be22156ade943c"   # bản pyVideoTrans đã kiểm tra

xanh() { print -P "%F{green}$1%f"; }
vang() { print -P "%F{yellow}$1%f"; }
do_() { print -P "%F{red}$1%f"; }
buoc() { echo; xanh "==> $1"; }

loi() {
  do_ "\n✖ Cài đặt bị lỗi ở bước trên."
  do_ "  Chụp màn hình cửa sổ này gửi cho người đưa bạn bộ cài để được hỗ trợ."
  echo "Bấm Enter để đóng."; read
}
trap loi ERR

echo "Thư mục cài: $GOC"
if [[ "$GOC" == *" "* ]]; then vang "(Đường dẫn có dấu cách - vẫn chạy được)"; fi

# ---------- 1. Công cụ dòng lệnh của Apple (cần để biên dịch) ----------
buoc "1/7 Kiểm tra Command Line Tools của Apple"
if ! xcode-select -p >/dev/null 2>&1; then
  vang "Máy sẽ hiện cửa sổ cài 'Command Line Tools'. Bấm Install và chờ cài xong."
  xcode-select --install || true
  echo "Cài xong thì bấm Enter để tiếp tục..."; read
fi

# ---------- 2. Homebrew ----------
buoc "2/7 Kiểm tra Homebrew"
if [ -x /opt/homebrew/bin/brew ]; then BREW=/opt/homebrew
elif [ -x /usr/local/bin/brew ]; then BREW=/usr/local
else
  vang "Chưa có Homebrew. Đang cài (sẽ hỏi mật khẩu máy Mac của bạn)..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [ -x /opt/homebrew/bin/brew ]; then BREW=/opt/homebrew; else BREW=/usr/local; fi
fi
export PATH="$BREW/bin:$PATH"
eval "$($BREW/bin/brew shellenv)"

# ---------- 3. Thư viện hệ thống ----------
buoc "3/7 Cài ffmpeg, uv, openfst... (vài phút)"
brew install git uv libsndfile openfst ffmpeg ffmpeg-full

# ---------- 4. pyVideoTrans ----------
buoc "4/7 Tải pyVideoTrans"
if [ ! -d pyvideotrans/.git ]; then
  git clone https://github.com/jianchang512/pyvideotrans.git pyvideotrans
fi
git -C pyvideotrans fetch --depth 1 origin "$PVT_COMMIT" 2>/dev/null || git -C pyvideotrans fetch origin
git -C pyvideotrans checkout -q "$PVT_COMMIT"

buoc "5/7 Cài thư viện Python cho pyVideoTrans (lâu nhất, ~2-3 GB, có thể 10-20 phút)"
# pynini cần OpenFst; bản Homebrew mới đổi tên hàm StringJoin -> StrJoin
export CPATH="$BREW/include" LIBRARY_PATH="$BREW/lib"
export CFLAGS="-DStringJoin=StrJoin" CXXFLAGS="-DStringJoin=StrJoin"
(cd pyvideotrans && uv sync)
unset CFLAGS CXXFLAGS

# Tạo file cài đặt mặc định của pyVideoTrans rồi áp các tinh chỉnh của tool
(cd pyvideotrans && .venv/bin/python -c "from videotrans.configure import config" >/dev/null 2>&1 || true)
pyvideotrans/.venv/bin/python - <<'PY'
import json
from pathlib import Path
f = Path("pyvideotrans/videotrans/cfg.json")
d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
d.update({
    "min_speech_duration_ms": 500,   # chia câu theo từng cụm lời -> lồng tiếng khớp hình
    "min_silence_duration_ms": 150,
    "max_speech_duration_s": 3.0,
    "dubbing_thread": 6,             # lồng tiếng 6 câu song song
    "crf": 16, "preset": "slow",     # chất lượng video cao
    "uvr_models": "UVR-MDX-NET-Inst_HQ_4",   # tách giọng / nhạc nền chất lượng cao
})
f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
print("Đã áp cài đặt chia câu + lồng song song")
PY

# ---------- 6. Môi trường cho phần đọc chữ / tải video ----------
buoc "6/7 Cài phần đọc chữ trên hình (OCR) và tải video"
[ -d .venv_tool ] || uv venv --python 3.10 .venv_tool
VIRTUAL_ENV="$GOC/.venv_tool" uv pip install rapidocr onnxruntime opencv-python-headless numpy requests yt-dlp torch==2.7.0
# Mô hình AI xoá chữ gốc (LaMa, ~200 MB). Tải lỗi thì tool tự dùng kiểu khung đen.
mkdir -p mo_hinh
if [ ! -s mo_hinh/big-lama.pt ]; then
  curl -fL --retry 3 -o mo_hinh/big-lama.pt.tam \
    https://github.com/Sanster/models/releases/download/add_big_lama/big-lama.pt \
    && mv mo_hinh/big-lama.pt.tam mo_hinh/big-lama.pt \
    || { rm -f mo_hinh/big-lama.pt.tam; vang "Chưa tải được mô hình AI xoá chữ - tạm dùng kiểu khung đen."; }
fi
# Mô hình AI làm nét video mờ (Real-ESRGAN, ~5 MB). Tải lỗi thì bỏ qua bước làm nét.
if [ ! -s mo_hinh/realesr-general-x4v3.pth ]; then
  curl -fL --retry 3 -o mo_hinh/realesr-general-x4v3.pth.tam \
    https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth \
    && mv mo_hinh/realesr-general-x4v3.pth.tam mo_hinh/realesr-general-x4v3.pth \
    || { rm -f mo_hinh/realesr-general-x4v3.pth.tam; vang "Chưa tải được mô hình làm nét - bỏ qua bước làm nét."; }
fi

# ---------- 7. Tạo app ----------
buoc "7/7 Tạo ứng dụng 'Dịch Video.app'"
mkdir -p Video_Vao Video_Ra
sed "s|__GOC__|$GOC|g" mo_app.applescript > /tmp/dichvideo_app.applescript
rm -rf "Dịch Video.app"
osacompile -o "Dịch Video.app" /tmp/dichvideo_app.applescript
rm -f /tmp/dichvideo_app.applescript

trap - ERR
echo
xanh "✔ CÀI ĐẶT XONG!"
echo "  • Mở tool: bấm đúp 'Dịch Video.app' trong thư mục này."
echo "  • Lần dịch đầu tiên sẽ tự tải mô hình nghe (~3 GB), các lần sau nhanh."
echo "  • API key ai33 / DeepSeek (nếu có) nhập trên giao diện. Không có key vẫn dùng"
echo "    được Google Dịch + giọng Edge miễn phí."
echo "  • Hướng dẫn: HUONG_DAN.md"
open "$GOC"
echo "Bấm Enter để đóng."; read
