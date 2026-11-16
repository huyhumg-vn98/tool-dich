"""Tự động dịch video sang tiếng Việt bằng pyVideoTrans.

Cách dùng:
    python auto_dich.py video1.mp4 video2.mp4 ...
Không truyền file nào thì script dịch mọi video trong thư mục Video_Vao.
Video xong nằm trong thư mục Video_Ra, tên dạng <tên gốc>_vi.mp4.

Mỗi lần chạy sẽ hỏi: chọn giọng, tốc độ đọc, có sửa phụ đề trước khi lồng tiếng không.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ===== Cài đặt cố định (sửa ở đây nếu muốn) =====
NGON_NGU_DICH = "vi"
MO_HINH = "large-v3"     # nhận dạng giọng nói: large-v3 (chuẩn) / medium (nhanh hơn)
KIEU_PHU_DE = "1"        # 0=không, 1=phụ đề cứng, 2=phụ đề mềm, 3=song ngữ cứng
# ================================================

# Tên hiển thị -> (mã engine lồng tiếng, giọng)
GIONG = {
    "Nữ - HoaiMy (Microsoft Edge)": ("0", "vi-VN-HoaiMyNeural"),
    "Nam - NamMinh (Microsoft Edge)": ("0", "vi-VN-NamMinhNeural"),
    "Nữ - Google (gTTS)": ("31", "gtts"),
    "Không lồng tiếng (chỉ gắn phụ đề)": ("0", "No"),
}
CONG_HANG_DOI = 8765  # máy chủ hang_doi.py: có cầu nối gửi câu sang ai33


def danh_sach_giong() -> dict:
    """Giọng có sẵn + giọng ai33 bạn đã thêm (mã engine 35 = Custom TTS API của pyVideoTrans)."""
    ds = dict(GIONG)
    try:
        for g in json.loads((Path(__file__).resolve().parent / ".giong_ai33.json").read_text(encoding="utf-8")):
            ds[f"ai33 · {g['ten']}"] = ("35", g["voice_id"])
    except Exception:
        pass
    return ds


TOC_DO = {
    "Bình thường": "+0%",
    "Nhanh hơn một chút (+10%)": "+10%",
    "Nhanh (+20%)": "+20%",
    "Chậm hơn (-10%)": "-10%",
}
# Cách dịch -> mã translate_type của pyVideoTrans
CACH_DICH = {
    "Google Dịch (miễn phí)": "0",
    "DeepSeek (AI, hiểu ngữ cảnh)": "5",
}
PD_XOA = "Che chữ gốc: AI xoá sạch, phụ đề Việt đè lên"   # không khung, chậm hơn
PD_CHE = "Che chữ gốc, phụ đề Việt đè lên"                 # khung đen
PD_THUONG = "Phụ đề thường ở dưới video"
PD_KHONG = "Không gắn phụ đề"
SUA_CO = "Có - cho tôi sửa phụ đề trước khi lồng tiếng"
SUA_KHONG = "Không - chạy thẳng ra video"
SUA_GIA = "Chỉ khi có nói giá - dừng cho tôi kiểm tra, không có giá thì chạy thẳng"
AM_GIU = "Giữ nhạc nền & hiệu ứng, chỉ thay giọng"
AM_BO = "Bỏ hết tiếng gốc, chỉ còn giọng Việt"
TM_TU_DONG = "Video không có lời: AI viết lời giới thiệu sản phẩm"
TM_KHONG = "Video không có lời: bỏ qua (báo lỗi)"
NET_CO = "Làm nét video mờ bằng AI (video dưới 1080p, chậm hơn)"
NET_KHONG = "Không làm nét"
GIONG2_KHONG = "Không (video 1 người nói)"

GOC = Path(__file__).resolve().parent
sys.path.insert(0, str(GOC))
import gia_tien  # noqa: E402  (chuẩn hoá giá tiền để giọng đọc đúng mệnh giá)
PVT = GOC / "pyvideotrans"
WIN = sys.platform == "win32"


def python_cua(thu_muc: Path) -> Path:
    """Đường dẫn python trong môi trường ảo (.venv): Windows ở Scripts\\, Mac ở bin/."""
    return thu_muc / ("Scripts/python.exe" if WIN else "bin/python")


PY_PVT = python_cua(PVT / ".venv")        # python của pyVideoTrans
PY_TOOL = python_cua(GOC / ".venv_tool")  # python cho đọc chữ (OCR) + tải video
if WIN:
    # Windows: bộ cài để ffmpeg trong thư mục tool, uv ở %USERPROFILE%\\.local\\bin
    FFMPEG_DIR = str(GOC / "ffmpeg" / "bin")
    PATH_THEM = FFMPEG_DIR + os.pathsep + str(Path.home() / ".local" / "bin") + os.pathsep
else:
    # Mac: Homebrew ở /opt/homebrew (chip Apple) hoặc /usr/local (Intel)
    BREW = "/opt/homebrew" if Path("/opt/homebrew/bin/brew").exists() else "/usr/local"
    FFMPEG_DIR = f"{BREW}/opt/ffmpeg-full/bin"        # ffmpeg đầy đủ (có chèn phụ đề)
    PATH_THEM = f"{FFMPEG_DIR}:{BREW}/bin:"
FFMPEG = str(Path(FFMPEG_DIR) / ("ffmpeg.exe" if WIN else "ffmpeg"))


def la_kieu_che(phu_de) -> bool:
    """Kiểu phụ đề 'che chữ gốc' (gồm cả tên cũ '... (khung đen)')."""
    return phu_de is None or str(phu_de).startswith("Che chữ gốc")


def kieu_che(phu_de) -> str:
    """Cách che cho che_chu.py: 'ai' = AI xoá sạch chữ gốc, 'den' = khung đen."""
    return "ai" if phu_de is None or phu_de == PD_XOA else "den"


def mo(duong_dan, chon_trong_thu_muc=False):
    """Mở file / thư mục / trang web bằng ứng dụng mặc định."""
    duong_dan = str(duong_dan)
    if WIN:
        if chon_trong_thu_muc:
            subprocess.run(["explorer", "/select,", duong_dan])
        else:
            os.startfile(duong_dan)
    else:
        subprocess.run(["open", "-R", duong_dan] if chon_trong_thu_muc else ["open", duong_dan])


def chep(chu: str):
    """Chép chữ vào clipboard."""
    if WIN:
        subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $input"],
                       input=chu, text=True)
    else:
        subprocess.run(["pbcopy"], input=chu, text=True)
VAO = GOC / "Video_Vao"
RA = GOC / "Video_Ra"
LUA_CHON_CU = GOC / ".lua_chon.json"
DUOI_VIDEO = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".flv"}

# Mã ngôn ngữ của whisper -> mã của pyVideoTrans (chỉ khác ở vài ngôn ngữ)
MAP_NGON_NGU = {"zh": "zh-cn", "jw": "jv", "tl": "fil", "no": "nb"}


# ---------- Hộp thoại macOS ----------
def _as(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def chon(tieu_de: str, cac_muc: list, mac_dinh: str):
    """Hiện danh sách để chọn. Trả về mục đã chọn, hoặc None nếu bấm Huỷ."""
    if mac_dinh not in cac_muc:
        mac_dinh = cac_muc[0]
    ds = "{" + ", ".join(_as(m) for m in cac_muc) + "}"
    script = (f"choose from list {ds} with prompt {_as(tieu_de)} "
              f"default items {{{_as(mac_dinh)}}} OK button name \"Chọn\" cancel button name \"Huỷ\"")
    kq = subprocess.run(["osascript", "-e", script], capture_output=True, text=True).stdout.strip()
    return None if kq in ("", "false") else kq


def hop_thoai(noi_dung: str, nut: list) -> str:
    script = (f"display dialog {_as(noi_dung)} buttons {{{', '.join(_as(n) for n in nut)}}} "
              f"default button {_as(nut[-1])} with title \"Dịch Video\"")
    kq = subprocess.run(["osascript", "-e", script], capture_output=True, text=True).stdout
    return kq.split("button returned:")[-1].strip()


def hoi_lua_chon():
    cu = {}
    try:
        cu = json.loads(LUA_CHON_CU.read_text())
    except Exception:
        pass
    giong = chon("Chọn giọng lồng tiếng:", list(danh_sach_giong()), cu.get("giong", ""))
    if giong is None:
        return None
    toc_do = "Bình thường"
    if danh_sach_giong()[giong][1] != "No":
        toc_do = chon("Tốc độ đọc:", list(TOC_DO), cu.get("toc_do", ""))
        if toc_do is None:
            return None
    phu_de = chon("Kiểu phụ đề trên video:", [PD_XOA, PD_CHE, PD_THUONG, PD_KHONG], cu.get("phu_de", PD_XOA))
    if phu_de is None:
        return None
    sua = chon("Sửa phụ đề tiếng Việt trước khi lồng tiếng?", [SUA_CO, SUA_KHONG], cu.get("sua", SUA_CO))
    if sua is None:
        return None
    lc = {"giong": giong, "toc_do": toc_do, "phu_de": phu_de, "sua": sua}
    try:
        LUA_CHON_CU.write_text(json.dumps(lc, ensure_ascii=False))
    except Exception:
        pass
    return lc


# ---------- Xử lý ----------
def nhan_dien_ngon_ngu(video: Path, chay=subprocess.run) -> str:
    """Nghe thử video bằng mô hình nhỏ để biết đang nói tiếng gì."""
    code = (
        "import sys\n"
        "from faster_whisper import WhisperModel\n"
        "m = WhisperModel('base', device='cpu', compute_type='int8')\n"
        "_, info = m.transcribe(sys.argv[1], beam_size=1)\n"
        "print(info.language)\n"
    )
    kq = chay([str(PY_PVT), "-c", code, str(video)],
              capture_output=True, text=True)
    lang = kq.stdout.strip().splitlines()[-1] if kq.stdout.strip() else "en"
    return MAP_NGON_NGU.get(lang, lang)


def chay_pvt(video: Path, lang: str, tam: Path, tts_type: str, giong: str,
             toc_do: str, phu_de: str, xoa_cache: bool, dich: str = "0", chay=subprocess.run,
             tach_giong: bool = False, viet_loi=None, chi_dich: bool = False,
             kieu: str = None, hai_giong: dict = None) -> subprocess.CompletedProcess:
    """viet_loi(tam, lang): hàm viết lời thuyết minh khi video không có lời nói (None = không viết).
    Trả về None nếu viết xong (đã có tam/vi.srt), hoặc CompletedProcess báo lỗi.
    chi_dich=True: chỉ nghe + dịch ra tam/vi.srt rồi dừng (chưa lồng tiếng) để kiểm tra trước."""
    if tts_type == "35":
        dat_cau_noi_ai33()
    dat_luat_gia_tien()
    dat_ha_nhac_nen()
    env = dict(os.environ)
    # ffmpeg-full có hỗ trợ chèn phụ đề
    env["PATH"] = PATH_THEM + env.get("PATH", "")
    tam = Path(tam).resolve()
    video = Path(video).resolve()
    if xoa_cache:
        # Lần chạy mới: tự nghe trước để sửa câu bị cắt vụn, rồi pyVideoTrans dịch + lồng tiếng từ file đã sửa
        shutil.rmtree(tam, ignore_errors=True)
        kq = nghe(Path(video).resolve(), lang, tam, env, chay, hai_nguoi=bool(hai_giong))
        goc = tam / f"{lang}.srt"
        if viet_loi is not None and (kq.returncode != 0 or not goc.exists() or khong_co_loi(goc, video)):
            loi = viet_loi(tam, lang)
            if loi is not None:
                return loi
        if not goc.exists():
            return kq
        xoa_cache = False
        vi = tam / f"{NGON_NGU_DICH}.srt"
        if (giong != "No" or chi_dich) and not vi.exists():
            # dịch riêng trước để sửa giá tiền / con số rồi mới lồng tiếng
            dich_rieng(goc, lang, dich, tam, env, chay)
        if vi.exists():
            hoan_thien_phu_de(vi, goc, kieu)
        if chi_dich:
            return subprocess.CompletedProcess([], 0, "", "")
    vi, goc = tam / f"{NGON_NGU_DICH}.srt", tam / f"{lang}.srt"
    hien = gia_tien.tach_doc(vi, goc) if giong != "No" and vi.exists() else None
    lenh = [
        str(PY_PVT), "cli.py", "--task", "vtv",
        "--name", str(video),
        "--source_language_code", lang,
        "--target_language_code", NGON_NGU_DICH,
        "--recogn_type", "0", "--model_name", MO_HINH,
        "--translate_type", dich,
        "--tts_type", tts_type, "--voice_role", giong,
        "--voice_rate", toc_do, "--voice_autorate",
        "--subtitle_type", phu_de,
        *(["--is_separate"] if tach_giong and giong != "No" else []),  # tách giọng gốc, giữ nhạc nền
        "--output-dir", str(tam),
        "--cuda",      # có card NVIDIA chạy được thì dùng card (không có thì pyVideoTrans tự bỏ qua)
    ]
    if not xoa_cache:
        lenh.append("--no-clear-cache")  # giữ phụ đề đã sửa, bỏ qua bước nhận dạng + dịch
    vai = chia_vai(video, tam, lang, giong, tts_type, hai_giong) if giong != "No" else None
    if vai:   # video 2 người nói: mỗi câu 1 giọng riêng
        lenh = [str(PY_PVT), str(GOC / "chay_vai.py"), str(vai)] + lenh[1:]
    kq = chay(lenh, cwd=PVT, env=env, capture_output=True, text=True)
    if hien:
        gia_tien.tra_hien(vi, hien)      # phụ đề hiện trên video giữ dạng số (9,9 tệ)
    elif vi.exists():
        hoan_thien_phu_de(vi, goc, kieu)       # bước chỉ dịch (chờ sửa): sửa sẵn giá tiền, rút gọn câu dài
    return kq


def hoan_thien_phu_de(vi: Path, goc: Path, kieu: str = None):
    """Sau khi dịch: viết lại tự nhiên + câu mở đầu thu hút, đổi giá tiền, rút gọn câu quá dài."""
    import viet_lai
    viet_lai.viet_lai(vi, goc, kieu)
    gia_tien.sua_hien(vi, goc)
    import rut_gon
    rut_gon.rut_gon(vi)
    rut_gon.chia_lai_thoi_gian(vi)


def chia_vai(video, tam: Path, lang: str, giong: str, tts_type: str, hai_giong: dict):
    """Video 2 người nói -> tam/vai.json {số câu: giọng}. Trả về đường dẫn file, hoặc None nếu dùng 1 giọng."""
    try:
        if not hai_giong or hai_giong.get("tts") != tts_type or not hai_giong.get("giong") \
                or hai_giong["giong"] == giong or not (tam / "nguoi_noi.json").exists():
            return None
        nguoi = json.loads((tam / "nguoi_noi.json").read_text(encoding="utf-8"))
        k_goc = gia_tien._doc_srt(tam / f"{lang}.srt")
        k_vi = gia_tien._doc_srt(tam / f"{NGON_NGU_DICH}.srt")
        if not (len(nguoi) == len(k_goc) == len(k_vi)):
            return None
        import hai_giong as hg
        moc = []
        for _, t, _ in k_goc:
            a, b = t.split("-->")
            h1, m1, r1 = a.strip().split(":"); h2, m2, r2 = b.strip().split(":")
            moc.append((int(h1) * 3600 + int(m1) * 60 + float(r1.replace(",", ".")),
                        int(h2) * 3600 + int(m2) * 60 + float(r2.replace(",", "."))))
        kq = hg.gan_giong(video, moc, nguoi, giong, hai_giong["giong"], FFMPEG,
                          hai_giong.get("ten1", ""), hai_giong.get("ten2", ""))
        (tam / "hai_giong.json").write_text(json.dumps({"ghi_chu": kq["ghi_chu"]}, ensure_ascii=False), encoding="utf-8")
        if all(v == giong for v in kq["vai"]):
            return None
        f = tam / "vai.json"
        f.write_text(json.dumps({k[0]: v for k, v in zip(k_vi, kq["vai"])}, ensure_ascii=False), encoding="utf-8")
        return f
    except Exception:
        return None


def dich_rieng(goc: Path, lang: str, dich: str, tam: Path, env: dict, chay=subprocess.run):
    """Chỉ dịch phụ đề gốc -> tam/vi.srt (lỗi thì để pyVideoTrans tự dịch như cũ)."""
    ra = tam / "_dich"
    shutil.rmtree(ra, ignore_errors=True)
    try:
        chay([str(PY_PVT), "cli.py", "--task", "sts", "--name", str(goc), "--source_language_code", lang,
              "--target_language_code", NGON_NGU_DICH, "--translate_type", dich, "--output-dir", str(ra)],
             cwd=PVT, env=env, capture_output=True, text=True)
        f = next(ra.glob(f"*.{NGON_NGU_DICH}.srt"), None) if ra.exists() else None
        if f and f.stat().st_size > 0:
            shutil.copy2(f, tam / f"{NGON_NGU_DICH}.srt")
    finally:
        shutil.rmtree(ra, ignore_errors=True)


LUAT_GIA = """
PRICES & MONEY (critical: the voice reads exactly what you write). Prices in these videos are Chinese yuan:
- Translate 元/块/块钱 as "tệ". ALWAYS keep the exact amount, written in digits, followed by "tệ" for EVERY price,
  even when the source omits the unit (只要69.9 -> "chỉ 69,9 tệ"; 九块九 -> "9,9 tệ"; 两块五 -> "2,5 tệ";
  五毛 -> "0,5 tệ"; 三十来块 -> "khoảng 30 tệ"; 三块一包 -> "3 tệ một gói").
