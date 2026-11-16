"""Giao diện hàng chờ dịch video (mở trên trình duyệt: http://127.0.0.1:8765).

- Dán nhiều link / thêm file bất cứ lúc nào, các video khác vẫn chạy.
- Tải video chạy song song với dịch; dịch lần lượt từng video (cho máy khỏi quá tải).
- Video chọn "sửa phụ đề" sẽ dừng chờ bạn sửa trên giao diện, video khác vẫn chạy tiếp.

Chạy:  pyvideotrans/.venv/bin/python hang_doi.py   (Windows: pyvideotrans\\.venv\\Scripts\\python.exe hang_doi.py)
"""
import json
import re
import shutil
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import ai33
import deepseek_cfg
import auto_dich as a

CONG = 8765
GOC = a.GOC
FILE_HANG_DOI = GOC / ".hang_doi.json"
HTML = GOC / "giao_dien.html"

khoa = threading.Lock()
co_viec = threading.Condition(khoa)
jobs: list = []

# Trạng thái: cho_tai, dang_tai, cho_dich, dang_dich, cho_sua, cho_long_tieng, xong, loi
DANG_CHAY = {"dang_tai", "dang_dich"}


# ---------- Lưu / đọc hàng chờ ----------
def luu():
    try:
        FILE_HANG_DOI.write_text(json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def doc():
    global jobs
    try:
        jobs = json.loads(FILE_HANG_DOI.read_text(encoding="utf-8"))
    except Exception:
        jobs = []
    for j in jobs:  # app bị tắt giữa chừng -> chạy lại bước đó
        if j["trang_thai"] == "dang_tai":
            j["trang_thai"] = "cho_tai"
        elif j["trang_thai"] == "dang_tai_tay":
            j["trang_thai"] = "cho_tai_tay"
        elif j["trang_thai"] == "dang_dich":
            j["trang_thai"] = "cho_long_tieng" if j.get("da_sua") else "cho_dich"
        j["buoc"] = ""


def tim(jid):
    return next((j for j in jobs if j["id"] == jid), None)


# ---------- Ước tính % cho các bước không tự báo tiến độ (nghe, dịch, lồng tiếng của pyVideoTrans) ----------
FILE_TOC_DO = GOC / ".toc_do_buoc.json"     # bước -> số giây xử lý cho mỗi giây video (học từ các video đã làm)
TOC_DO_BAN_DAU = {"Nhận dạng giọng nói & dịch phụ đề...": 0.6, "Lồng tiếng & ghép video...": 2.0,
                  "Nhận dạng, dịch, lồng tiếng...": 2.6, "Nhận diện ngôn ngữ...": 0.1}


def _doc_toc_do() -> dict:
    try:
        return {**TOC_DO_BAN_DAU, **json.loads(FILE_TOC_DO.read_text(encoding="utf-8"))}
    except Exception:
        return dict(TOC_DO_BAN_DAU)


def _ghi_toc_do(buoc, giay, dai):
    if not buoc or dai <= 0 or giay < 3:
        return
    d = _doc_toc_do()
    moi = giay / max(dai, 15)
    d[buoc] = round(0.5 * d[buoc] + 0.5 * moi, 3) if buoc in d else round(moi, 3)
    try:
        FILE_TOC_DO.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def uoc_tinh(j) -> str:
    """'≈40% · còn ~3 phút' cho bước đang chạy, dựa trên tốc độ các video trước."""
    toc = _doc_toc_do().get(j.get("buoc", ""))
    if not toc or not j.get("dai") or not j.get("buoc_bd"):
        return ""
    can = toc * max(j["dai"], 15)
    da = time.time() - j["buoc_bd"]
    pt = min(95, int(100 * da / can))
    con = max(0, can - da)
    chu = f"≈{pt}%"
    if pt < 95:
        chu += f" · còn ~{int(con // 60)} phút" if con >= 90 else f" · còn ~{int(con)} giây"
    return chu


def do_dai(video) -> float:
    try:
        ffprobe = str(Path(a.FFMPEG).with_name("ffprobe.exe" if a.WIN else "ffprobe"))
        r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                           capture_output=True, text=True)
        return float(r.stdout.strip() or 0)
    except Exception:
        return 0.0


def cap_nhat(j, **kw):
    with khoa:
        if j.get("huy") and kw.get("trang_thai") not in (None, "da_dung"):
            # video đã bị dừng: không cho bước đang chạy dở ghi đè trạng thái
            kw.pop("trang_thai")
            kw.pop("loi", None)
        if "buoc" in kw and kw["buoc"] != j.get("buoc"):
            # bước cũ xong (không lỗi) -> học tốc độ của nó; bắt đầu tính giờ bước mới
            if j.get("buoc") and j.get("buoc_bd") and kw.get("trang_thai") not in ("loi", "da_dung"):
                _ghi_toc_do(j["buoc"], time.time() - j["buoc_bd"], j.get("dai") or 0)
            kw["buoc_bd"] = time.time()
        j.update(kw)
        j["cap_nhat"] = time.time()
        luu()
        co_viec.notify_all()


def tao_job(nguon: str, lc: dict, video: str = "", ten: str = "", chu_de: str = "") -> dict:
    j = {
        "id": uuid.uuid4().hex[:8], "nguon": nguon, "ten": ten or nguon, "lc": lc,
        "video": video, "trang_thai": "cho_dich" if video else "cho_tai",
        "buoc": "", "lang": "", "ket_qua": "", "loi": "", "da_sua": False, "canh_bao": "",
        "tao_luc": time.time(), "cap_nhat": time.time(), "bat_dau": 0, "chu_de": chu_de,
    }
    jobs.append(j)
    return j


