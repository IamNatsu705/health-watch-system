# Health Watch System — bản local dùng dữ liệu mock

`health_watch/` là code lấy từ Raspberry Pi, vẫn chạy riêng trên Pi. Bản local trong repo này có mock publisher đóng vai Pi để kiểm tra MQTT → PostgreSQL → API → web trên máy tính mà không cần chạm phần cứng.

```text
mock-pi → Mosquitto → backend/ingest → PostgreSQL → backend/api → web
                         (sau này thay mock bằng health_watch/ trên Pi)
```

## Chạy nhanh trên Windows

Yêu cầu Docker Desktop đang chạy. Đứng tại thư mục `C:\Project\health_watch_system`:

```powershell
Copy-Item .\infra\local\.env.example .\infra\local\.env
docker compose --env-file infra/local/.env -f infra/local/compose.yaml --profile mock up --build -d
docker compose --env-file infra/local/.env -f infra/local/compose.yaml ps
```

Mở dashboard tại <http://localhost:5173>. API ở <http://localhost:8000/docs>. Mock gửi số đo mỗi giây; sự kiện ngã/SOS xuất hiện định kỳ trong một chu kỳ 60 giây.

Thử API bằng PowerShell:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/api/v1/devices
Invoke-RestMethod http://localhost:8000/api/v1/devices/pi-watch-mock-001/latest
```

Kiểm tra tích hợp (gửi bản tin hợp lệ, gửi trùng, gửi sai schema, rồi tự xóa dữ liệu thử):

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml --profile mock exec -T ingest python -m backend.smoke_local
```

Xem log hoặc dừng các dịch vụ:

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml logs -f ingest mock-pi api
docker compose --env-file infra/local/.env -f infra/local/compose.yaml --profile mock down
```

Lệnh `down` giữ lại volume PostgreSQL. File `infra/local/.env` dành riêng máy local và được Git bỏ qua. Giá trị trong `.env.example` chỉ dành cho demo LAN; đổi chúng trước khi dùng với Pi thật hoặc mở dịch vụ cho máy khác.

## Thư mục và nơi chạy

| Thư mục | Vai trò | Nơi chạy khi thử local |
| --- | --- | --- |
| [`health_watch/`](health_watch/README.md) | Code cảm biến/TFT/LED/còi hiện có; chưa publish MQTT | Raspberry Pi, chưa tham gia bản mock |
| [`backend/mock_publisher/`](backend/mock_publisher/README.md) | Giả lập Pi và phát bản tin v1 | Container `mock-pi` trên máy tính |
| [`backend/ingest/`](backend/ingest/README.md) | Nhận MQTT, kiểm tra schema, ghi DB | Container trên máy tính |
| [`backend/api/`](backend/api/README.md) | Đọc DB, trả HTTP API, ghi hoạt động trình duyệt | Container trên máy tính |
| [`web/`](web/README.md) | Dashboard responsive | Container Vite trên máy tính |
| [`contracts/mqtt/`](contracts/mqtt/README.md) | Cấu trúc bản tin dùng chung | Pi/mock và ingest |
| [`infra/local/`](infra/local/README.md) | Docker Compose, cấu hình broker/DB | Máy tính |

Xem [kiến trúc hệ thống](docs/ARCHITECTURE.md) và [thiết kế tổng thể](PROJECT_DESIGN.md) để biết đường chuyển từ local lên cloud. APK và AI chưa được triển khai trong bản local này.

## Giới hạn bản local

API đang mở cho thử nghiệm local, chưa có đăng nhập hoặc phân quyền. `user_activity_logs` hiện ghi hành động của một phiên trình duyệt ẩn danh (`session_id`), chưa gắn tài khoản thật. MQTT/DB có mật khẩu demo, nhưng chưa có TLS. Không đưa cấu hình này lên Internet.

Số BPM, bước, km và kcal trên dashboard là dữ liệu mô phỏng. Bản local dùng để xác nhận đường đi dữ liệu, không đánh giá thuật toán cảm biến.
