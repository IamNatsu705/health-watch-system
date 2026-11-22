# Kiến trúc Health Watch

## 1. Mục tiêu của bản đầu

Thu thập số đo đã xử lý trên Raspberry Pi, lưu theo thời gian ở PostgreSQL và hiển thị cho người dùng trên web/Android. Bản đầu chỉ dùng logic cảm biến hiện có; chưa có mô hình AI và chưa coi BPM, bước hay phát hiện ngã là phép đo y tế.

## 2. Nơi chạy của từng thành phần

```text
Raspberry Pi                         Máy tính local / máy chủ cloud
┌──────────────────────┐              ┌──────────────────────────────────┐
│ MPU6050 + MAX30102   │              │ Mosquitto (MQTT broker)          │
│ Nút SOS              │              │       │                          │
│          ↓           │  MQTT        │       ↓                          │
│ health_watch/main.py ├─────────────→│ backend/ingest → PostgreSQL       │
│   ├→ TFT             │              │                         ↑        │
│   ├→ LED/còi         │              │                  backend/api      │
│   └→ MQTT publisher  │              └─────────────────────────┬────────┘
└──────────────────────┘                                        │ HTTP(S)
                                                      ┌─────────┴─────────┐
                                                      │ web / Android APK │
                                                      └───────────────────┘
```

Bản local đã triển khai broker, PostgreSQL, ingest, API và web trên máy tính. `backend/mock_publisher/` đóng vai Pi để thử không cần phần cứng; `health_watch/` đã có publisher MQTT nền và cấu hình qua biến môi trường để thay mock bằng Pi thật trong LAN. Android APK và Edge AI chưa triển khai. Khi đưa server lên cloud, giữ hợp đồng bản tin và API nhưng cần thêm bảo mật như mục 7.

## 3. Trách nhiệm và ranh giới

| Thành phần | Sở hữu việc gì | Không làm gì |
| --- | --- | --- |
| `health_watch/` | Đọc cảm biến, tính bước/BPM thử nghiệm/ngã, điều khiển TFT và cảnh báo, tạo bản tin MQTT | Không kết nối PostgreSQL, không phục vụ HTTP cho người dùng |
| Mosquitto | Nhận và phân phối bản tin MQTT giữa Pi với ingest | Không lưu lịch sử sức khỏe để truy vấn |
| `backend/ingest/` | Subscribe, kiểm tra schema, chống ghi trùng, lưu telemetry/events | Không xử lý đăng nhập hoặc trả dashboard |
| PostgreSQL | Lưu thiết bị, số đo, sự kiện, nhật ký hoạt động; bảng người dùng chỉ thêm khi triển khai đăng nhập | Không nhận kết nối trực tiếp từ web/Android |
| `backend/api/` | Truy vấn dữ liệu, trả HTTP API, ghi log phiên trình duyệt ẩn danh; xác thực/phân quyền là bước tiếp theo | Không đọc GPIO, không subscribe MQTT trong cùng tiến trình API |
| `web/` | Hiển thị dashboard, lịch sử ngắn, sự kiện; có thể dùng làm cơ sở cho APK sau này | Không tự tính lại số đo, không kết nối MQTT/DB trực tiếp |
| `contracts/` | Nguồn chuẩn cho topic, schema MQTT và quy tắc phiên bản | Không chứa bí mật hay logic phần cứng |

## 4. Luồng một phép đo

1. Pi đọc MPU6050 khoảng mỗi 40 ms và lấy dữ liệu MAX30102 từ FIFO như code hiện tại.
2. Pi xử lý tại chỗ. TFT, nút, LED/còi tiếp tục hoạt động ngay cả khi mất mạng.
3. Publisher gửi một bản tổng hợp khoảng mỗi giây tới `health/v1/devices/{device_id}/telemetry`. Không gửi luồng gia tốc thô 25 Hz trong bản đầu.
4. Ingest kiểm tra `schema_version`, ID thiết bị, kiểu dữ liệu và thời gian; ghi PostgreSQL. Khóa `(device_id, boot_id, sequence)` chặn bản tin bị giao lại do MQTT QoS 1.
5. API trả số đo mới nhất và lịch sử cho web/Android. Bản đầu có thể lấy mới nhất mỗi 2–5 giây; chỉ cần WebSocket nếu có yêu cầu độ trễ thấp hơn.