# ---------- Chạy tiến trình con (dừng được) ----------
tien_trinh = {}  # id video -> tiến trình đang chạy


class DaDung(Exception):
    pass


def file_tien_do(j) -> Path:
    return a.RA / f".tien_do_{j['id']}.txt"


def chay_cho(j):
    """Trả về hàm giống subprocess.run nhưng ghi nhớ tiến trình để nút Dừng tắt được."""
    def chay(cmd, **kw):
        if j.get("huy"):
            raise DaDung()
        cap = kw.pop("capture_output", False)
        kw.pop("check", None)
        if kw.get("text"):    # luôn đọc kết quả theo UTF-8 (Windows mặc định bảng mã cũ -> lỗi chữ Việt/Trung)
            kw.setdefault("encoding", "utf-8")
            kw.setdefault("errors", "replace")
        if not a.WIN:
            kw["start_new_session"] = True   # gom tiến trình con thành 1 nhóm để Dừng tắt được hết
        import os
        td = file_tien_do(j)
        td.unlink(missing_ok=True)
        kw["env"] = {**(kw.get("env") or os.environ), "TIEN_DO": str(td)}   # bước nào biết % thì ghi vào đây
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE if cap else None,
                             stderr=subprocess.PIPE if cap else None, **kw)
        tien_trinh[j["id"]] = p
        try:
            out, err = p.communicate()
        finally:
            tien_trinh.pop(j["id"], None)
            td.unlink(missing_ok=True)
        if j.get("huy"):
            raise DaDung()
        return subprocess.CompletedProcess(cmd, p.returncode, out, err)
    return chay


def dung_tien_trinh(jid):
    import os
    import signal
    p = tien_trinh.get(jid)
    if not p:
        return
    if a.WIN:   # Windows: tắt cả cây tiến trình con
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
        return
    try:
        os.killpg(p.pid, signal.SIGTERM)
    except Exception:
        pass

    def chac_chan():
        time.sleep(3)
        if p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except Exception:
                pass
    threading.Thread(target=chac_chan, daemon=True).start()


# ---------- Luồng tải video ----------
def luong_tai():
    while True:
        with khoa:
            j = next((x for x in jobs if x["trang_thai"] == "cho_tai"), None)
            if j is None:
                co_viec.wait(timeout=5)
                continue
            j["trang_thai"], j["buoc"], j["bat_dau"] = "dang_tai", "Đang tải video...", time.time()
            luu()
        f, p = "", None
        try:
            for lan in range(3):     # mạng chập chờn -> tự thử lại 2 lần trước khi nhờ tải tay
                if lan:
                    cap_nhat(j, buoc=f"Tải lỗi, đang thử lại lần {lan + 1}/3...")
                    time.sleep(15)
                p = chay_cho(j)([str(a.PY_TOOL), "-X", "utf8", "-I", str(GOC / "tai_douyin.py"),
                                 str(a.VAO / "Tai_ve"), j["nguon"]], capture_output=True, text=True)
                f = next((l[5:].strip() for l in (p.stdout or "").splitlines() if l.startswith("FILE:")), "")
                if f and Path(f).exists():
                    break
        except DaDung:
            continue
        except Exception as e:      # không chạy được chương trình tải (vd thiếu Python) -> báo rõ, không chết luồng
            p = subprocess.CompletedProcess([], 1, "", f"Lỗi chạy chương trình tải: {e}")
        if f and Path(f).exists():
            cap_nhat(j, video=f, ten=Path(f).name, trang_thai="cho_dich", buoc="")
        else:
            # ghi đúng lý do thật (SaveTik vì sao lỗi, yt-dlp vì sao lỗi, hoặc chương trình bị lỗi)
            dong = (p.stdout or "").splitlines() if p else []
            ly_do = [l.strip().replace("SaveTik lỗi (", "SaveTik: ").replace("), thử yt-dlp...", "")
                     for l in dong if "SaveTik lỗi (" in l]
            ly_do += [l.strip(" ✖").replace("Không tải được: ", "") for l in dong if "Không tải được" in l]
            if not ly_do and p is not None and p.stderr:
                ly_do = [p.stderr.strip().splitlines()[-1][:200]]
            cap_nhat(j, trang_thai="cho_tai_tay", buoc="",
                     loi="Tự tải không được: " + (" | ".join(ly_do) or "không rõ lý do") +
                         ". Kiểm tra mạng / thử lại sau, hoặc tải tay qua Seekin.")


# ---------- Tải tay qua trang web (Seekin) ----------
TRANG_TAI_TAY = "https://www.seekin.ai/vi/douyin-downloader/"
DOWNLOADS = Path.home() / "Downloads"


def luong_nhan_file():
    """Video 'đang chờ tải tay': thấy file video mới trong Downloads thì gắn vào và dịch tiếp."""
    da_thay = {}
    while True:
        time.sleep(2)
        with khoa:
            cho = sorted((x for x in jobs if x["trang_thai"] == "dang_tai_tay"), key=lambda x: x["bat_dau"])
        if not cho:
            continue
        try:
            moi = [f for f in DOWNLOADS.iterdir() if f.is_file() and f.suffix.lower() in a.DUOI_VIDEO
                   and f.stat().st_mtime > cho[0]["bat_dau"] - 2]
        except Exception:
            continue
        dung_roi = {x.get("video") for x in jobs}
        for f in sorted(moi, key=lambda f: f.stat().st_mtime):
            if str(f) in dung_roi:
                continue
            kt = f.stat().st_size
            if da_thay.get(str(f)) != kt or kt == 0:   # còn đang tải -> đợi kích thước đứng yên
                da_thay[str(f)] = kt
                continue
            j = cho.pop(0)
            cap_nhat(j, video=str(f), ten=f.name, trang_thai="cho_dich", buoc="", loi="")
            if not cho:
                break


