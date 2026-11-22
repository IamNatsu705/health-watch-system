# Kiến trúc Health Watch

## 1. Mục tiêu và trạng thái hiện tại

Health Watch thu thập dữ liệu MPU6050/MAX30102 trên Raspberry Pi, xử lý sơ bộ tại edge, gửi MQTT tới backend Python, lưu PostgreSQL và hiển thị trên web/Android. Người dùng cũng có thể điều khiển LED đỏ và còi trên Pi từ web/app bằng một công tắc ON/OFF.

Hệ thống local, publisher Pi, dashboard và APK debug đã có. Hạ tầng cloud, đăng nhập/phân quyền và mô hình AI chưa được triển khai. Các thuật toán BPM, bước chân và phát hiện ngã là thử nghiệm, không phải phép đo y tế.

## 2. Sơ đồ runtime

```text
Raspberry Pi                              Máy tính local / máy chủ tương lai
┌──────────────────────────┐              ┌───────────────────────────────────┐
│ MPU6050, MAX30102, SOS   │              │ Mosquitto                         │
│          │               │ telemetry →  │   ├─→ ingest ─→ PostgreSQL        │
│ health_watch/main.py     ├──────────────►│   │                  ↑             │
│   ├─ xử lý edge          │ events/status│   │               FastAPI          │
│   ├─ TFT                 │              │   │                  ↑ HTTP         │
│   └─ LED đỏ + còi        │◄─────────────┤   └─ commands / alert-state        │
└──────────────────────────┘   command    └───────────────────┬───────────────┘
                                                            │
                                                 ┌──────────▼──────────┐
                                                 │ Web / Android APK   │
                                                 └─────────────────────┘
```

## 3. Trách nhiệm từng thành phần

| Thành phần | Chịu trách nhiệm | Không chịu trách nhiệm |
| --- | --- | --- |
| `health_watch/` | Đọc cảm biến, tính số đo thử nghiệm, phát hiện sự kiện, TFT/GPIO, publish telemetry/event/status/alert-state và nhận command | Không truy cập PostgreSQL hoặc phục vụ HTTP |
| Mosquitto | Định tuyến MQTT hai chiều giữa Pi, ingest và API | Không thay thế kho lịch sử |
| `backend/ingest/` | Subscribe telemetry/events/status, kiểm tra schema, chống trùng và ghi DB | Không phục vụ dashboard hoặc GPIO |
| PostgreSQL | Lưu thiết bị, telemetry, sự kiện và log hoạt động người dùng | Không mở trực tiếp cho web/app/Pi |
| `backend/api/` | Trả REST API, ghi activity log, publish command, subscribe `alert-state`, chặn lệnh bật trùng | Không đọc cảm biến hoặc điều khiển GPIO trực tiếp |
| `backend/mock_publisher/` | Sinh dữ liệu giả để thử luồng đọc | Không mô phỏng command/alert-state, do đó không dùng để thử công tắc |
| `web/` | Dashboard web và mã nguồn APK; gọi API và hiển thị trạng thái Pi xác nhận | Không kết nối MQTT/DB trực tiếp |
| `contracts/` | Nguồn chuẩn cho topic, schema và phiên bản | Không chứa secret hoặc logic runtime |

## 4. Luồng telemetry và sự kiện

1. Pi đọc MPU6050 theo vòng lặp và lấy mẫu MAX30102 từ FIFO.
2. Pi xử lý tại chỗ; TFT, SOS và cảnh báo cục bộ vẫn hoạt động khi mất mạng.
3. Publisher nền gửi telemetry tổng hợp QoS 1 tới `health/v1/devices/{device_id}/telemetry`; không gửi liên tục toàn bộ gia tốc thô.
4. Sự kiện SOS/ngã dùng topic `events` và `event_id` riêng. Trạng thái online/offline dùng retained `status`.
5. Ingest kiểm tra schema và đối chiếu `device_id` trong topic với payload.
6. Khóa `(device_id, boot_id, sequence)` và `event_id` giúp DB bỏ bản tin giao lại do QoS 1.
7. API đọc DB, trả latest/history/events/devices cho giao diện. Dashboard làm mới khoảng 3 giây.

`heart_rate_bpm: null` nghĩa là chưa có phép đo hợp lệ. Số bước hiện là số bước của phiên chạy Pi, không phải tổng ngày.

## 5. Luồng điều khiển cảnh báo từ xa

