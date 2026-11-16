"""Chạy cli.py của pyVideoTrans nhưng gán giọng riêng cho từng câu (video 2 người nói).

    <python pyVideoTrans> chay_vai.py <file vai.json> cli.py <các tham số của cli.py>
vai.json = {"<số câu>": "<giọng>", ...}. Chạy với thư mục hiện tại = thư mục pyvideotrans.
"""
import json
import os
import runpy
import sys

sys.path.insert(0, os.getcwd())
vai = json.loads(open(sys.argv[1], encoding="utf-8").read())
from videotrans.configure.config import app_cfg  # noqa: E402

app_cfg.line_roles = {str(k): v for k, v in vai.items()}
sys.argv = sys.argv[2:]
runpy.run_path(sys.argv[0], run_name="__main__")