# ---------- Luồng dịch ----------
def mo_ta_loi(kq) -> str:
    log = (kq.stdout or "") + (kq.stderr or "")
    if "No human voice detected" in log:
        return "Video không có giọng người nói (chỉ có nhạc nền), không có gì để dịch."
    dong = [l for l in log.splitlines() if l.strip()]
    tm = [l for l in dong if l.startswith("LOI:")]          # lỗi từ bước AI viết lời thuyết minh
    if tm:
        return tm[-1][4:].strip()[:300]
    loi = [l for l in dong if "Error" in l or "error" in l or "Failed" in l]
    return (loi[-1] if loi else (dong[-1] if dong else "Lỗi không rõ"))[:300]


def thu_muc_ra(j) -> Path:
    """Video theo chủ đề -> Video_Ra/<tên chủ đề>/, còn lại -> Video_Ra/."""
    ra = a.RA / j["chu_de"] if j.get("chu_de") else a.RA
    ra.mkdir(parents=True, exist_ok=True)
    return ra


# ---------- Thư mục chủ đề: Chu_De/<chủ đề>/*.txt chứa link -> tự thêm vào hàng chờ ----------
CHU_DE = GOC / "Chu_De"
HUONG_DAN_CHU_DE = """Mỗi chủ đề là 1 thư mục con ở đây, vd:  Chu_De/My_pham/links.txt
Dán link Douyin/TikTok vào file .txt trong thư mục chủ đề (mỗi dòng 1 link, dán cả đoạn chia sẻ cũng được) rồi lưu.
Dòng bắt đầu bằng # là ghi chú, tool bỏ qua. Xem mẫu: Chu_De/Vi_du_My_pham/links.txt
Kiểu nội dung (không bắt buộc): tạo file kieu.txt trong thư mục chủ đề, ghi 1 trong:
  ban hang / huong dan / giai tri / kien thuc
-> AI viết lời, câu mở đầu, từ khoá theo kiểu đó. Không có file thì AI tự nhận ra từng video.
Tool tự thấy link mới sau ~15 giây, xử lý lần lượt, video xong nằm ở Video_Ra/<tên chủ đề>/.
Link đã thêm được ghi vào .da_them.txt trong thư mục chủ đề (xoá dòng trong đó nếu muốn làm lại link đó).
"""


def kieu_chu_de(j):
    """Kiểu nội dung ghi sẵn cho thư mục chủ đề (Chu_De/<chủ đề>/kieu.txt). Không có -> AI tự nhận ra."""
    if not j.get("chu_de"):
        return None
    try:
        import viet_lai
        return viet_lai.doc_kieu((CHU_DE / j["chu_de"] / "kieu.txt").read_text(encoding="utf-8"))
    except Exception:
        return None


def ghi_kieu(j, tam):
    """Hiện kiểu video AI đã nhận ra (bán hàng / hướng dẫn...) trên hàng chờ."""
    try:
        d = json.loads((tam / "viet_lai.json").read_text(encoding="utf-8"))
        if d.get("ten_kieu"):
            cap_nhat(j, kieu_nd=d["ten_kieu"])
    except Exception:
        pass


def quet_chu_de() -> int:
    CHU_DE.mkdir(exist_ok=True)
    hd = CHU_DE / "HUONG_DAN.txt"
    if not hd.exists():
        hd.write_text(HUONG_DAN_CHU_DE, encoding="utf-8")
    them = 0
    for td in sorted((p for p in CHU_DE.iterdir() if p.is_dir() and not p.name.startswith(".")),
                     key=lambda p: p.name.lower()):
        da = td / ".da_them.txt"
        cu = set(da.read_text(encoding="utf-8", errors="ignore").split()) if da.exists() else set()
        links = []
        for f in sorted(list(td.glob("*.txt")) + list(td.glob("*.rtf"))):
            if f.name.startswith("."):
                continue
            chu = "\n".join(d for d in f.read_text(encoding="utf-8", errors="ignore").splitlines()
                            if not d.lstrip().startswith("#"))       # dòng bắt đầu bằng # = ghi chú, bỏ qua
            for l in a.loc_link(chu):
                l = l.rstrip("\\}")
                if l not in cu and l not in links:
                    links.append(l)
        if not links:
            continue
        lc = lua_chon_mac_dinh()
        with khoa:
            for l in links:
                tao_job(l, dict(lc), chu_de=td.name)
            luu()
            co_viec.notify_all()
        with open(da, "a", encoding="utf-8") as g:
            g.write("\n".join(links) + "\n")
        them += len(links)
    return them


def luong_chu_de():
    while True:
        try:
            quet_chu_de()
        except Exception:
            pass
        time.sleep(15)


