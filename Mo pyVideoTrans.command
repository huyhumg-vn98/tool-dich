#!/bin/zsh
# Mở pyVideoTrans với ffmpeg-full (có hỗ trợ chèn phụ đề)
export PATH="/opt/homebrew/opt/ffmpeg-full/bin:/opt/homebrew/bin:$PATH"
cd "$(dirname "$0")/pyvideotrans"
uv run sp.py
