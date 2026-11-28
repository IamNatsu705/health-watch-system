# Môi trường local bằng Docker Compose

[`compose.yaml`](compose.yaml) chạy toàn bộ phần server trên máy tính. Dữ liệu
chỉ đến từ Raspberry Pi thật đã khai báo trong `MQTT_DEVICES`; không có dịch vụ
giả lập thiết bị.

## Dịch vụ

| Service | Vai trò | Cổng host |
| --- | --- | --- |
| `db` | PostgreSQL 17, lưu dữ liệu | Không public |
| `mosquitto` | MQTT broker, tài khoản + ACL riêng cho từng Pi, giữ retained ở volume `mosquitto_data` | `1883` |
| `migrate` | Chạy Alembic rồi kết thúc | Không public |
| `ingest` | MQTT → validate → PostgreSQL | Không public |
| `api` | FastAPI và MQTT command client | `8000` |
| `web` | Vue/Vite dashboard | `5173` |

## 1. Chuẩn bị

Yêu cầu Docker Desktop đang chạy. Từ thư mục gốc dự án:

```powershell
if (-not (Test-Path .\infra\local\.env)) { Copy-Item .\infra\local\.env.example .\infra\local\.env }
notepad .\infra\local\.env
```

Các biến:

| Biến | Dùng cho | Ghi chú |
| --- | --- | --- |
| `POSTGRES_PASSWORD` | PostgreSQL/API/ingest | Đổi trước lần chạy đầu |
| `MQTT_USERNAME`, `MQTT_PASSWORD` | Tài khoản MQTT của backend (API, ingest) | Chỉ đọc dữ liệu thiết bị, chỉ ghi commands/config; không dùng trên Pi |
| `MQTT_DEVICES` | Broker, API, ingest | `id:mat_khau` cho từng Pi thật, cách nhau dấu phẩy. Pi dùng `MQTT_USERNAME=id` và mật khẩu đó |
| `LOCAL_TIMEZONE` | API | Múi giờ chia số bước theo ngày, mặc định `Asia/Ho_Chi_Minh` |

`.env` được Git bỏ qua. `.env.example` chỉ chứa giá trị demo.

## 2. Chạy stack và kết nối Pi thật

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml up --build -d
docker compose --env-file infra/local/.env -f infra/local/compose.yaml ps
```

Pi dùng IP LAN của máy tính ở `MQTT_HOST`, không dùng `localhost`. Cho phép
TCP `1883` trên Windows Firewall profile Private. Android cần TCP `8000`;
máy khác mở web cần TCP `5173`. Dashboard trống cho tới khi Pi gửi dữ liệu.

**Nâng cấp từ bản có mock:** container `mock-pi` cũ (nếu còn) không còn trong compose.
Chạy `docker compose ... up -d --remove-orphans` để xóa nó. Migration `0002` xóa dữ
liệu của thiết bị `pi-watch-mock-*` và `smoke-*` trong DB.

## 3. Thêm hoặc đổi thiết bị

Thêm `id:mat_khau` vào `MQTT_DEVICES`, rồi chạy
`docker compose ... up -d --force-recreate mosquitto ingest api`. Trên Pi mới, đặt
`MQTT_DEVICE_ID=id`, `MQTT_USERNAME=id`, `MQTT_PASSWORD=mat_khau`. Gỡ một Pi khỏi danh
sách thì broker từ chối kết nối của nó, và API/web không còn hiển thị thiết bị đó.

## 4. Kiểm tra

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/api/v1/devices
docker compose --env-file infra/local/.env -f infra/local/compose.yaml logs --tail 100 mosquitto ingest api
```

Kiểm tra tự động không ghi vào DB thật. Chạy `python -m pytest backend/tests` trên PC;
test dùng SQLite trong bộ nhớ. Kiểm tra đầu-cuối được làm bằng Pi thật theo
[tests/integration](../../tests/integration/README.md).

## 5. Cập nhật sau khi sửa code

Sửa backend/contract/Compose:

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml up --build -d
```

Sửa web: volume source được mount vào Vite. Nếu trình duyệt vẫn nhận module
cũ, chạy:

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml restart web
```

Sau đó nhấn `Ctrl+F5` trong trình duyệt.

## 6. Log và vòng đời

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml ps
docker compose --env-file infra/local/.env -f infra/local/compose.yaml logs -f ingest api web mosquitto
docker compose --env-file infra/local/.env -f infra/local/compose.yaml restart api web
docker compose --env-file infra/local/.env -f infra/local/compose.yaml down
```

`down` giữ volume `postgres_data`. `down -v` xóa dữ liệu PostgreSQL và
`web_node_modules`; chỉ dùng khi chủ ý tạo lại môi trường.

Nếu đổi `POSTGRES_PASSWORD` sau khi volume DB đã được tạo, đổi biến môi trường
không tự đổi mật khẩu trong DB. Hãy giữ mật khẩu cũ, đổi trong PostgreSQL hoặc
tạo volume mới có chủ ý sau khi backup.

## 7. Xử lý lỗi nhanh

| Lỗi | Kiểm tra |
| --- | --- |
| `localhost:5173` không mở | `docker compose ps`, log `web`, port 5173 bị chiếm |
| API `503` khi gửi command | Log `api`, kết nối API → Mosquitto |
| Pi MQTT timeout | IP LAN, cùng mạng, firewall 1883 |
| MQTT `not authorised` | Trên Pi: `MQTT_USERNAME` = `MQTT_DEVICE_ID`, mật khẩu khớp `MQTT_DEVICES` |
| Ingest log `không có trong MQTT_DEVICES` | Thêm ID của Pi vào `MQTT_DEVICES` rồi recreate `mosquitto ingest api` |
| Ingest log `Rejected ... telemetry` | Pi còn chạy firmware cũ (telemetry v1); triển khai lại `health_watch/` |
| Thiết bị hiện offline | Pi service, ingest log, telemetry mới hơn 10 giây |
| Công tắc báo chưa có trạng thái | Pi chưa chạy code `alert-state` mới hoặc API chưa nhận retained state |
| Web vẫn giao diện cũ | Restart `web`, sau đó `Ctrl+F5` |

## 8. Bảo mật local

Mosquitto yêu cầu mật khẩu, mỗi Pi một tài khoản, có ACL theo thiết bị; chưa dùng TLS.
API chưa có đăng nhập và CORS đang mở. Không port-forward 1883/8000/5173 ra Internet.
