# Kiến trúc Health Watch

## 1. Mục tiêu và nguyên tắc dữ liệu

Health Watch thu thập dữ liệu MPU6050/MAX30102 trên Raspberry Pi, xử lý và đếm bước
(có AI) ngay tại Pi, gửi MQTT tới backend Python, lưu PostgreSQL và hiển thị trên
web/Android. Người dùng có thể điều khiển LED đỏ/còi từ xa và nhập hồ sơ người đeo.

Nguyên tắc xuyên suốt: **chỉ dữ liệu thật**.

- Không có thiết bị giả lập trong hệ thống chạy. Mock publisher và smoke test ghi
  vào DB thật đã bị gỡ.
- Broker chỉ cho mỗi Pi ghi topic của chính nó; ingest chỉ nhận ID có trong
  `MQTT_DEVICES`.
- Không giá trị mẫu nào được trình bày như số đo. Chưa đo/ước tính được thì là `null`,
  và giao diện hiển thị `--`.
- Mỗi số liệu mang theo nguồn gốc: firmware, thuật toán, mô hình AI (tên + phiên bản),
  trạng thái IMU, trạng thái đồng hồ.
- Dữ liệu cũ luôn kèm tuổi dữ liệu; giao diện không trình bày nó như số hiện tại.

## 2. Sơ đồ runtime

```text
Raspberry Pi                                Máy tính local
┌────────────────────────────┐              ┌──────────────────────────────────┐
│ MPU6050 ─FIFO 100 Hz─┐     │              │ Mosquitto (tài khoản + ACL/Pi)   │
│                      ▼     │ telemetry v2 │   ├─→ ingest ─→ PostgreSQL       │
│ ImuStream → StepEngine ────┼─────────────►│   │   (schema, thiết bị đăng ký, │
│   ├─ peak-bout-v2          │ events/status│   │    bộ đếm hợp lý)            │
│   └─ WalkGate (AI, JSON)   │              │   │               ↑              │
│ MAX30102 → PulseMonitor    │◄─────────────┤   └─ commands / config ← FastAPI │
│ FallDetector, SOS, TFT     │ commands     │         alert-state →   ↑ HTTP   │
│ state/: bước hôm nay, hồ sơ│ config       │                  Web / Android   │
└────────────────────────────┘              └──────────────────────────────────┘
```

## 3. Đường dữ liệu bước chân

1. **Cảm biến:** MPU6050 lấy mẫu 100 Hz theo đồng hồ PLL, lọc thông thấp 44 Hz, ±8 g.
   Mẫu gia tốc + gyro nằm trong FIFO của chip (1024 byte ≈ 0,85 s), nên khi vòng lặp chính bị TFT chặn
   ~200 ms thì không mất mẫu.
2. **`ImuStream`:** đọc FIFO, gán thời gian đều 10 ms. Lớp này phát hiện tràn FIFO (đứt
   mẫu), I2C lỗi, chip tự reset/ngủ, dữ liệu đứng yên tuyệt đối và bão hòa, và tự khởi
   tạo lại cảm biến. Khi lỗi nó không trả mẫu nào, nên bộ đếm dừng tăng.
3. **`StepEngine`:** dùng độ lớn gia tốc, lọc thông dải 0,5–3 Hz.
   - `steps_algorithm`: đỉnh vượt ngưỡng thích nghi, chỉ được cộng khi có ≥6 đỉnh
     liên tiếp đều nhịp.
   - `steps_ai`: mỗi cửa sổ 5 s, `WalkGate` (Random Forest) quyết định có đang đi bộ
     hay không; nếu có thì cộng các đỉnh ứng viên trong cửa sổ.
4. **Pi:** lưu số bước hôm nay vào `state/daily_steps.json`, ước tính quãng đường/kcal
   nếu có hồ sơ, và gửi telemetry v2 mỗi giây.
5. **Ingest:** kiểm tra schema và format, chặn NaN/∞, chỉ nhận thiết bị đăng ký. Trong
   một `boot_id`, bộ đếm không được giảm và không được tăng nhanh hơn giới hạn vật lý.
6. **API:** chọn bản mới nhất theo **giờ server nhận** (Pi không có RTC), trả kèm
   `age_s`/`fresh`. `/steps/daily` cộng phần tăng của từng phiên theo ngày địa phương.
7. **Web/app:** hiển thị số hôm nay, nguồn đếm, độ mới dữ liệu, lỗi IMU.

Quy trình huấn luyện và kết quả đánh giá AI nằm ở [ml/README.md](../ml/README.md); cách
thu dữ liệu thật của nhóm ở [data-collection.md](data-collection.md).

## 4. Trách nhiệm từng thành phần