- Vietnamese number format: comma for decimals (69,9), dot for thousands (20.000). 万 = 10.000 (2万 -> 20.000, never "vạn").
- Never convert to VND. Never use "chục", "xị", "k", "hào", "rưỡi", "đồng" for prices."""
_DAU_GIA = "PRICES & MONEY (critical"


# Tự hạ nhạc nền khi có giọng đọc (ducking). Nhạc nhỏ đi khoảng HA_NHAC_DB khi có giọng, hết giọng to lại.
HA_NHAC = True
HA_NHAC_TY_LE = 4          # càng lớn nhạc càng bị hạ mạnh (4 ~ nhỏ đi 8 dB; 6 ~ 11 dB)
_TRON_CU = "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,alimiter=limit=0.95:level=0"


def dat_ha_nhac_nen():
    """Sửa bước trộn giọng + nhạc nền của pyVideoTrans: nhạc tự nhỏ lại khi có giọng đọc."""
    f = PVT / "videotrans" / "task" / "_stage_audio.py"
    try:
        s = f.read_text(encoding="utf-8")
        moi = ("[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[vo][sc];"
               f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo[bgi];"
               f"[bgi][sc]sidechaincompress=threshold=0.02:ratio={HA_NHAC_TY_LE}:attack=30:release=500[bg];"
               "[vo][bg]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,alimiter=limit=0.95:level=0")
        hien = re.search(r'"(\[0:a\][^"]*amix=inputs=2:duration=first[^"]*)"', s)
        if not hien:
            return
        muon = moi if HA_NHAC else _TRON_CU
        if hien.group(1) != muon:
            f.write_text(s.replace(hien.group(1), muon), encoding="utf-8")
    except Exception:
        pass


def dat_luat_gia_tien():
    """Thêm luật giá tiền vào hướng dẫn dịch tiếng Việt của pyVideoTrans (cho DeepSeek / AI dịch)."""
    f = PVT / "videotrans" / "prompts" / "language_prompts" / f"{NGON_NGU_DICH}.txt"
    try:
        cu = f.read_text(encoding="utf-8") if f.exists() else ""
        if _DAU_GIA not in cu:
            f.write_text(cu.rstrip() + "\n" + LUAT_GIA, encoding="utf-8")
    except Exception:
        pass


def nghe(video: Path, lang: str, tam: Path, env: dict, chay=subprocess.run, hai_nguoi: bool = False) -> subprocess.CompletedProcess:
    """Bước nghe: chuyển lời nói thành phụ đề gốc tam/<lang>.srt, rồi gộp các câu bị cắt vụn."""
    tam.mkdir(parents=True, exist_ok=True)
    tam_nghe = tam / "_nghe"
    shutil.rmtree(tam_nghe, ignore_errors=True)
    kq = chay([str(PY_PVT), "cli.py", "--task", "stt", "--name", str(video),
               "--source_language_code", lang, "--recogn_type", "0", "--model_name", MO_HINH,
               "--output-dir", str(tam_nghe), "--cuda",
               *(["--enable_diariz", "--nums_diariz", "2"] if hai_nguoi else [])],   # video 2 người: tách người nói
              cwd=PVT, env=env, capture_output=True, text=True)
    srt = next(tam_nghe.glob("*.srt"), None) if tam_nghe.exists() else None
    if kq.returncode == 0 and srt:
        nguoi = None
        try:
            nguoi = json.loads((tam_nghe / "speaker.json").read_text(encoding="utf-8")) if hai_nguoi else None
        except Exception:
            pass
        nguoi = gop_cau_vun(srt, tam / f"{lang}.srt", nguoi=nguoi)
        if hai_nguoi and any(nguoi):
            (tam / "nguoi_noi.json").write_text(json.dumps(nguoi), encoding="utf-8")
        if lang.startswith("zh"):
            gia_tien.sua_goc(tam / f"{lang}.srt")    # "九块九" -> "9.9元" để dịch đúng giá
    shutil.rmtree(tam_nghe, ignore_errors=True)
    return kq


def ham_viet_loi(video: Path, chay=subprocess.run):
    """Tạo hàm cho chay_pvt: AI (DeepSeek) xem video rồi viết lời thuyết minh vào tam/vi.srt."""
    def viet(tam: Path, lang: str):
        vi = tam / f"{NGON_NGU_DICH}.srt"
        kq = chay([str(PY_TOOL), "-X", "utf8", "-I", str(GOC / "thuyet_minh.py"), str(Path(video).resolve()), str(vi)],
                  capture_output=True, text=True)
        if kq.returncode != 0 or not vi.exists():
            return kq
        # phụ đề "gốc" giả cùng mốc thời gian để pyVideoTrans bỏ qua bước nghe + dịch, lồng tiếng thẳng
        shutil.copy2(vi, tam / f"{lang}.srt")
        return None
    return viet


def khong_co_loi(srt: Path, video: Path) -> bool:
    """Phụ đề nghe được quá ít / vô nghĩa -> coi như video không có lời nói (chỉ nhạc, tiếng động).

    Mô hình nghe hay "bịa" vài chữ lặp lại khi chỉ có nhạc (vd "鸡鸡鸡", "字幕by...")."""
    import re as _re
    try:
        r = subprocess.run([str(Path(FFMPEG).with_name("ffprobe.exe" if WIN else "ffprobe")), "-v", "error",
                            "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                           capture_output=True, text=True)
        dai = float(r.stdout.strip() or 0)
    except Exception:
        dai = 0
    chu = ""
    noi = 0.0
    for k in _re.split(r"\n\s*\n", srt.read_text(encoding="utf-8-sig").strip()):
        ls = k.strip().splitlines()
        i = next((n for n, l in enumerate(ls) if "-->" in l), None)
        if i is None:
            continue
        try:
            a, b = [sum(float(x) * m for x, m in zip(t.strip().replace(",", ".").split(":"), (3600, 60, 1)))
                    for t in ls[i].split("-->")]
            noi += max(0.0, b - a)
        except ValueError:
            pass
        chu += "".join(ls[i + 1:])
    chu = _re.sub(r"[\s\W\d_]", "", chu)
    if len(chu) < 4 or len(set(chu)) <= 3:
        return True
    if dai > 0 and (len(chu) < 0.6 * dai or noi < 0.15 * dai):
        return True
    return False


def gop_cau_vun(vao: Path, ra: Path, it_chu: int = 2, ngan: float = 0.5, khe: float = 0.35, dai_nhat: float = 6.0,
                nguoi: list = None):
    """Gộp câu quá ngắn (<= it_chu chữ hoặc < ngan giây) vào câu sát bên cạnh.

    Ví dụ "关" | "注我后续..." -> "关注我后续...". Chỉ gộp khi 2 câu cách nhau < khe giây
    và câu sau khi gộp không dài quá dai_nhat giây (để giữ khớp hình).
    """
    import re as _re

    def giay(t):
        h, m, r = t.strip().split(":")
        s, ms = r.replace(".", ",").split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    def tg(x):
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

    cau = []
    for so, k in enumerate(_re.split(r"\n\s*\n", vao.read_text(encoding="utf-8-sig").strip())):
        ls = k.strip().splitlines()
        i = next((n for n, l in enumerate(ls) if "-->" in l), None)
        if i is None:
            continue
        a, b = ls[i].split("-->")
        chu = " ".join(l.strip() for l in ls[i + 1:] if l.strip())
        chu = _re.sub(r"^\[spk\d+\]\s*", "", chu)          # nhãn người nói do bước tách người nói chèn vào
        if chu:
            cau.append([giay(a), giay(b), chu, nguoi[so] if nguoi and so < len(nguoi) else ""])

    def so_chu(s):
        return len(_re.sub(r"[\s\W\d_]", "", s))

    doi = True
    while doi:
        doi = False
        for n, (a, b, chu, sp) in enumerate(cau):
            if so_chu(chu) > it_chu and b - a >= ngan:
                continue
            truoc = cau[n - 1] if n > 0 else None
            sau = cau[n + 1] if n + 1 < len(cau) else None
            # không gộp lời của 2 người khác nhau
            gan_truoc = truoc and truoc[3] == sp and a - truoc[1] < khe and b - truoc[0] <= dai_nhat
            gan_sau = sau and sau[3] == sp and sau[0] - b < khe and sau[1] - a <= dai_nhat
            # chỉ 1 chữ (vd "关" của "关注"): gần như luôn là nửa đầu của từ ở câu sau -> ưu tiên gộp về sau
            mot_chu_ve_sau = so_chu(chu) <= 1 and sau and sau[3] == sp and sau[0] - b < 2.0 and sau[1] - a <= dai_nhat
            if mot_chu_ve_sau or (gan_sau and (not gan_truoc or sau[0] - b <= a - truoc[1])):
                sau[0], sau[2] = a, (chu + sau[2]) if so_chu(chu) <= it_chu else f"{chu} {sau[2]}"
            elif gan_truoc:
                truoc[1], truoc[2] = b, f"{truoc[2]} {chu}"
            else:
                continue
            del cau[n]
            doi = True
            break

    ra.write_text("\n\n".join(f"{n}\n{tg(a)} --> {tg(b)}\n{chu}" for n, (a, b, chu, _) in enumerate(cau, 1)) + "\n",
                  encoding="utf-8")
    return [c[3] for c in cau]


def luu_va_dong_textedit(srt: Path):
    """Lưu và đóng file phụ đề đang mở trong TextEdit (nếu có)."""
    script = f'''
    tell application "TextEdit"
        repeat with d in (every document)
            try
                if (path of d) is {_as(str(srt))} then
                    save d
                    close d saving no
                end if
            end try
        end repeat
    end tell'''
    subprocess.run(["osascript", "-e", script], capture_output=True, text=True)


def dat_cau_noi_ai33():
    """Chỉ pyVideoTrans gửi từng câu tới cầu nối ai33 trong hang_doi.py."""
    f = PVT / "videotrans/params.json"
    try:
        p = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        p = {}
    url = f"http://127.0.0.1:{CONG_HANG_DOI}/tts_ai33"
    if p.get("ttsapi_url") != url:
        p["ttsapi_url"] = url
        f.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")


def bao_loi(kq):
    log = kq.stdout + kq.stderr
    if "No human voice detected" in log:
        print("  ✖ Video không có giọng người nói (chỉ có nhạc nền), nên không có gì để dịch/lồng tiếng.")
        return
    print("  ✖ Lỗi khi dịch. 20 dòng log cuối:")
    print("\n".join((kq.stdout + kq.stderr).splitlines()[-20:]))


def dich(video: Path, lc: dict) -> bool:
    print(f"\n==============================\n▶ Đang dịch: {video.name}")
    lang = nhan_dien_ngon_ngu(video)
    print(f"  Ngôn ngữ gốc: {lang}")
    if lang == NGON_NGU_DICH:
        print("  Video đã là tiếng Việt, bỏ qua.")
        return False

    tts_type, giong = danh_sach_giong()[lc["giong"]]
    dich_bang = CACH_DICH.get(lc.get("dich"), "0")
    toc_do = TOC_DO.get(lc["toc_do"], "+0%")
    tam = RA / f".tam_{video.stem}"
    shutil.rmtree(tam, ignore_errors=True)
    srt = tam / f"{NGON_NGU_DICH}.srt"
    # Kiểu phụ đề pyVideoTrans tự gắn: chỉ gắn khi chọn "phụ đề thường"
    kieu_pd = KIEU_PHU_DE if lc.get("phu_de") == PD_THUONG else "0"

    if lc["sua"] == SUA_CO:
        # Bước 1: chỉ nhận dạng + dịch ra phụ đề
        print("  Bước 1/2: nhận dạng giọng nói và dịch ra phụ đề...")
        kq = chay_pvt(video, lang, tam, tts_type, "No", toc_do, "0", xoa_cache=True, dich=dich_bang)
        if kq.returncode != 0 or not srt.exists():
            bao_loi(kq)
            return False
        print(f"  Mở phụ đề để sửa: {srt}")
        ban_dau = srt.read_text(encoding="utf-8", errors="ignore")
        subprocess.run(["open", "-a", "TextEdit", str(srt)])
        while True:
            nut = hop_thoai(
                f"Đang sửa phụ đề cho: {video.name}\n\n"
                "• Sửa chữ trong cửa sổ TextEdit.\n"
                "• Chỉ sửa dòng chữ, KHÔNG sửa số thứ tự và dòng thời gian (00:00:01,000 --> ...).\n"
                "• Sửa xong bấm \"Tiếp tục\" (app tự lưu giúp bạn).",
                ["Bỏ qua video này", "Tiếp tục"])
            if nut != "Tiếp tục":
                luu_va_dong_textedit(srt)
                print("  Đã bỏ qua video này.")
                shutil.rmtree(tam, ignore_errors=True)
                return False
            luu_va_dong_textedit(srt)
            if srt.read_text(encoding="utf-8", errors="ignore") != ban_dau:
                print("  Đã nhận phụ đề bạn sửa.")
                break
            nut = hop_thoai("Phụ đề chưa có thay đổi nào.\n\nVẫn lồng tiếng theo bản dịch gốc?",
                            ["Quay lại sửa", "Vẫn tiếp tục"])
            if nut == "Vẫn tiếp tục":
                break
            subprocess.run(["open", "-a", "TextEdit", str(srt)])
        # Bước 2: lồng tiếng + ghép video theo phụ đề đã sửa
        if giong != "No" or kieu_pd != "0":
            print("  Bước 2/2: lồng tiếng và ghép video theo phụ đề đã sửa... (mất 1-3 phút, cứ để máy chạy)")
            kq = chay_pvt(video, lang, tam, tts_type, giong, toc_do, kieu_pd, xoa_cache=False, dich=dich_bang)
    else:
        kq = chay_pvt(video, lang, tam, tts_type, giong, toc_do, kieu_pd, xoa_cache=True, dich=dich_bang)

    if kq.returncode != 0 or not srt.exists():
        bao_loi(kq)
        return False
    video_ra = next((p for p in tam.glob("*") if p.suffix.lower() in DUOI_VIDEO), None)
    if video_ra is None:
        if giong != "No":
            bao_loi(kq)
            return False
        video_ra = video  # không lồng tiếng: dùng luôn video gốc

    if la_kieu_che(lc.get("phu_de")):
        try:
            da_che = tam / f"che_{video.stem}.mp4"
            subprocess.run([str(PY_TOOL), "-X", "utf8", "-I", str(GOC / "che_chu.py"),
                            str(video_ra), str(srt), str(da_che), kieu_che(lc.get("phu_de"))], check=True)
            video_ra = da_che
        except Exception as e:
            print(f"  ✖ Lỗi khi che chữ gốc: {e}")
            return False
    elif video_ra == video:
        shutil.copy2(video, tam / f"goc_{video.name}")
        video_ra = tam / f"goc_{video.name}"

    # Không ghi đè: nếu trùng tên thì thêm số (2), (3)...
    ten = f"{video.stem}_vi"
    so = 2
    while (RA / f"{ten}{video_ra.suffix}").exists() or (RA / f"{ten}.srt").exists():
        ten = f"{video.stem}_vi ({so})"
        so += 1
    dich_den = RA / f"{ten}{video_ra.suffix}"
    shutil.move(str(video_ra), dich_den)
    if srt.exists():
        shutil.move(str(srt), RA / f"{ten}.srt")
    shutil.rmtree(tam, ignore_errors=True)
    print(f"  ✔ Xong: {dich_den}")
    return True


# ---------- Tải video qua trang SaveTik ----------
TRANG_TAI = "https://savetik.io/vi/douyin-video-downloader"
DOWNLOADS = Path.home() / "Downloads"
CHO_TOI_DA = 600  # giây chờ bạn bấm tải


def loc_link(chu: str) -> list:
    """Lọc link từ đoạn chia sẻ Douyin (có lẫn chữ Trung)."""
    import re
    ds = []
    for l in re.findall(r"https?://[^\s，。！？、\"'<>]+", chu):
        l = l.rstrip(".,;:)]}")
        if l not in ds:
            ds.append(l)
    return ds


def cho_tai_ve(link: str):
    """Chép link vào clipboard, mở trang SaveTik, chờ file video mới xuất hiện trong Downloads."""
    import time
    co_san = {p.name for p in DOWNLOADS.iterdir()}
    chep(link)
    mo(TRANG_TAI)
    print("  Đã chép link và mở trang SaveTik.")
    print("  → Trên trang: bấm vào ô nhập, Cmd+V để dán, bấm \"Tải xuống\", rồi chọn tải video (MP4 HD).")
    print("  Đang chờ video tải về thư mục Downloads...", flush=True)
    bat_dau = time.time()
    while time.time() - bat_dau < CHO_TOI_DA:
        time.sleep(2)
        moi = [p for p in DOWNLOADS.iterdir()
               if p.name not in co_san and p.suffix.lower() in DUOI_VIDEO]
        for p in moi:
            # chờ tải xong: kích thước không đổi trong 3 giây
            try:
                s1 = p.stat().st_size
                time.sleep(3)
                if p.exists() and p.stat().st_size == s1 and s1 > 0:
                    return p
            except FileNotFoundError:
                pass
    return None


def main():
    VAO.mkdir(exist_ok=True)
    RA.mkdir(exist_ok=True)
    args = sys.argv[1:]
    link = ""
    if args and args[0] == "--link":
        link = " ".join(args[1:])
        ds = []
    elif args:
        ds = [Path(p) for p in args]
    else:
        ds = sorted(VAO.iterdir())
    ds = [p for p in ds if p.is_file() and p.suffix.lower() in DUOI_VIDEO]
    if not ds and not link:
        print("Không có video nào. Hãy kéo video vào app, dán link, hoặc bỏ video vào thư mục Video_Vao.")
        return

    lc = hoi_lua_chon()
    if lc is None:
        print("Đã huỷ.")
        return
    print(f"Giọng: {lc['giong']} | Tốc độ: {lc['toc_do']} | Phụ đề: {lc['phu_de']} | "
          f"Sửa phụ đề: {'có' if lc['sua'] == SUA_CO else 'không'}")

    if link:
        links = loc_link(link)
        if not links:
            hop_thoai("Không tìm thấy link nào trong nội dung đã dán.", ["OK"])
            return
        print("\n==============================\n▶ Tự tải video từ link...")
        p = subprocess.Popen([str(PY_TOOL), "-X", "utf8", "-I", str(GOC / "tai_douyin.py"),
                              str(VAO / "Tai_ve"), " ".join(links)],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        loi = []
        for dong in p.stdout:
            if dong.startswith("FILE:"):
                ds.append(Path(dong[5:].strip()))
            elif dong.startswith("LOI:"):
                loi.append(dong[4:].strip())
            else:
                print(dong, end="")
        p.wait()
        # Link nào tự tải lỗi thì mở trang SaveTik cho bạn tải tay
        for i, l in enumerate(loi, 1):
            print(f"\n▶ Tải tay [{i}/{len(loi)}]: {l}")
            f = cho_tai_ve(l)
            if f:
                print(f"  ✔ Đã tải: {f.name}")
                ds.append(f)
            else:
                print("  ✖ Không thấy video tải về, bỏ qua link này.")
        if not ds:
            hop_thoai("Không có video nào được tải về.", ["OK"])
            return

    xong = 0
    for i, v in enumerate(ds, 1):
        print(f"\n[{i}/{len(ds)}]", end="")
        if dich(v, lc):
            xong += 1
            # video lấy từ Video_Vao thì chuyển sang Da_Dich để không dịch lại
            if v.parent == VAO:
                (VAO / "Da_Dich").mkdir(exist_ok=True)
                shutil.move(str(v), VAO / "Da_Dich" / v.name)

    print(f"\n==============================\nHoàn tất {xong}/{len(ds)} video. Kết quả ở: {RA}")
    mo(RA)
    hop_thoai(f"Đã xong {xong}/{len(ds)} video.\nVideo nằm trong thư mục Video_Ra.", ["OK"])


if __name__ == "__main__":
    main()
