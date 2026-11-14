# Tool dịch & lồng tiếng video Douyin/TikTok sang tiếng Việt

Xây trên [pyVideoTrans](https://github.com/jianchang512/pyvideotrans) (GPL-3.0). Giao diện hàng chờ chạy trên trình duyệt (http://127.0.0.1:8765).

**Tính năng chính**
- Tải video từ link Douyin/TikTok, tự nhận diện ngôn ngữ, nghe, dịch (Google / DeepSeek), lồng tiếng Việt (Edge / ai33).
- Giữ nhạc nền & hiệu ứng, chỉ thay giọng.
- AI xoá sạch chữ gốc (LaMa) rồi đặt phụ đề Việt đúng chỗ, hoặc kiểu khung đen.
- Video không lời: AI (DeepSeek) xem hình, tự viết lời giới thiệu sản phẩm + zoom chậm vào chỗ đẹp.
- Giá tiền tự đổi tệ → tiền Việt ("cành"), tự rút gọn câu quá dài để giọng đọc không bị nhanh.
- AI làm nét video mờ (Real-ESRGAN) lên 1080p.
- Thư mục chủ đề: bỏ file link vào `Chu_De/<chủ đề>/`, tool tự dịch lần lượt, video ra theo từng chủ đề.
- Hiện % tiến độ từng bước.

**Cài đặt:** xem `phat_hanh/` (macOS: `CaiDat.command`, Windows: `windows/CaiDat.bat`) và `HUONG_DAN.md`.
API key (ai33, DeepSeek) mỗi người tự nhập trên giao diện, không có trong mã nguồn.
