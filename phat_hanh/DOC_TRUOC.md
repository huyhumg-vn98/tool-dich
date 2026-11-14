# Tool dịch video Douyin → tiếng Việt: Cài đặt

## Yêu cầu
- Máy Mac, nên dùng chip Apple (M1 trở lên). Máy Intel vẫn chạy nhưng chậm hơn.
- Trống khoảng **10 GB** ổ cứng, có mạng ổn định.

## Cài (chỉ làm 1 lần)
1. Giải nén file zip vào nơi bạn muốn để tool, ví dụ thư mục `Documents`.
   Đừng di chuyển thư mục này sau khi cài. Nếu lỡ di chuyển thì chạy lại bước 2.
2. **Chuột phải** vào `CaiDat.command` → **Open** → **Open**.
   (Bấm đúp thường sẽ bị macOS chặn vì file tải từ Internet.)
3. Làm theo cửa sổ Terminal. Máy có thể hỏi mật khẩu Mac (để cài Homebrew) và hỏi cài
   "Command Line Tools". Bấm Install, chờ xong rồi quay lại Terminal bấm Enter.
4. Thấy dòng **"✔ CÀI ĐẶT XONG!"** là xong. Lần cài đầu mất khoảng 15–30 phút tuỳ mạng.

## Dùng
- Bấm đúp **`Dịch Video.app`**. Lần đầu nếu bị chặn: chuột phải → Open → Open.
- Xem cách dùng chi tiết trong `HUONG_DAN.md`.

## API key (không bắt buộc)
Mỗi người tự nhập key của mình trên giao diện:
- **ai33.pro**: thêm nhiều giọng đọc (Vbee, ElevenLabs…). Mục "Giọng ai33.pro".
- **DeepSeek**: dịch hay hơn Google, hiểu ngữ cảnh. Mục "Dịch bằng DeepSeek".

Không có key vẫn dùng được: **Google Dịch + giọng Edge (HoaiMy, NamMinh)** miễn phí.

## Lưu ý
- Lần dịch đầu tiên tool tự tải mô hình nghe (~3 GB) nên sẽ lâu. Từ lần sau thì nhanh.
- Tool dùng [pyVideoTrans](https://github.com/jianchang512/pyvideotrans) (giấy phép GPL-3.0).
  Xem `GIAY_PHEP.md`.
- Video Douyin thuộc bản quyền tác giả gốc. Bạn tự chịu trách nhiệm khi sử dụng hoặc đăng lại.
