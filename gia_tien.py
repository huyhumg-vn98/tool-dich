"""Chuẩn hoá giá tiền / con số để giọng đọc tiếng Việt đọc đúng mệnh giá.

3 lớp, chạy tự động trong quy trình (auto_dich.chay_pvt):
1. Trước khi dịch - sửa phụ đề tiếng Trung: "九块九" -> "9.9元", "两块五" -> "2.5元", "五毛" -> "0.5元",
   "只要69.9" -> "只要69.9元", "2万" -> "20000"... để máy dịch thấy rõ số tiền + đơn vị.
2. Sau khi dịch - sửa phụ đề tiếng Việt để hiện: "nhân dân tệ/RMB/元/¥" -> "tệ", số nào là tiền ở câu gốc
   mà bản dịch quên đơn vị thì thêm "tệ", số viết kiểu Việt (69,9 / 20.000).
3. Bản cho giọng đọc: mọi con số đổi thành chữ ("69,9 tệ" -> "sáu mươi chín phẩy chín tệ") để giọng đọc
   không đọc nhầm dấu chấm/phẩy. Phụ đề hiện trên video vẫn giữ dạng số.
"""
import re
from pathlib import Path

DON_VI = "tệ"     # tên đơn vị tiền Trung Quốc khi đọc

# ===== Quy đổi sang tiền Việt (sửa ở đây) =====
QUY_DOI_VND = True        # True: đổi giá tệ -> tiền Việt; False: giữ nguyên "tệ"
TEN_NGHIN = "cành"        # 1 cành = 1 nghìn đồng (500 nghìn đồng -> "500 cành")
TY_GIA_DU_PHONG = 3846    # 1 tệ = ? đồng, dùng khi không lấy được tỷ giá mới (13/11/2026)
URL_TY_GIA = "https://open.er-api.com/v6/latest/CNY"
# ==============================================

# ---------------------------------------------------------------- đọc số tiếng Việt
CS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
NHOM = ["", "nghìn", "triệu", "tỷ", "nghìn tỷ", "triệu tỷ"]


def _doc3(n, du):
    h, t, u = n // 100, n // 10 % 10, n % 10
    w = []
    if h or du:
        w += [CS[h], "trăm"]
    if t == 0:
        if u:
            if h or du:
                w.append("linh")
            w.append(CS[u])
    elif t == 1:
        w.append("mười")
        if u:
            w.append("lăm" if u == 5 else CS[u])
    else:
        w += [CS[t], "mươi"]
        if u:
            w.append({1: "mốt", 4: "tư", 5: "lăm"}.get(u, CS[u]))
    return w


def doc_so(n: int) -> str:
    """1288 -> 'một nghìn hai trăm tám mươi tám'."""
    if n == 0:
        return "không"
    nhom = []
    while n:
        nhom.append(n % 1000)
        n //= 1000
    if len(nhom) > len(NHOM):
        return " ".join(CS[int(c)] for c in str(n))
    w = []
    for i in range(len(nhom) - 1, -1, -1):
        g = nhom[i]
        if g == 0:
            continue
        w += _doc3(g, du=bool(w))
        if NHOM[i]:
            w.append(NHOM[i])
    return " ".join(w)


def doc_so_le(nguyen: str, le: str | None) -> str:
    """('69', '9') -> 'sáu mươi chín phẩy chín'."""
    if len(nguyen) >= 9 and le is None and nguyen.startswith("0"):
        return " ".join(CS[int(c)] for c in nguyen)          # số điện thoại...
    s = doc_so(int(nguyen))
    if le:
        if le.startswith("0") or len(le) > 2:
            s += " phẩy " + " ".join(CS[int(c)] for c in le)
        else:
            s += " phẩy " + doc_so(int(le))
    return s


# ---------------------------------------------------------------- số trong câu tiếng Việt
SO_VI = re.compile(r"(?<![\w.,])(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)(?!\w)")


def tach_so(chuoi: str):
    """'1.288,5' -> ('1288', '5'); '69.9' -> ('69', '9'); '20.000' -> ('20000', None)."""
    vt = [i for i, c in enumerate(chuoi) if c in ".,"]
    if not vt:
        return chuoi, None
    loai = {chuoi[i] for i in vt}
    cuoi = vt[-1]
    sau = chuoi[cuoi + 1:]
    if len(loai) == 2:
        thap = cuoi
    elif len(vt) > 1:
        thap = None if len(sau) == 3 else cuoi
    else:
        truoc = chuoi[:cuoi]
        thap = None if (len(sau) == 3 and truoc != "0") else cuoi
    if thap is None:
        return re.sub(r"[.,]", "", chuoi), None
    return re.sub(r"[.,]", "", chuoi[:thap]), chuoi[thap + 1:]