Ngã, SOS và xác nhận ngã đi theo topic `events` với `event_id` riêng. `null` ở BPM nghĩa là chưa đo được, không phải 0 BPM. Số bước hiện tại là số bước của phiên chạy, chưa phải tổng ngày.

## 5. Hợp đồng và dữ liệu

- Topic, trường bắt buộc và ví dụ nằm tại [contracts/mqtt/README.md](../contracts/mqtt/README.md).
- Schema JSON v1 hiện được ingest và mock publisher sử dụng; Pi thật sẽ dùng cùng hợp đồng khi tích hợp publisher.
- Tất cả timestamp dùng UTC ISO 8601. Pi cần đồng bộ giờ; backend lưu thêm thời điểm nhận để phát hiện đồng hồ thiết bị sai.
- Telemetry ghi các cột có kiểu rõ ràng cho các giá trị cần tìm kiếm/đồ thị. Bảng event lưu loại sự kiện; bản local chưa có payload phụ. Bảng `user_activity_logs` lưu `session_id` ẩn danh và hành động trình duyệt, không chứa mật khẩu/token hay `user_id` thật.
- Dữ liệu mẫu và dữ liệu người dùng thật phải tách biệt. Không dùng các ảnh `preview_*.png` làm bằng chứng số đo thật.

## 6. Mất mạng và độ tin cậy

Đứt MQTT không được làm gián đoạn vòng lặp phần cứng. Publisher nên có timeout và không gọi kết nối mạng đồng bộ trong đoạn đọc cảm biến. MQTT QoS 1 giúp giao nhận nhưng không bảo đảm dữ liệu tồn tại qua mọi lần Pi mất điện; nếu yêu cầu không mất dữ liệu, thêm hàng đợi trên đĩa ở Pi và gửi bù sau khi nối lại. Ingest phải chống trùng trong CSDL. Mọi cảnh báo tại chỗ được xử lý trên Pi, không phụ thuộc phản hồi cloud.

## 7. Local và cloud

| Nội dung | Local | Cloud |
| --- | --- | --- |
| Pi | Có thể dùng `mock-pi` hoặc chạy `health_watch/` trực tiếp trên Pi với publisher nền | Vẫn chạy trên Pi |
| Broker/ingest/API/PostgreSQL | Docker Compose trên máy tính | Máy chủ/managed service với TLS, sao lưu, giám sát |
| Web | Vite trên máy tính | Host giao diện qua HTTPS |
| Android | Chưa triển khai APK | APK gọi API qua tên miền HTTPS sau khi triển khai |
| Cấu hình | Địa chỉ LAN qua file môi trường riêng | Tên miền, credential thiết bị riêng, quyền topic |

Không mở PostgreSQL trực tiếp ra Internet. Mỗi Pi cần định danh và credential riêng trước khi kết nối broker cloud. API phải kiểm tra người dùng được phép xem thiết bị nào.

## 8. Chỗ dành cho Edge AI

Sau khi xác định bài toán và có dữ liệu kiểm chứng, thêm module `health_watch/inference/` đọc dữ liệu đã lấy trên Pi. Kết quả model được lưu như trường/sự kiện có `model_name`, `model_version`, `confidence` và timestamp, không ghi đè số đo gốc. Bản đầu chưa tạo thư mục hay kết quả AI giả để tránh nhầm lẫn với tính năng đã có.

## 9. Điều kiện để xem bản local là hoàn chỉnh

- Bản mock local: MQTT → ingest → PostgreSQL → API → web chạy được; bài `backend/smoke_local.py` kiểm tra schema và chống ghi trùng.
- Web phân biệt trạng thái mất kết nối/dữ liệu cũ với số đo mới; bản local không có APK.
- Trước khi nối Pi thật: publisher không làm gián đoạn TFT/LED/còi khi tắt broker.
- Trước khi dùng dữ liệu thật/cloud: API chỉ trả thiết bị mà người dùng được quyền xem; MQTT TLS, quyền topic, HTTPS, backup và giám sát đầy đủ.
