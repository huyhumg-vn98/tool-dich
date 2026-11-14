# Tool dịch video Douyin → tiếng Việt: Cài đặt trên Windows

## Yêu cầu
- Windows 10 hoặc 11, bản 64-bit.
- Trống khoảng **10 GB** ổ cứng, có mạng ổn định.
- Có card NVIDIA thì chạy nhanh hơn, không có vẫn chạy được.

## Cài (chỉ làm 1 lần)
1. **Giải nén** file zip vào nơi muốn để tool, ví dụ `D:\DichVideo`.
   - Phải giải nén ra (chuột phải → Extract All), không chạy trực tiếp trong file zip.
   - Nên để ở đường dẫn ngắn, không dấu. Đừng di chuyển thư mục sau khi cài.
2. Bấm đúp **`CaiDat.bat`**.
   - Nếu Windows hiện "Windows protected your PC": bấm **More info** → **Run anyway**.
3. Chờ cửa sổ chạy xong, thấy dòng **"✔ CÀI ĐẶT XONG!"** là xong. Mất khoảng 15–30 phút tuỳ mạng.

## Dùng
- Bấm đúp lối tắt **"Dich Video"** trên Desktop. Giao diện mở trên trình duyệt.
- Một cửa sổ đen thu nhỏ "Dich Video - may chu" sẽ chạy ở thanh taskbar. **Đừng tắt nó khi đang dịch.**
  Dịch xong muốn tắt hẳn tool thì đóng cửa sổ đó.
- Cách dùng chi tiết: `HUONG_DAN.md`. Phần giao diện giống hệt bản Mac.

## API key (không bắt buộc)
Mỗi người tự nhập key của mình trên giao diện:
- **ai33.pro**: thêm nhiều giọng đọc (Vbee, ElevenLabs…). Mục "Giọng ai33.pro".
- **DeepSeek**: dịch hay hơn Google. Mục "Dịch bằng DeepSeek".

Không có key vẫn dùng được **Google Dịch + giọng Edge** miễn phí.

## Lưu ý
- Lần dịch đầu tiên tool tự tải mô hình nghe (~3 GB) nên sẽ lâu.
- Nút "Tải qua Seekin": tool tự nhận file video mới trong thư mục **Downloads** của Windows.
- Tool dùng [pyVideoTrans](https://github.com/jianchang512/pyvideotrans) (GPL-3.0). Xem `GIAY_PHEP.md`.
- Video Douyin thuộc bản quyền tác giả gốc. Bạn tự chịu trách nhiệm khi sử dụng hoặc đăng lại.
