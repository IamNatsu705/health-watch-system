# Dashboard web local

Ứng dụng Vue 3 + Vite chạy ở <http://localhost:5173> qua Docker Compose. Nó gọi FastAPI để lấy danh sách thiết bị, số đo mới nhất, lịch sử ngắn và sự kiện; cập nhật khoảng mỗi 3 giây. Vite proxy `/api` vào container API, nên trình duyệt máy tính/điện thoại cùng LAN không cần gọi PostgreSQL hay MQTT trực tiếp.

Dashboard có trạng thái dữ liệu mới/cũ, hiển thị `--` khi BPM chưa có, và ghi `dashboard_view`/`device_select` bằng `session_id` ẩn danh. Dữ liệu hiển thị trong bản local là mock.

Khi chạy Vite ngoài Compose trên Windows, dùng `npm.cmd install` rồi `npm.cmd run dev` trong thư mục `web/`; proxy mặc định gọi API ở `http://localhost:8000`. Khi đóng gói APK sau này, đặt `VITE_API_BASE_URL` tới địa chỉ API truy cập được từ điện thoại. Capacitor/Android chưa được thêm trong bản local này.

Để thử trên điện thoại trong cùng LAN, mở `http://<IP-LAN-máy-tính>:5173`. Cổng 5173 phải được Windows Firewall cho phép; `localhost` trên điện thoại không trỏ tới máy tính.