| Thành phần | Chịu trách nhiệm | Không chịu trách nhiệm |
| --- | --- | --- |
| `health_watch/` | Cảm biến, đếm bước + AI, BPM thử nghiệm, phát hiện ngã, TFT/GPIO, MQTT, lưu trạng thái ngày/hồ sơ | Không truy cập PostgreSQL hoặc phục vụ HTTP |
| `ml/` | Huấn luyện/đánh giá mô hình trên dữ liệu thật bằng chính mã của Pi, xuất JSON | Không chạy trên Pi |
| Mosquitto | Định tuyến MQTT; xác thực từng Pi; ACL theo thiết bị; giữ retained qua khởi động lại | Không thay thế kho lịch sử |
| `backend/ingest/` | Kiểm tra và ghi telemetry/event/status của thiết bị đăng ký | Không phục vụ dashboard hoặc GPIO |
| PostgreSQL | Thiết bị, telemetry (kèm nguồn gốc), sự kiện, hồ sơ, log hoạt động | Không mở trực tiếp cho web/app/Pi |
| `backend/api/` | REST API, tổng ngày, hồ sơ → MQTT `config`, lệnh cảnh báo, `alert-state` | Không đọc cảm biến hoặc điều khiển GPIO trực tiếp |
| `web/` | Dashboard web và APK | Không kết nối MQTT/DB trực tiếp |
| `contracts/` | Topic, schema, phiên bản | Không chứa secret hoặc logic runtime |

## 5. Luồng điều khiển và cấu hình

**Cảnh báo từ xa:** web/app gọi API. API kiểm tra thiết bị đang online và trạng thái còi,
rồi publish `commands` (QoS 1, không retained). Pi kiểm tra `command_id`/thời hạn, bật còi
+ LED đỏ, và publish retained `alert-state`. Pi tự tắt sau 10 s, tối đa 60 s.

**Hồ sơ người đeo:** web/app PUT/DELETE `/profile`. API lưu DB rồi publish retained
`config`. Mỗi lần kết nối broker, API publish lại cấu hình của mọi thiết bị đăng ký
(không có hồ sơ thì `null`). Pi kiểm tra phạm vi giá trị, bỏ cấu hình cũ hơn bản đang
dùng (`updated_at`), lưu `state/profile.json` và dùng ngay. Pi offline vẫn dùng hồ sơ
đã lưu.

## 6. Mất mạng và độ tin cậy

- Đứt MQTT không chặn đọc cảm biến, đếm bước hay cảnh báo cục bộ.
- Lỗi MAX30102 không làm dừng đếm bước. Lỗi MPU6050 được báo `imu_status` và cảm biến
  tự khởi tạo lại, chương trình không thoát.
- Outbox MQTT trong RAM ưu tiên event; khi dừng có kiểm soát thì gửi nốt bản tin còn chờ
  (tối đa 3 s). Chưa có hàng đợi bền khi mất điện; số bước hôm nay trên Pi được lưu mỗi 10 s.
- QoS 1 có thể giao trùng: khóa `(device_id, boot_id, sequence)` và `event_id` chống ghi trùng.
- Last Will của phiên cũ đến muộn không đánh dấu phiên mới là offline. Status retained
  do broker giao lại khi ingest kết nối không làm thiết bị hiện "online".
- Ingest/API dùng client ID có hậu tố ngẫu nhiên để thiết bị khác không chiếm được kết nối.
- Pi không có RTC: trước khi NTP đồng bộ, số bước trên Pi là "từ khi bật máy", không
  gán vào ngày đoán sai. Backend chia ngày theo giờ server nhận.

## 7. Local và cloud

| Nội dung | Local hiện tại | Cloud mục tiêu |
| --- | --- | --- |
| Pi | `health_watch/`, broker ở IP máy tính | Broker qua DNS/TLS |
| MQTT | Tài khoản + ACL theo thiết bị, chưa TLS | Thêm TLS, quản lý credential |
| Backend/DB | Docker Compose trên Windows | Container, managed DB, backup |
| Web/API | HTTP trong LAN | HTTPS, đăng nhập, phân quyền theo thiết bị |

Chi tiết ở [infra/cloud/README.md](../infra/cloud/README.md).

## 8. Tiêu chí hoàn chỉnh

- Pi thật gửi telemetry v2, có `step_model` khác null, `imu_status=ok`; dashboard hiện số
  bước hôm nay với nguồn "AI".
- Không có thiết bị nào ngoài `MQTT_DEVICES` trong DB hoặc giao diện.
- Test Pi (`health_watch/tests`) và backend (`backend/tests`) qua; `npm run build` qua.
- Sai số đếm bước trên dữ liệu ghi của nhóm đạt tiêu chí ở
  [data-collection.md](data-collection.md). Đây là bước cần làm trên thiết bị thật.

Các điều trên chưa đồng nghĩa hệ thống đủ điều kiện dùng y tế hoặc công khai trên Internet.