def lam_net_neu_can(j, chay) -> Path:
    """Video mờ (dưới 1080p) -> AI làm nét trước khi dịch. Trả về video sẽ dùng cho các bước sau."""
    goc = Path(j["video"])
    if j["lc"].get("lam_net", a.NET_CO) != a.NET_CO:
        return goc
    if j.get("video_net") and Path(j["video_net"]).exists():
        return Path(j["video_net"])
    net = goc.parent / ".lam_net" / f"{goc.stem}_net.mp4"     # thư mục ẩn, không lẫn với video vào
    net.parent.mkdir(exist_ok=True)
    if not (GOC / "mo_hinh" / "realesr-general-x4v3.pth").exists():
        return goc
    try:   # đo kích thước bằng ffprobe (server không chạy cùng môi trường với AI)
        ffprobe = str(Path(a.FFMPEG).with_name("ffprobe.exe" if a.WIN else "ffprobe"))
        r = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(goc)], capture_output=True, text=True)
        w, h = (int(x) for x in r.stdout.strip().split("\n")[0].split(",")[:2])
        if min(w, h) >= 1080 * 0.95:
            return goc       # đã đủ nét
    except Exception:
        return goc
    cap_nhat(j, buoc="AI làm nét video (video mờ)...")
    r = chay([str(a.PY_TOOL), "-X", "utf8", "-I", str(GOC / "lam_net.py"), str(goc), str(net)], capture_output=True, text=True)
    if r.returncode == 0 and net.exists() and net.stat().st_size > 0:
        cap_nhat(j, video_net=str(net))
        return net
    return goc       # làm nét lỗi -> dùng video gốc, vẫn dịch bình thường


def xu_ly(j):
    lc = j["lc"]
    video = Path(j["video"])
    tam = a.RA / f".tam_{j['id']}"
    srt = tam / f"{a.NGON_NGU_DICH}.srt"
    tts_type, giong = a.danh_sach_giong().get(lc["giong"], ("0", "vi-VN-HoaiMyNeural"))
    toc_do = a.TOC_DO.get(lc.get("toc_do"), "+0%")
    kieu_pd = a.KIEU_PHU_DE if lc.get("phu_de") == a.PD_THUONG else "0"
    sua = lc.get("sua") == a.SUA_CO
    dich = a.CACH_DICH.get(lc.get("dich"), "0")
    tach = lc.get("am_thanh", a.AM_GIU) == a.AM_GIU      # giữ nhạc nền & hiệu ứng
    chay = chay_cho(j)
    # video 2 người nói: giọng thứ 2 (phải cùng loại giọng với giọng chính, vd cùng ai33 hoặc cùng Edge)
    ds_giong = a.danh_sach_giong()
    hai = None
    g2 = lc.get("giong_2")
    if g2 and g2 in ds_giong and g2 != lc.get("giong") and giong != "No":
        t2, v2 = ds_giong[g2]
        if t2 == tts_type:
            hai = {"tts": t2, "giong": v2, "ten1": lc.get("giong", ""), "ten2": g2}
        else:
            cap_nhat(j, canh_bao="Giọng người thứ 2 phải cùng loại với giọng chính (cùng ai33 hoặc cùng Edge) - dùng 1 giọng.")
    if not j.get("dai"):
        cap_nhat(j, dai=do_dai(video))
    ten_goc = video.stem
    video = lam_net_neu_can(j, chay)
    # video không có lời nói -> AI xem hình viết lời thuyết minh
    viet_loi = None if lc.get("thuyet_minh") == a.TM_KHONG else a.ham_viet_loi(video, chay)

    if not j["lang"]:
        cap_nhat(j, buoc="Nhận diện ngôn ngữ...")
        lang = a.nhan_dien_ngon_ngu(video, chay=chay)
        cap_nhat(j, lang=lang)
    lang = j["lang"]
    if lang == a.NGON_NGU_DICH:
        return cap_nhat(j, trang_thai="loi", loi="Video đã là tiếng Việt.", buoc="")

    kq = None
    goc_srt = tam / f"{lang}.srt"
    if j["trang_thai"] == "dang_dich" and not j["da_sua"]:
        shutil.rmtree(tam, ignore_errors=True)
        if sua:
            cap_nhat(j, buoc="Nhận dạng giọng nói & dịch phụ đề...")
            kq = a.chay_pvt(video, lang, tam, tts_type, "No", toc_do, "0", xoa_cache=True, dich=dich, chay=chay, hai_giong=hai,
                            tach_giong=tach, viet_loi=viet_loi, kieu=kieu_chu_de(j))
            ghi_kieu(j, tam)
            if kq.returncode != 0 or not srt.exists():
                return cap_nhat(j, trang_thai="loi", loi=mo_ta_loi(kq), buoc="")
            return cap_nhat(j, trang_thai="cho_sua", buoc="Chờ bạn sửa phụ đề", gia=a.gia_tien.cau_co_gia(srt, goc_srt))
        # dịch trước, chưa lồng tiếng: có câu nói giá -> dừng lại cho bạn kiểm tra
        cap_nhat(j, buoc="Nhận dạng giọng nói & dịch phụ đề...")
        kq = a.chay_pvt(video, lang, tam, tts_type, giong, toc_do, kieu_pd, xoa_cache=True, dich=dich, chay=chay, hai_giong=hai,
                        tach_giong=tach, viet_loi=viet_loi, chi_dich=True, kieu=kieu_chu_de(j))
        ghi_kieu(j, tam)
        if kq.returncode != 0:
            return cap_nhat(j, trang_thai="loi", loi=mo_ta_loi(kq), buoc="")
        gia = a.gia_tien.cau_co_gia(srt, goc_srt) if srt.exists() else []
        if gia and lc.get("sua", a.SUA_GIA) == a.SUA_GIA:
            return cap_nhat(j, trang_thai="cho_sua", gia=gia, buoc="")
        cap_nhat(j, buoc="Lồng tiếng & ghép video...")
        kq = a.chay_pvt(video, lang, tam, tts_type, giong, toc_do, kieu_pd, xoa_cache=False, dich=dich, chay=chay, hai_giong=hai,
                        tach_giong=tach)
    elif giong != "No" or kieu_pd != "0":
        cap_nhat(j, buoc="Lồng tiếng & ghép video...")
        kq = a.chay_pvt(video, lang, tam, tts_type, giong, toc_do, kieu_pd, xoa_cache=False, dich=dich, chay=chay, hai_giong=hai, tach_giong=tach)

    if (kq is not None and kq.returncode != 0) or not srt.exists():
        return cap_nhat(j, trang_thai="loi", loi=mo_ta_loi(kq) if kq else "Thiếu file phụ đề.", buoc="")
    try:   # nhớ giọng từng câu (để "đọc lại câu câm" dùng đúng giọng) + ghi chú 1 hay 2 người nói
        if (tam / "hai_giong.json").exists():
            cap_nhat(j, ghi_chu_giong=json.loads((tam / "hai_giong.json").read_text(encoding="utf-8"))["ghi_chu"])
        cap_nhat(j, vai=json.loads((tam / "vai.json").read_text(encoding="utf-8")) if (tam / "vai.json").exists() else {})
    except Exception:
        pass
    video_ra = next((p for p in tam.glob("*") if p.suffix.lower() in a.DUOI_VIDEO), None)
    if video_ra is None:
        if giong != "No":
            return cap_nhat(j, trang_thai="loi", loi=mo_ta_loi(kq) if kq else "Không có video ra.", buoc="")
        video_ra = video

    hieu_ung = tam / "hieu_ung.json"     # do thuyet_minh.py ghi ra (chỉ có ở video không lời)
    if a.la_kieu_che(lc.get("phu_de")):
        kc = a.kieu_che(lc.get("phu_de"))
        cap_nhat(j, buoc={"ai": "AI xoá chữ gốc & gắn phụ đề Việt...", "ai_trong": "AI xoá chữ gốc (không gắn phụ đề)..."}
                 .get(kc, "Che chữ gốc & gắn phụ đề Việt..."))
        da_che = tam / f"che_{j['id']}.mp4"
        # video không lời có thuyết minh AI -> thêm zoom ở điểm nhấn (chỉ kiểu AI xoá chữ)
        hu = [str(hieu_ung)] if kc in ("ai", "ai_trong") and hieu_ung.exists() else []
        r = chay([str(a.PY_TOOL), "-X", "utf8", "-I", str(GOC / "che_chu.py"),
                            str(video_ra), str(srt), str(da_che), kc, *hu], capture_output=True, text=True)
        if r.returncode != 0 or not da_che.exists():
            return cap_nhat(j, trang_thai="loi", loi="Lỗi khi che chữ gốc: " + (r.stderr or r.stdout)[-200:], buoc="")
        video_ra = da_che
    elif lc.get("phu_de") == a.PD_KHONG and hieu_ung.exists() and video_ra != video:
        cap_nhat(j, buoc="Thêm hiệu ứng zoom chậm...")
        da_zoom = tam / f"zoom_{j['id']}.mp4"
        r = chay([str(a.PY_TOOL), "-X", "utf8", "-I", str(GOC / "hieu_ung.py"), str(video_ra), str(hieu_ung), str(da_zoom)],
                 capture_output=True, text=True)
        if r.returncode == 0 and da_zoom.exists():
            video_ra = da_zoom
    elif video_ra == video:
        shutil.copy2(video, tam / f"goc_{video.name}")
        video_ra = tam / f"goc_{video.name}"

    ra = thu_muc_ra(j)
    ten = f"{ten_goc}_vi"
    so = 2
    while (ra / f"{ten}{video_ra.suffix}").exists() or (ra / f"{ten}.srt").exists():
        ten = f"{ten_goc}_vi ({so})"
        so += 1
    dich_den = ra / f"{ten}{video_ra.suffix}"
    shutil.move(str(video_ra), dich_den)
    shutil.move(str(srt), ra / f"{ten}.srt")
    shutil.rmtree(tam, ignore_errors=True)
    cap_nhat(j, ket_qua=str(dich_den), canh_bao="", da_va="")
    if giong != "No":
        # Tự kiểm tra câu câm và tự vá (tối đa 2 lần) - áp dụng cho mọi video
        for _ in range(2):
            if not cau_bi_cam(dich_den, ra / f"{ten}.srt"):
                break
            va_cau_cam(j, tu_dong=True)
            if not j.get("canh_bao", "").startswith("Vẫn còn"):
                break
    cap_nhat(j, trang_thai="xong", buoc="", va_cau=False)


