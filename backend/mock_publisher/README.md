# Mock Raspberry Pi

Container `mock-pi` gửi telemetry mỗi giây cho thiết bị `pi-watch-mock-001` theo [MQTT contract v1](../../contracts/mqtt/README.md). Số BPM dao động giả lập, bước tăng theo thời gian, km/kcal tính từ bước; đôi lúc `finger_present=false` và BPM là `null`.

Trong mỗi chu kỳ 60 giây, mock phát `fall_detected`, `fall_acknowledged`, `sos_pressed`, `sos_released`. Khi kết nối/ngắt, nó phát status online/offline. Đây là dữ liệu tạo bằng code, không đọc cảm biến Pi.

Để bật mock, dùng `--profile mock` trong lệnh Docker Compose ở [README gốc](../../README.md). Khi thay bằng Pi thật, bỏ profile mock và cho Pi publish cùng topic/schema với credential MQTT local.