def viet_so(nguyen: str, le: str | None) -> str:
    """Viết số kiểu Việt để hiện phụ đề: 20000 -> 20.000, 69.9 -> 69,9."""
    n = nguyen.lstrip("0") or "0"
    if len(n) >= 5:
        n = f"{int(n):,}".replace(",", ".")
    return n + ("," + le if le else "")


def _gia_tri(nguyen, le):
    return float(f"{int(nguyen)}.{le}" if le else int(nguyen))


# ---------------------------------------------------------------- 1. câu tiếng Trung
_CN_SO = "零〇一二两三四五六七八九"
_CN_DV = {"十": 10, "百": 100, "千": 1000}
_CN_LON = {"万": 10000, "亿": 100000000}
NUM_ZH = r"(?:\d+(?:\.\d+)?[万亿千]?|[一二两三四五六七八九十][零〇一二两三四五六七八九十百千万亿]*)"
_MO_DAU_GIA = r"(?:只要|只需|仅需|仅要|只卖|才|仅|原价|现价|售价|到手价?|券后价?|特价|秒杀价?|价格|卖|一共|总共|共|便宜|省)"
_LUONG_TU = "包个斤盒瓶件箱袋份杯只支条张台双套桶罐片颗块克听提根粒"


def cn_so(tok: str):
    """'一千二百八十八' -> 1288, '两万' -> 20000, '一万五' -> 15000, '1.5万' -> 15000."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([万亿千]?)", tok)
    if m:
        v = float(m.group(1)) * ({"千": 1000, **_CN_LON}.get(m.group(2), 1))
        return v
    tong = phan = so = 0
    dv_cuoi = 0
    vua_dv = False
    for ch in tok:
        if ch in _CN_SO:
            so = _cn_digit(ch)
            if ch in "零〇":
                dv_cuoi = 0
            vua_dv = False
        elif ch in _CN_DV:
            u = _CN_DV[ch]
            phan += (so or (1 if u == 10 else 0)) * u
            so, dv_cuoi, vua_dv = 0, u, True
        elif ch in _CN_LON:
            u = _CN_LON[ch]
            tong += (phan + so) * u
            phan = so = 0
            dv_cuoi, vua_dv = u, True
        else:
            return None
    if so and dv_cuoi and not vua_dv and tok[-2] not in "零〇":
        phan += so * dv_cuoi // 10          # 一万五 = 15000, 三百五 = 350
    else:
        phan += so
    return tong + phan


def _cn_digit(ch):
    if ch.isdigit():
        return int(ch)
    if ch == "两":
        return 2
    return {"零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}.get(ch)


def _fmt(v):
    v = round(v, 2)
    return str(int(v)) if v == int(v) else f"{v:.2f}".rstrip("0")


def _khoang(m, f):
    class M:
        def group(self, i):
            if i == 0:
                return m.group(0)
            if i == 4:
                return m.group(4) or m.group(5)
            return m.group(i)
    return f(M())


def chuan_hoa_goc(cau: str) -> str:
    """Câu tiếng Trung: viết rõ số tiền bằng số + '元' trước khi dịch."""
    s = re.sub(r"[¥￥]\s*(\d+(?:\.\d+)?)", r"\1元", cau)

    # khoảng giá nói tắt: 一两百 -> 100-200, 三五十块 -> 30-50块, 七八块 -> 7-8块
    def khoang(m):
        a, b = _cn_digit(m.group(1)), _cn_digit(m.group(2))
        if not (a and b and 0 < b - a <= 2):
            return m.group(0)
        u = {"十": 10, "百": 100, "千": 1000, "万": 10000}.get(m.group(3) or "", 1)
        return f"{a * u}-{b * u}{m.group(4) or ''}"
    s = re.sub(r"(?<![\d零一二两三四五六七八九十百千万])([一二两三四五六七八])([二两三四五六七八九])"
               r"(?:([十百千万])(块钱?|元)?|(块钱?|元))", lambda m: _khoang(m, khoang), s)

    def tien(m, them=""):
        v = cn_so(m.group("n"))
        return m.group(0) if v is None else f"{them}{_fmt(v)}"

    # 三十来块 -> 约30元, 三十多块 -> 30多元
    s = re.sub(rf"(?P<n>{NUM_ZH})来(?:块|元)钱?", lambda m: (lambda v: m.group(0) if v is None else f"约{_fmt(v)}元")(cn_so(m.group("n"))), s)
    s = re.sub(rf"(?P<n>{NUM_ZH})多(?:块|元)钱?", lambda m: (lambda v: m.group(0) if v is None else f"{_fmt(v)}多元")(cn_so(m.group("n"))), s)

    # 九块九 / 两块五 / 3块5毛 / 5元8角 -> 9.9元 (nhưng 三块一包 = 3元一包)
    def thap_phan(m):
        v, d = cn_so(m.group("n")), _cn_digit(m.group("d"))
        sau = s[m.end():m.end() + 1]
        if v is None or d is None:
            return m.group(0)
        if m.group("d") == "一" and not m.group("hao") and sau and sau in _LUONG_TU:
            return f"{_fmt(v)}元一"                 # 三块一包 = 3元一包
        return f"{_fmt(v + d / 10)}元"
    s = re.sub(rf"(?P<n>{NUM_ZH})(?:块|元)(?P<d>[零一二两三四五六七八九\d])(?![\d十百千万])(?P<hao>[毛角]钱?)?", thap_phan, s)

    # X块 / X元 -> X元 (块 chỉ là tiền khi có 钱, đứng cuối câu, hoặc ngay sau từ chỉ giá)
    def don(m):
        v = cn_so(m.group("n"))
        if v is None:
            return m.group(0)
        if m.group("dv") == "块":
            sau = s[m.end():m.end() + 1] if m.end() < len(s) else ""
            truoc = s[max(0, m.start() - 4):m.start()]
            cuoi_cau = (sau == "" or re.match(r"[\s，。,.!！?？、~～]", sau)) and not re.search(r"[吃切拿夹掰分剩]了?$", truoc)
            if not (m.group("tien") or cuoi_cau or re.search(_MO_DAU_GIA + "$", truoc)):
                return m.group(0)
        return f"{_fmt(v)}元"
    s = re.sub(rf"(?P<n>{NUM_ZH})(?P<dv>块|元)(?P<tien>钱)?", don, s)

    # 五毛 / 三角钱 -> 0.5元
    s = re.sub(r"(?<![\d一二两三四五六七八九十百千万])(?P<d>[一二两三四五六七八九\d])(?:毛|角)钱?(?![衣巾绒发孔笔病线])",
               lambda m: f"{_fmt(_cn_digit(m.group('d')) / 10)}元", s)

    # 只要69.9 / 才三十 -> 只要69.9元 (số trần đứng sau từ chỉ giá, hết câu)
    s = re.sub(rf"(?P<dau>{_MO_DAU_GIA})(?P<n>{NUM_ZH})(?!\d)(?!\.\d)(?=[\s，。,!！?？、~～]|\.(?!\d)|$)",
               lambda m: (lambda v: m.group(0) if v is None else f"{m.group('dau')}{_fmt(v)}元")(cn_so(m.group("n"))), s)

    # 2万 / 两万 (không phải tiền) -> 20000 để bản dịch không ra "2 vạn"
    s = re.sub(rf"(?P<n>(?:\d+(?:\.\d+)?|[一二两三四五六七八九十][零〇一二两三四五六七八九十百千]*)[万亿][零〇一二两三四五六七八九]?)(?![零〇一二两三四五六七八九十百千])",
               lambda m: (lambda v: m.group(0) if v is None else _fmt(v))(cn_so(m.group("n"))), s)
    return s


def so_tien_goc(cau: str) -> set:
    """Các số tiền (đã chuẩn hoá) trong câu tiếng Trung."""
    return {round(float(x), 2) for x in re.findall(r"(\d+(?:\.\d+)?)多?元", cau)}


# ---------------------------------------------------------------- 2 + 3. câu tiếng Việt
_TEN_TIEN = re.compile(r"(?i)\b(?:đồng\s+)?(?:nhân\s+dân\s+tệ|NDT|RMB|CNY|yuan|tệ)\b")


def chuan_hoa_hien(cau: str, tien_goc: set = frozenset()) -> str:
    """Câu tiếng Việt để hiện phụ đề: đơn vị 'tệ', số kiểu Việt, thêm 'tệ' nếu bản dịch quên."""
    s = _TEN_TIEN.sub(DON_VI, cau)
    s = re.sub(r"[¥￥]\s*(\d[\d.,]*)", rf"\1 {DON_VI}", s)
    s = re.sub(r"(\d)\s*元", rf"\1 {DON_VI}", s)

    def so(m):
        ng, le = tach_so(m.group(1))
        moi = viet_so(ng, le)
        sau = s[m.end():]
        if tien_goc and round(_gia_tri(ng, le), 2) in tien_goc:
            if re.match(r"\s*đồng\b", sau):
                return moi + "\0"                       # "9,9 đồng" -> "9,9 tệ"
            if not re.match(rf"\s*(?:{DON_VI}|{TEN_NGHIN}|nghìn|ngàn|triệu|tỷ|đồng|%)", sau):
                return f"{moi} {DON_VI}"
        return moi
    s = SO_VI.sub(so, s)
    s = re.sub(r"\0\s*đồng", f" {DON_VI}", s)
    s = re.sub(rf"\b{DON_VI}(\s+{DON_VI}\b)+", DON_VI, s)
    return doi_tien_viet(s)


_FILE_TY_GIA = Path(__file__).resolve().parent / ".ty_gia.json"
_ty_gia_nho = None


def ty_gia() -> float:
    """1 tệ = ? đồng. Lấy tỷ giá mới mỗi ngày 1 lần (lưu .ty_gia.json), lỗi mạng thì dùng số đã lưu / dự phòng."""
    global _ty_gia_nho
    if _ty_gia_nho:
        return _ty_gia_nho
    import datetime
    import json
    hom_nay = datetime.date.today().isoformat()
    cu = {}
    try:
        cu = json.loads(_FILE_TY_GIA.read_text(encoding="utf-8"))
        if cu.get("ngay") == hom_nay and cu.get("ty_gia"):
            _ty_gia_nho = float(cu["ty_gia"])
            return _ty_gia_nho
    except Exception:
        pass
    try:
        import urllib.request
        with urllib.request.urlopen(URL_TY_GIA, timeout=10) as r:
            v = float(json.loads(r.read().decode())["rates"]["VND"])
        if 1000 < v < 20000:
            _FILE_TY_GIA.write_text(json.dumps({"ngay": hom_nay, "ty_gia": v}), encoding="utf-8")
            _ty_gia_nho = v
            return v
    except Exception:
        pass
    _ty_gia_nho = float(cu.get("ty_gia") or TY_GIA_DU_PHONG)
    return _ty_gia_nho


def _canh(dong: float) -> str:
    """Số đồng -> 'N cành'. Làm tròn cho gọn, dễ đọc: dưới 100 cành tròn 1 cành (38),
    100-999 tròn 10 cành (270), từ 1.000 tròn 100 cành (5.000)."""
    c = dong / 1000
    c = max(1, round(c)) if c < 100 else int(round(c / 10) * 10) if c < 1000 else int(round(c / 100) * 100)
    return f"{viet_so(str(c), None)} {TEN_NGHIN}"


_SO = r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?"


def doi_tien_viet(cau: str) -> str:
    """'69,9 tệ' -> '269 cành'; '500 nghìn đồng' / '500.000 đồng' -> '500 cành'."""
    if not QUY_DOI_VND:
        return cau
    tg = ty_gia()

    def gt(x):
        return _gia_tri(*tach_so(x))

    nhan_so = {None: 1, "trăm": 100, "nghìn": 1000, "ngàn": 1000, "vạn": 10000, "triệu": 1_000_000}

    def te(m):
        k = nhan_so[m.group("nhan")] * tg
        a = _canh(gt(m.group("a")) * k)
        if m.group("b"):        # khoảng giá: "100-200 tệ", "100, 200 tệ", "1-2 trăm tệ" -> "385 đến 769 cành"
            return f"{a.rsplit(' ', 1)[0]} đến {_canh(gt(m.group('b')) * k)}"
        return a
    s = re.sub(rf"(?<![\w.,])(?P<a>{_SO})(?:\s*(?:-|–|~|/|,|đến|tới|hoặc)\s*(?P<b>{_SO}))?"
               rf"\s*(?P<nhan>trăm|nghìn|ngàn|vạn|triệu)?\s*{DON_VI}\b", te, cau)
    s = re.sub(rf"(?<![\w.,])(?P<a>{_SO})\s*(?:nghìn|ngàn)\s*(?:đồng|VNĐ|VND)\b",
               lambda m: _canh(gt(m.group("a")) * 1000), s)
    s = re.sub(rf"(?<![\w.,])(?P<a>{_SO})\s*(?:đồng|VNĐ|VND|đ)(?!\w)",
               lambda m: _canh(gt(m.group("a"))) if gt(m.group("a")) >= 1000 else m.group(0), s)
    s = re.sub(rf"(?<![\w.,])(?P<a>{_SO})\s*(?:triệu)\s*(?:đồng|VNĐ|VND)\b",
               lambda m: _canh(gt(m.group("a")) * 1_000_000), s)
    return s


def chuan_hoa_doc(cau: str) -> str:
    """Câu cho giọng đọc: mọi con số thành chữ."""
    s = re.sub(r"(\d)\s*%", r"\1 phần trăm", cau)
    s = SO_VI.sub(lambda m: doc_so_le(*tach_so(m.group(1))), s)
    return s


# ---------------------------------------------------------------- làm trên file SRT
def _doc_srt(p: Path):
    khoi = re.split(r"\n\s*\n", Path(p).read_text(encoding="utf-8", errors="ignore").strip())
    ra = []
    for k in khoi:
        d = k.splitlines()
        if len(d) >= 2 and "-->" in d[1]:
            ra.append([d[0], d[1], "\n".join(d[2:])])
    return ra


def _ghi_srt(p: Path, khoi):
    Path(p).write_text("\n\n".join(f"{a}\n{b}\n{c}" for a, b, c in khoi) + "\n", encoding="utf-8")


def sua_goc(srt: Path):
    """Lớp 1: sửa phụ đề tiếng Trung tại chỗ."""
    try:
        khoi = _doc_srt(srt)
        _ghi_srt(srt, [[a, b, chuan_hoa_goc(c)] for a, b, c in khoi])
    except Exception:
        pass


def sua_hien(vi: Path, goc: Path | None = None):
    """Lớp 2: sửa phụ đề tiếng Việt tại chỗ (dạng hiện)."""
    try:
        khoi = _doc_srt(vi)
        g = _doc_srt(goc) if goc and Path(goc).exists() else []
        cung = len(g) == len(khoi)
        _ghi_srt(vi, [[a, b, chuan_hoa_hien(c, so_tien_goc(g[i][2]) if cung else set())]
                      for i, (a, b, c) in enumerate(khoi)])
    except Exception:
        pass


def tach_doc(vi: Path, goc: Path | None = None) -> Path | None:
    """Trước khi lồng tiếng: lưu bản hiện ra vi_hien.srt, còn vi.srt thành bản cho giọng đọc (số -> chữ)."""
    try:
        sua_hien(vi, goc)
        hien = Path(vi).with_name(Path(vi).stem + "_hien.srt")
        khoi = _doc_srt(vi)
        _ghi_srt(hien, khoi)
        _ghi_srt(vi, [[a, b, chuan_hoa_doc(c)] for a, b, c in khoi])
        return hien
    except Exception:
        return None


def tra_hien(vi: Path, hien: Path):
    """Sau khi lồng tiếng: đưa chữ hiện (dạng số) trở lại vi.srt, giữ mốc thời gian mới nhất."""
    try:
        moi, cu = _doc_srt(vi), _doc_srt(hien)
        if len(moi) == len(cu):
            _ghi_srt(vi, [[a, b, cu[i][2]] for i, (a, b, _) in enumerate(moi)])
        Path(hien).unlink(missing_ok=True)
    except Exception:
        pass


def cau_co_gia(vi: Path, goc: Path | None = None) -> list:
    """Số thứ tự (từ 0) các câu có nói giá tiền - để cảnh báo người dùng kiểm tra trước khi lồng tiếng."""
    try:
        khoi = _doc_srt(vi)
        g = _doc_srt(goc) if goc and Path(goc).exists() else []
        cung = len(g) == len(khoi)
        ra = []
        for i, (_, _, c) in enumerate(khoi):
            co = re.search(rf"\d\s*(?:{DON_VI}|{TEN_NGHIN}|đồng|nghìn đồng|k)\b|[¥￥元]", c, re.I) or re.search(rf"\b{DON_VI}\b", c)
            if co or (cung and (so_tien_goc(g[i][2]) or re.search(r"[元¥￥]|块钱|\d块", g[i][2]))):
                ra.append(i)
        return ra
    except Exception:
        return []


if __name__ == "__main__":
    import sys
    for dong in sys.argv[1:]:
        print(dong, "->", chuan_hoa_goc(dong))