def cau_bi_cam(video: Path, srt: Path) -> list:
    """Đo âm lượng từng câu phụ đề trong video ra. Trả về số thứ tự các câu gần như im lặng."""
    try:
        import numpy as np
        raw = subprocess.run([a.FFMPEG, "-v", "error", "-i", str(video), "-vn",
                              "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True).stdout
        am = np.frombuffer(raw, dtype=np.int16).astype(np.float32)

        def giay(t):
            h, m, r = t.strip().split(":")
            sec, ms = r.split(",")
            return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000

        cam = []
        for n, k in enumerate(doc_srt(srt), 1):
            a1, b1 = [giay(x) for x in k["tg"].split("-->")]
            doan = am[int(a1 * 16000):int(b1 * 16000)]
            if len(doan) > 1600 and np.sqrt((doan ** 2).mean()) < 30:  # ~ -60 dBFS
                cam.append(n)
        return cam
    except Exception:
        return []


def va_cau_cam(j, tu_dong=False):
    """Chỉ lồng lại các câu bị câm và trộn vào tiếng có sẵn của video (giữ nguyên hình).

    tu_dong=True: được gọi ngay sau khi dịch xong, nên giữ trạng thái "đang dịch".
    """
    tt = "dang_dich" if tu_dong else "xong"
    video = Path(j["ket_qua"])
    srt = video.with_suffix(".srt")
    chay = chay_cho(j)
    cap_nhat(j, buoc="Tìm câu bị câm...")
    cam = cau_bi_cam(video, srt)
    if not cam:
        return cap_nhat(j, trang_thai=tt, va_cau=False, canh_bao="", buoc="")
    lc = j["lc"]
    tts_type, giong = a.danh_sach_giong().get(lc["giong"], ("0", "vi-VN-HoaiMyNeural"))
    toc_do = a.TOC_DO.get(lc.get("toc_do"), "+0%")
    if tts_type == "35":
        a.dat_cau_noi_ai33()
    khoi = doc_srt(srt)
    tam = a.RA / f".tam_{j['id']}" / "va_cau"
    shutil.rmtree(tam, ignore_errors=True)
    tam.mkdir(parents=True)
    mini = tam / "cau_cam.srt"
    ghi_srt(mini, [khoi[n - 1] for n in cam])

    cap_nhat(j, buoc=f"Đọc lại {len(cam)} câu câm...")
    env = dict(__import__("os").environ)
    env["PATH"] = a.PATH_THEM + env.get("PATH", "")
    lenh = [str(a.PY_PVT), "cli.py", "--task", "tts", "--name", str(mini), "--tts_type", tts_type,
            "--voice_role", giong, "--voice_rate", toc_do, "--voice_autorate", "--align_sub_audio",
            "--target_language_code", a.NGON_NGU_DICH, "--output-dir", str(tam / "ra")]
    if j.get("vai"):   # video 2 người nói: câu nào đọc lại bằng đúng giọng của người đó
        vai_mini = {str(i): j["vai"].get(str(n), giong) for i, n in enumerate(cam, 1)}
        (tam / "vai.json").write_text(json.dumps(vai_mini, ensure_ascii=False), encoding="utf-8")
        lenh = [str(a.PY_PVT), str(GOC / "chay_vai.py"), str(tam / "vai.json")] + lenh[1:]
    r = chay(lenh, cwd=a.PVT, env=env, capture_output=True, text=True)
    wav = next((tam / "ra").glob("*.wav"), None) if (tam / "ra").exists() else None
    if r.returncode != 0 or wav is None:
        return cap_nhat(j, trang_thai=tt, va_cau=False, buoc="",
                        canh_bao=f"Đọc lại câu câm không được: {mo_ta_loi(r)}")

    cap_nhat(j, buoc="Chèn tiếng vào video...")
    moi = tam / f"moi{video.suffix}"
    r = chay([a.FFMPEG, "-v", "error", "-y", "-i", str(video), "-i", str(wav),
              "-filter_complex", "[1:a]apad[p];[0:a][p]amix=inputs=2:duration=first:normalize=0[a]",
              "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
              "-movflags", "+faststart", str(moi)], capture_output=True, text=True)
    if r.returncode != 0 or not moi.exists():
        return cap_nhat(j, trang_thai=tt, va_cau=False, buoc="",
                        canh_bao="Chèn tiếng vào video không được: " + (r.stderr or "")[-200:])
    shutil.move(str(moi), video)  # thay video cũ bằng bản đã vá
    shutil.rmtree(tam.parent, ignore_errors=True)

    con = cau_bi_cam(video, srt)
    canh_bao = (f"Vẫn còn {len(con)} câu câm: câu {', '.join(map(str, con))}. Bấm \"Lồng tiếng lại\" lần nữa."
                if con else "")
    cap_nhat(j, trang_thai=tt, va_cau=False, buoc="", canh_bao=canh_bao,
             da_va=f"Đã lồng lại câu {', '.join(map(str, [n for n in cam if n not in con]))}" if len(con) < len(cam) else "")


def don_rac():
    """Dọn file tạm của pyVideoTrans: thư mục tạm > 1 giờ, tiếng đệm > 7 ngày."""
    tmp = a.PVT / "tmp"
    bay_gio = time.time()
    try:
        for d in tmp.iterdir():
            if d.name == "dubbing_cache":
                for f in d.rglob("*"):
                    if f.is_file() and bay_gio - f.stat().st_mtime > 7 * 86400:
                        f.unlink(missing_ok=True)
            elif d.is_dir() and bay_gio - d.stat().st_mtime > 3600:
                shutil.rmtree(d, ignore_errors=True)
    except Exception:
        pass


def luong_dich():
    while True:
        with khoa:
            j = next((x for x in jobs if x["trang_thai"] in ("cho_dich", "cho_long_tieng")), None)
            if j is None:
                co_viec.wait(timeout=5)
                continue
            j["trang_thai"], j["bat_dau"] = "dang_dich", time.time()
            luu()
        try:
            if j.get("va_cau"):
                va_cau_cam(j)
            else:
                xu_ly(j)
        except DaDung:
            pass
        except Exception as e:
            cap_nhat(j, trang_thai="loi", loi=f"Lỗi: {e}", buoc="")
        if j.get("huy"):
            shutil.rmtree(a.RA / f".tam_{j['id']}", ignore_errors=True)
        don_rac()


# ---------- Phụ đề ----------
def doc_srt(path: Path) -> list:
    khoi = []
    for k in re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip()):
        ls = k.strip().splitlines()
        i = next((n for n, l in enumerate(ls) if "-->" in l), None)
        if i is not None:
            khoi.append({"tg": ls[i].strip(), "chu": "\n".join(ls[i + 1:]).strip()})
    return khoi


def ghi_srt(path: Path, khoi: list):
    path.write_text("\n\n".join(f"{n}\n{k['tg']}\n{k['chu'].strip()}" for n, k in enumerate(khoi, 1)
                                if k["chu"].strip()) + "\n", encoding="utf-8")


# ---------- Máy chủ web ----------
def lua_chon_mac_dinh():
    try:
        return json.loads(a.LUA_CHON_CU.read_text())
    except Exception:
        return {"giong": list(a.GIONG)[0], "toc_do": "Bình thường", "phu_de": a.PD_XOA, "sua": a.SUA_KHONG, "lam_net": a.NET_CO, "giong_2": a.GIONG2_KHONG}


class XuLy(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def gui(self, data, code=200, kieu="application/json"):
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", kieu + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def doc_json(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/":
            return self.gui(HTML.read_bytes(), kieu="text/html")
        if u.path == "/api/ping":
            return self.gui({"ok": True})
        if u.path == "/api/jobs":
            with khoa:
                ds = []
                for j in jobs:
                    if j["trang_thai"] in DANG_CHAY:
                        try:
                            j = {**j, "tien_do": file_tien_do(j).read_text(encoding="utf-8")}
                        except OSError:
                            j = {**j, "tien_do": uoc_tinh(j)}     # bước không tự báo % -> ước tính
                    ds.append(j)
                return self.gui({"jobs": ds, "bay_gio": time.time()})
        if u.path == "/api/options":
            return self.gui({"giong": list(a.danh_sach_giong()), "toc_do": list(a.TOC_DO),
                             "phu_de": [a.PD_XOA, a.PD_CHE, a.PD_XOA_TRONG, a.PD_THUONG, a.PD_KHONG],
                             "thuyet_minh": [a.TM_TU_DONG, a.TM_KHONG],
                             "lam_net": [a.NET_CO, a.NET_KHONG],
                             "giong_2": [a.GIONG2_KHONG] + [k for k, v in a.danh_sach_giong().items() if v[1] != "No"],
                             "sua": [a.SUA_KHONG, a.SUA_GIA, a.SUA_CO],
                             "dich": list(a.CACH_DICH),
                             "am_thanh": [a.AM_GIU, a.AM_BO], "mac_dinh": lua_chon_mac_dinh()})
        if u.path == "/api/ai33/status":
            if not ai33.doc_key():
                return self.gui({"co_key": False, "yeu_thich": ai33.ds_yeu_thich()})
            try:
                return self.gui({"co_key": True, "credits": ai33.so_credit(), "yeu_thich": ai33.ds_yeu_thich()})
            except Exception as e:
                return self.gui({"co_key": True, "loi": str(e), "yeu_thich": ai33.ds_yeu_thich()})
        if u.path == "/api/deepseek/status":
            return self.gui(deepseek_cfg.kiem_tra())
        if u.path == "/api/ai33/voices":
            try:
                return self.gui(ai33.tim_giong(q.get("provider", "vbee"), q.get("q", ""),
                                               int(q.get("page", 1)), q.get("vi", "1") == "1",
                                               q.get("gender", ""), int(q.get("size", 24))))
            except Exception as e:
                return self.gui({"loi": str(e)}, 400)
        if u.path == "/api/srt":
            j = tim(q.get("id"))
            srt = a.RA / f".tam_{j['id']}" / "vi.srt" if j else None
            if not srt or not srt.exists():
                return self.gui({"loi": "Không thấy phụ đề"}, 404)
            return self.gui({"khoi": doc_srt(srt), "ten": j["ten"], "gia": j.get("gia") or []})
        self.gui({"loi": "không có"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/tts_ai33":
            # Cầu nối: pyVideoTrans (Custom TTS API) gửi từng câu tới đây -> chuyển sang ai33
            n = int(self.headers.get("Content-Length", 0))
            f = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode("utf-8")).items()}
            try:
                url = ai33.doc_ra(f.get("text", ""), f.get("voice", ""), float(f.get("rate", 1) or 1))
                return self.gui({"code": 0, "msg": "ok", "data": url})
            except Exception as e:
                return self.gui({"code": 1, "msg": str(e)})
        if u.path == "/api/ai33/key":
            ai33.luu_key(self.doc_json().get("key", ""))
            try:
                return self.gui({"ok": True, "credits": ai33.so_credit()})
            except Exception as e:
                return self.gui({"ok": False, "loi": str(e)})
        if u.path == "/api/deepseek/key":
            return self.gui(deepseek_cfg.luu_key(self.doc_json().get("key", "")))
        if u.path == "/api/ai33/fav":
            d = self.doc_json()
            if d.get("bo"):
                ai33.bo_yeu_thich(d["voice_id"])
            else:
                ai33.them_yeu_thich(d["voice_id"], d.get("ten") or d["voice_id"])
            return self.gui({"ok": True})
        if u.path == "/api/lua_chon":   # lưu lựa chọn ngay khi đổi (thư mục chủ đề dùng lựa chọn này)
            lc = self.doc_json().get("lc")
            if lc:
                a.LUA_CHON_CU.write_text(json.dumps(lc, ensure_ascii=False))
            return self.gui({"ok": True})
        if u.path == "/api/add":
            d = self.doc_json()
            lc = d.get("lc") or lua_chon_mac_dinh()
            a.LUA_CHON_CU.write_text(json.dumps(lc, ensure_ascii=False))
            links = a.loc_link(d.get("text", ""))
            with khoa:
                for l in links:
                    tao_job(l, lc)
                luu()
                co_viec.notify_all()
            return self.gui({"them": len(links)})
        if u.path == "/api/add_files":  # từ app (kéo thả file vào icon)
            d = self.doc_json()
            lc = d.get("lc") or lua_chon_mac_dinh()
            n = 0
            with khoa:
                for p in d.get("paths", []):
                    if Path(p).suffix.lower() in a.DUOI_VIDEO and Path(p).exists():
                        tao_job(p, lc, video=p, ten=Path(p).name)
                        n += 1
                luu()
                co_viec.notify_all()
            return self.gui({"them": n})
        if u.path == "/api/upload":
            ten = Path(unquote(q.get("name", "video.mp4"))).name
            lc = json.loads(unquote(q.get("lc", ""))) if q.get("lc") else lua_chon_mac_dinh()
            thu_muc = a.VAO / "Tai_len"
            thu_muc.mkdir(parents=True, exist_ok=True)
            dich = thu_muc / ten
            so = 2
            while dich.exists():
                dich = thu_muc / f"{Path(ten).stem} ({so}){Path(ten).suffix}"
                so += 1
            con_lai = int(self.headers.get("Content-Length", 0))
            with dich.open("wb") as f:
                while con_lai > 0:
                    chunk = self.rfile.read(min(1 << 20, con_lai))
                    if not chunk:
                        break
                    f.write(chunk)
                    con_lai -= len(chunk)
            with khoa:
                tao_job(str(dich), lc, video=str(dich), ten=dich.name)
                luu()
                co_viec.notify_all()
            return self.gui({"ok": True})

        j = tim(q.get("id"))
        if u.path == "/api/open_folder":
            a.mo(a.RA)
            return self.gui({"ok": True})
        if u.path == "/api/open_chu_de":
            quet_chu_de()
            a.mo(CHU_DE)
            return self.gui({"ok": True})
        if j is None:
            return self.gui({"loi": "không thấy"}, 404)
        if u.path == "/api/srt":
            d = self.doc_json()
            srt = a.RA / f".tam_{j['id']}" / "vi.srt"
            ghi_srt(srt, d["khoi"])
            cap_nhat(j, trang_thai="cho_long_tieng", da_sua=True, buoc="")
            return self.gui({"ok": True})
        if u.path == "/api/tai_tay":
            a.chep(j["nguon"])
            a.mo(TRANG_TAI_TAY)
            j["huy"] = False
            cap_nhat(j, trang_thai="dang_tai_tay", bat_dau=time.time(),
                     buoc="Đã chép link. Trên trang Seekin: Cmd+V → Tải xuống. App sẽ tự nhận file.")
            return self.gui({"ok": True})
        if u.path == "/api/stop":
            if j["trang_thai"] in ("xong", "loi", "da_dung"):
                return self.gui({"ok": True})
            j["huy"] = True
            dung_tien_trinh(j["id"])
            cap_nhat(j, trang_thai="da_dung", buoc="")
            return self.gui({"ok": True})
        if u.path == "/api/redub":
            # Chỉ đọc lại các câu câm rồi chèn vào video đã có (không nghe/dịch/che chữ lại)
            kq = Path(j.get("ket_qua", ""))
            if not kq.exists() or not kq.with_suffix(".srt").exists():
                return self.gui({"loi": "Không thấy video hoặc phụ đề của video này."}, 400)
            j["huy"] = False
            cap_nhat(j, trang_thai="cho_long_tieng", va_cau=True, buoc="")
            return self.gui({"ok": True})
        if u.path == "/api/retry":
            j["huy"] = False
            # làm lại theo lựa chọn đang chọn trên giao diện (không dùng lựa chọn cũ lúc thêm video)
            lc = self.doc_json().get("lc") or lua_chon_mac_dinh()
            cap_nhat(j, trang_thai="cho_dich" if j["video"] else "cho_tai", loi="", buoc="", da_sua=False,
                     canh_bao="", lang="", gia=[], lc=lc, vai={}, ghi_chu_giong="")
            return self.gui({"ok": True})
        if u.path == "/api/delete":
            if j["trang_thai"] in DANG_CHAY:
                return self.gui({"loi": "Video đang chạy, chờ xong mới xoá được."}, 400)
            with khoa:
                jobs.remove(j)
                luu()
            shutil.rmtree(a.RA / f".tam_{j['id']}", ignore_errors=True)
            return self.gui({"ok": True})
        if u.path == "/api/open":
            if j["ket_qua"] and Path(j["ket_qua"]).exists():
                a.mo(j["ket_qua"])
            return self.gui({"ok": True})
        if u.path == "/api/reveal":
            if j["ket_qua"] and Path(j["ket_qua"]).exists():
                a.mo(j["ket_qua"], chon_trong_thu_muc=True)
            return self.gui({"ok": True})
        self.gui({"loi": "không có"}, 404)


def main():
    a.VAO.mkdir(exist_ok=True)
    a.RA.mkdir(exist_ok=True)
    doc()
    don_rac()
    threading.Thread(target=luong_tai, daemon=True).start()
    threading.Thread(target=luong_dich, daemon=True).start()
    threading.Thread(target=luong_nhan_file, daemon=True).start()
    threading.Thread(target=luong_chu_de, daemon=True).start()
    print(f"Giao diện: http://127.0.0.1:{CONG}")
    ThreadingHTTPServer(("127.0.0.1", CONG), XuLy).serve_forever()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--add-files":
        # app gọi khi bạn kéo thả file vào icon: gửi file vào hàng chờ đang chạy
        import urllib.request
        req = urllib.request.Request(
            f"http://127.0.0.1:{CONG}/api/add_files",
            data=json.dumps({"paths": sys.argv[2:]}).encode(),
            headers={"Content-Type": "application/json"})
        print(urllib.request.urlopen(req, timeout=10).read().decode())
    else:
        main()