1. Người dùng gạt công tắc của thiết bị sang ON hoặc OFF.
2. Web/app gọi API với hành động `start` hoặc `stop`.
3. API kiểm tra thiết bị, trạng thái online, trạng thái cảnh báo hiện tại và lệnh đang chờ. Lệnh ON trùng bị từ chối.
4. API publish command QoS 1, `retain=false` tới topic `commands` của đúng thiết bị.
5. Pi kiểm tra `command_id`, `device_id`, timestamp và thời lượng; sau đó bật/tắt LED đỏ và còi.
6. Pi publish retained `alert-state` gồm trạng thái thực tế và command đã xử lý.
7. API subscribe `alert-state` và giữ bản trạng thái mới nhất trong bộ nhớ. Web/app đọc trạng thái này để cập nhật công tắc.
8. Nếu không nhận lệnh tắt, Pi tự dừng sau 10 giây mặc định; giới hạn tối đa là 60 giây.

Retained chỉ áp dụng cho trạng thái, không áp dụng cho command, để Pi vừa kết nối lại không thực thi một lệnh cũ. Vì trạng thái API đang giữ trong bộ nhớ, khi API restart nó cần nhận lại retained `alert-state` từ broker.

## 6. Mất mạng và độ tin cậy

- Đứt MQTT không được chặn vòng lặp cảm biến hoặc cảnh báo cục bộ trên Pi.
- Publisher có outbox trong bộ nhớ, ưu tiên event hơn telemetry khi đầy; chưa có hàng đợi bền vững qua mất điện.
- QoS 1 có thể giao trùng, nên ingest phải idempotent.
- Trạng thái online/offline dùng Last Will/retained status và độ mới dữ liệu; không dựa chỉ vào việc có hàng trong DB.
- Command có timestamp, ID duy nhất, giới hạn thời lượng và cơ chế tự tắt trên Pi.
- Nếu backend mất kết nối sau khi đã bật, Pi vẫn tự tắt theo timeout.

Nếu yêu cầu không mất telemetry khi Pi mất điện/mạng dài, cần bổ sung outbox SQLite trên Pi và chiến lược gửi bù có giới hạn.

## 7. Local và cloud

| Nội dung | Local hiện tại | Cloud mục tiêu |
| --- | --- | --- |
| Pi | Chạy `health_watch/`, broker ở IP máy tính | Giữ edge runtime, broker qua DNS/TLS |
| Backend | Docker Compose trên Windows | Container/orchestrator, private network, monitoring |
| PostgreSQL | Container và volume local | Managed DB/private DB, backup/PITR |
| Web/API | HTTP trong LAN | HTTPS qua domain/reverse proxy |
| Android | APK debug cho phép HTTP | APK/AAB release ký số, chỉ HTTPS |
| Xác thực | Chưa có | Người dùng/thiết bị, phân quyền theo thiết bị |
| MQTT | Một tài khoản demo, chưa TLS | Credential riêng từng Pi, TLS và ACL topic |

Chi tiết tiêu chí cloud ở [infra/cloud/README.md](../infra/cloud/README.md).

## 8. Vị trí mở rộng Edge AI

Chỉ thêm AI sau khi có bài toán, dữ liệu gán nhãn và tiêu chí đánh giá rõ. Module đề xuất là `health_watch/inference/`, nhận dữ liệu cảm biến đã lấy trên Pi và trả kết quả gồm `model_name`, `model_version`, `confidence`, timestamp. Không ghi đè số đo gốc; lưu output AI như trường hoặc event có phiên bản để có thể kiểm toán và rollback.

## 9. Tiêu chí hoàn chỉnh cho bản local

- Mock đi hết luồng MQTT → ingest → PostgreSQL → API → web.
- Pi thật publish telemetry/event/status và duy trì phần cứng khi broker ngắt.
- Web và APK phân biệt online, offline, dữ liệu cũ và giá trị chưa đo được.
- Công tắc ON/OFF đi hết API → MQTT → Pi → `alert-state` → giao diện; lệnh bật trùng bị chặn và Pi tự tắt.
- Test đơn vị Pi, test backend và smoke test local đều qua.
- Secret nằm trong `.env` bị Git bỏ qua; không dùng dữ liệu sức khỏe thật trong repo.

Các điều trên chưa đồng nghĩa hệ thống đủ điều kiện dùng y tế hoặc public Internet.
