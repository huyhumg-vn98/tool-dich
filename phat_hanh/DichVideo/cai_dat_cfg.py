"""Áp tinh chỉnh của tool vào cài đặt pyVideoTrans (bộ cài gọi file này).

- Chia câu theo từng cụm lời -> lồng tiếng khớp hình.
- Lồng tiếng 6 câu song song -> nhanh hơn.
"""
import json
from pathlib import Path

f = Path(__file__).resolve().parent / "pyvideotrans" / "videotrans" / "cfg.json"
d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
d.update({
    "min_speech_duration_ms": 500,
    "min_silence_duration_ms": 150,
    "max_speech_duration_s": 3.0,
    "dubbing_thread": 6,
    "crf": 16,                       # chất lượng video cao (khi pyVideoTrans phải mã hoá lại)
    "preset": "slow",
    "uvr_models": "UVR-MDX-NET-Inst_HQ_4",   # mô hình tách giọng / nhạc nền chất lượng cao
})
f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
print("Đã áp cài đặt chia câu + lồng tiếng song song")
