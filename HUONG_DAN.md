# Tool dịch video Douyin → tiếng Việt

## Mở tool
Bấm đúp **`Dịch Video.app`** (Mac) hoặc lối tắt **"Dich Video"** trên Desktop (Windows) → giao diện mở trên trình duyệt (http://127.0.0.1:8765).
Mac: lần đầu nếu máy chặn thì chuột phải vào app → Open → Open. Windows: đừng tắt cửa sổ đen "Dich Video - may chu" khi đang dịch.

## Dùng
1. Dán link Douyin (nhiều link / nguyên đoạn chia sẻ đều được), link video trực tiếp (douyinvod.com, .mp4), hoặc kéo thả file video vào ô.
2. Chọn giọng, tốc độ, kiểu phụ đề, cách dịch → **Thêm vào hàng chờ**. Thêm tiếp lúc nào cũng được.
3. Xong: bấm **Xem video** / **Hiện trong Finder**. Kết quả nằm trong thư mục `Video_Ra`.

Nút trên mỗi video: **■ Dừng** (bấm nhầm), **Làm lại** (chạy lại từ đầu), **Lồng tiếng lại** (chỉ đọc lại câu bị câm), **Xoá**.

## Quy trình tự động (mọi video, không cần chỉnh tay)
1. Tải video từ link qua SaveTik (tự thử lại). SaveTik lỗi thì bạn bấm "Tải qua Seekin", app tự nhận file.
2. **Làm nét video mờ** (ô "Làm nét video"): video dưới 1080p (vd 576x1024) được AI Real-ESRGAN phóng lên 1080p
   và làm nét trước khi dịch. Video đã 1080p thì bỏ qua. Mất khoảng 10 giây xử lý cho mỗi giây video trên Mac M4.
   Chỉnh ở đầu `lam_net.py`: DICH_NGANG (1080), MUC_NET (0.85 = trộn nhẹ với ảnh gốc cho tự nhiên).
3. Nhận diện tiếng gốc.
4. Nghe → chia câu theo từng cụm lời (khớp nhịp nói), tự gộp câu bị cắt vụn.
5. Dịch: Google (miễn phí) hoặc DeepSeek (hiểu ngữ cảnh, khuyên dùng).
   - **Video không có lời nói** (chỉ nhạc/tiếng động): AI DeepSeek xem các khung hình và tự viết lời
     thuyết minh tiếng Việt kiểu giới thiệu / bán sản phẩm, chia câu khớp từng cảnh, rồi lồng tiếng như thường.
     Cần API key DeepSeek. Tắt bằng ô "Video không có lời nói" → "bỏ qua". Bật "Sửa phụ đề" để sửa lời trước khi lồng.
     AI cũng chọn 2-4 **chỗ đẹp / ngon mắt nhất** → máy quay **từ từ đẩy cận** vào đó (~3 giây), giữ một chút rồi
     **từ từ lùi ra** (~2 giây), chuyển động liên tục, không bật về đột ngột. Chữ Việt đứng yên, không zoom theo. Có ở kiểu phụ đề "AI xoá sạch" và "Không gắn phụ đề".
     Video có lời nói thì không thêm hiệu ứng.
   - **Giá tiền tự đổi sang tiền Việt, gọi là "cành"** (1 cành = 1 nghìn đồng): "九块九" → 9,9 tệ → "38 cành",
     "199元" → "765 cành", "500 nghìn đồng" → "500 cành". Tỷ giá lấy mới mỗi ngày (mất mạng thì dùng tỷ giá đã lưu).
     Làm tròn cho gọn: dưới 100 cành tròn 1 cành, 100-999 tròn 10 cành, từ 1.000 tròn 100 cành. Giọng đọc nhận số dạng chữ nên không đọc lệch.
     Tắt quy đổi / đổi tên "cành": đầu file `gia_tien.py` (QUY_DOI_VND, TEN_NGHIN).
   - **Viết lại lời tự nhiên kiểu người Việt** (cần key DeepSeek): AI tự nhận ra kiểu video (bán hàng / hướng dẫn /
     giải trí / kiến thức) và viết lại từng câu theo giọng văn đó, đúng thuật ngữ (vd lái xe: "đánh lái", "trả lái"),
     giữ nguyên con số và giá. Câu trong **3 giây đầu** được viết thành câu mở đầu thu hút để giữ chân người xem.
     Ghi cố định kiểu cho cả thư mục chủ đề: tạo file `kieu.txt` ghi `ban hang` / `huong dan` / `giai tri` / `kien thuc`.
     Tắt: `viet_lai.py` → BAT = False.
   - **Phụ đề tô màu**: giá tiền, số đo và từ khoá quan trọng (AI chọn) hiện màu vàng. Đổi màu / tắt: `che_chu.py` → MAU_TU_KHOA.
   - **Chống đọc nhanh**: câu dịch nào quá nhiều chữ so với thời gian (trên 5 tiếng/giây) thì DeepSeek tự viết
     ngắn lại; còn chật thì mượn thêm tối đa 0,6 giây từ câu bên cạnh đang dư. Chỉnh ở đầu `rut_gon.py`
     (TOC_DO_TOI_DA, LECH_TOI_DA). Cần API key DeepSeek; không có key thì bỏ qua bước viết ngắn.
   - **Video 2 người nói** (ô "Giọng người thứ 2"): chọn thêm 1 giọng (cùng loại với giọng chính: cùng ai33 hoặc
     cùng Edge). Tool tự nhận ai nói câu nào, đo giọng trầm/cao: người giọng trầm đọc bằng giọng nam, giọng cao
     đọc bằng giọng nữ. Video chỉ có 1 người nói thì vẫn giữ đúng giọng chính. Hàng chờ hiện "👥 2 giọng" khi có tách.
     Chỉnh ngưỡng: đầu file `hai_giong.py` (NGUONG_NAM_NU, CHENH_TOI_THIEU).
6. Tách giọng gốc khỏi nhạc nền (giữ nhạc + hiệu ứng). **Nhạc nền tự nhỏ lại khi có giọng đọc** (~8 dB), hết giọng to lại
   (chỉnh `auto_dich.py` → HA_NHAC, HA_NHAC_TY_LE), lồng tiếng Việt 6 câu song song; lỗi tạm thời tự thử lại.
7. Che chữ gốc: tìm "làn phụ đề" (chữ căn giữa, lặp lại cùng chỗ), bỏ qua chữ trong cảnh
   (biển số, chữ trên xe, bao bì). Có 3 kiểu (chọn ở ô "Phụ đề"):
   - **AI xoá sạch** (mặc định): AI (mô hình LaMa) vẽ lại nền chỗ chữ gốc, chữ Trung biến mất hẳn,
     chữ Việt trắng viền đen đặt đúng chỗ đó, không có khung. Chậm hơn (video 18 giây ~2 phút trên Mac M4;
     máy Windows không có card NVIDIA sẽ chậm hơn nhiều).
   - **Khung đen**: chữ Việt trắng trên khung đen phủ lên dòng phụ đề chính. Nhanh.
   - **Chỉ xoá chữ gốc bằng AI, không gắn phụ đề Việt**: như AI xoá sạch nhưng không đặt chữ Việt lên
     (video sạch chữ, chỉ có giọng Việt). Máy chưa có mô hình AI thì lấp chữ bằng màu nền xung quanh.
   Video ra chất lượng gần như bản gốc.
8. Tự kiểm tra câu câm → tự đọc lại và chèn vào (tối đa 2 lần).
9. Tự dọn file tạm.

## Tự động theo thư mục chủ đề
1. Bấm nút **"Thư mục chủ đề"** trên giao diện (mở thư mục `Chu_De/`).
2. Tạo mỗi chủ đề 1 thư mục con, vd `Chu_De/My_pham/`, `Chu_De/Do_an/`.
3. Bỏ vào đó 1 file `.txt` chứa link (mỗi dòng 1 link, dán cả đoạn chia sẻ Douyin cũng được) rồi lưu.
4. Tool tự thấy link mới sau ~15 giây, tải + dịch **lần lượt** theo lựa chọn đang chọn trên giao diện.
   Video xong nằm ở `Video_Ra/<tên chủ đề>/`. Thêm link mới vào file bất cứ lúc nào, tool chỉ làm link chưa làm.
   Link đã thêm được ghi ở `.da_them.txt` trong thư mục chủ đề (xoá dòng đó nếu muốn làm lại).

## Cài đặt hay đổi
| Muốn đổi | Ở đâu |
|---|---|
| API key ai33 / DeepSeek | Trên giao diện (mục "Giọng ai33.pro", "Dịch bằng DeepSeek") |
| Thêm giọng ai33 | Giao diện → Giọng ai33.pro → chọn nguồn, lọc nam/nữ → ▶ Nghe → + Thêm |
| Kiểu che, font, màu chữ, cỡ chữ, chất lượng video | Đầu file `che_chu.py`: KIEU_CHE ("ai" AI xoá sạch / "den" khung đen / "xoa" xoá mờ), FONT, MAU_CHU, CO_CHU, CRF (16 = nét nhất; 18-20 = file nhẹ hơn) |
| Mức zoom, tốc độ zoom | Đầu file `hieu_ung.py`: MUC_ZOOM (1.18), TG_ZOOM (giây đẩy cận), TG_GIU, TG_LUI |
| Kiểu lời thuyết minh, tốc độ đọc, cách viết | Đầu file `thuyet_minh.py`: KIEU_LOI, AM_TIET_MOI_GIAY, HUONG_DAN |
| Tên đơn vị tiền khi đọc | Đầu file `gia_tien.py`: DON_VI = "tệ" |
| Mô hình nghe (chính xác/nhanh) | `auto_dich.py`: `MO_HINH = "large-v3"` (hoặc "medium" cho nhanh) |
| Chia câu chi tiết/thô | `pyvideotrans/videotrans/cfg.json`: min_speech_duration_ms=500, min_silence_duration_ms=150, max_speech_duration_s=3 |
| Số câu lồng tiếng song song | `pyvideotrans/videotrans/cfg.json`: dubbing_thread=6 |

## Gặp lỗi
- "Video không có giọng người nói": video chỉ có nhạc nền, không có gì để dịch.
- Video báo **Cần tải tay** (SaveTik lỗi): bấm **Tải qua Seekin** → dán link (Cmd+V) → Tải xuống. App tự nhận file và dịch tiếp.
- Video báo Lỗi: bấm **Làm lại**. Vẫn lỗi thì xem dòng lỗi màu đỏ dưới tên video.
- Giao diện không mở: bấm lại `Dịch Video.app`.
- Log máy chủ: `.hang_doi.log`; log pyVideoTrans: `pyvideotrans/logs/`.

## Thư mục
- `Video_Vao/Tai_ve`: video tải từ link · `Video_Vao/Tai_len`: video kéo thả
- `Video_Ra`: video đã dịch + phụ đề `.srt`
