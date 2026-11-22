# Môi trường local bằng Docker Compose

[`compose.yaml`](compose.yaml) chạy toàn bộ phần server trên máy tính. Có thể
dùng mock data hoặc thay mock bằng Raspberry Pi thật.

## Dịch vụ

| Service | Vai trò | Cổng host |
| --- | --- | --- |
| `db` | PostgreSQL 17, lưu dữ liệu | Không public |
| `mosquitto` | MQTT broker | `1883` |
| `migrate` | Chạy Alembic rồi kết thúc | Không public |
| `ingest` | MQTT → validate → PostgreSQL | Không public |
| `api` | FastAPI và MQTT command client | `8000` |
| `web` | Vue/Vite dashboard | `5173` |
| `mock-pi` | Dữ liệu mô phỏng, profile `mock` | Không public |

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
| `MQTT_USERNAME` | Broker, API, ingest, Pi/mock | Local đang dùng một tài khoản chung |
| `MQTT_PASSWORD` | MQTT | Phải khớp file `.env` trên Pi |
| `MOCK_DEVICE_ID` | Mock publisher | Mặc định `pi-watch-mock-001` |

`.env` được Git bỏ qua. `.env.example` chỉ chứa giá trị demo.

## 2. Chạy bằng mock data

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml --profile mock up --build -d
docker compose --env-file infra/local/.env -f infra/local/compose.yaml --profile mock ps
```

Mở <http://localhost:5173> và <http://localhost:8000/docs>. Mock gửi
telemetry/event nhưng không mô phỏng GPIO, command hoặc `alert-state`; công
tắc còi sẽ không hoạt động với mock.

## 3. Chạy với Pi thật

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml --profile mock stop mock-pi
docker compose --env-file infra/local/.env -f infra/local/compose.yaml up --build -d
docker compose --env-file infra/local/.env -f infra/local/compose.yaml ps
```

Pi dùng IP LAN của máy tính ở `MQTT_HOST`; không dùng `localhost`. Cho phép
TCP `1883` trên Windows Firewall profile Private. Android cần TCP `8000`;
máy khác mở web cần TCP `5173`.

## 4. Kiểm tra

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/api/v1/devices
docker compose --env-file infra/local/.env -f infra/local/compose.yaml logs --tail 100 mosquitto ingest api
```

Smoke test đầu-cuối:

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml exec -T ingest python -m backend.smoke_local
```

Smoke test tạo một `device_id` tạm, gửi telemetry/event hợp lệ và trùng, gửi
một payload sai schema, kiểm tra DB/API rồi tự xóa dữ liệu thử.

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
| MQTT `not authorised` | Username/password Pi khớp `infra/local/.env` |
| Thiết bị hiện offline | Pi service, ingest log, telemetry mới hơn 10 giây |
| Công tắc báo chưa có trạng thái | Pi chưa chạy code `alert-state` mới hoặc API chưa nhận retained state |
| Web vẫn giao diện cũ | Restart `web`, sau đó `Ctrl+F5` |

## 8. Bảo mật local

Mosquitto yêu cầu password nhưng chưa dùng TLS/ACL theo thiết bị. API chưa có
đăng nhập và CORS đang mở. Không port-forward 1883/8000/5173 ra Internet.
