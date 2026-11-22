# Kiểm tra tích hợp đầu-cuối

Repo có smoke test local chạy được và một checklist thủ công cho Raspberry Pi thật.

## 1. Smoke test tự động với mock

```powershell
Set-Location C:\Project\health_watch_system
docker compose --env-file infra/local/.env -f infra/local/compose.yaml --profile mock up --build -d
docker compose --env-file infra/local/.env -f infra/local/compose.yaml exec -T ingest python -m backend.smoke_local
```

Bài test kiểm tra:

1. payload telemetry hợp schema;
2. ingest ghi PostgreSQL;
3. API trả latest/history;
4. publish trùng `(device_id, boot_id, sequence)` không tạo thêm hàng;
5. event trùng `event_id` không tạo thêm sự kiện;
6. payload sai bị từ chối và có log phù hợp.

## 2. Tích hợp với Raspberry Pi thật

Trước khi thử, dừng mock:

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml --profile mock stop mock-pi
```

Sau đó:

1. Start `health-watch.service` trên Pi.
2. Xác nhận status MQTT online và telemetry tăng sequence.
3. Kiểm tra ingest ghi đúng `MQTT_DEVICE_ID`.
4. Kiểm tra API `devices`, `latest`, `history`, `events`.
5. Mở web và APK, kiểm tra số đo/thời điểm cập nhật thống nhất.
6. Nhấn SOS có kiểm soát, xác nhận event xuất hiện.
7. Ngắt broker ngắn: Pi vẫn chạy phần cứng; giao diện chuyển offline/dữ liệu cũ.
8. Kết nối lại: status/telemetry phục hồi mà không tạo bản ghi trùng.

## 3. Tích hợp công tắc cảnh báo

Với Pi online:

1. Lấy trạng thái ban đầu OFF từ retained `alert-state`.
2. Gạt ON; API trả chấp nhận, Pi bật LED đỏ/còi và publish ON.
3. Khi ON, thử gửi ON lần nữa; giao diện khóa và API từ chối lệnh lặp.
4. Gạt OFF; Pi tắt ngay và publish OFF.
5. Gạt ON rồi để yên; Pi tự tắt sau khoảng 10 giây.
6. Restart API; API phải khôi phục trạng thái từ retained `alert-state`.
7. Xác nhận command không retained: restart Pi không được tự bật lại từ lệnh cũ.
8. Xác nhận mock không cho phép điều khiển.

Theo dõi:

```bash
sudo journalctl -u health-watch -f
```

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml logs -f api mosquitto ingest
```

## 4. Kịch bản lỗi bắt buộc

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Payload sai schema/device topic không khớp | Ingest từ chối và ghi log, không crash |
| Giao lại QoS 1 | DB không sinh hàng trùng |
| Pi mất mạng | UI báo offline; cảnh báo local và auto-off vẫn hoạt động |
| API mất MQTT | Endpoint điều khiển trả lỗi khả dụng, không giả báo thành công |
| Lệnh quá cũ/sai thiết bị | Pi bỏ qua và không đổi GPIO |
| Người dùng không có quyền | Chưa thể xác nhận ở bản local vì auth chưa triển khai; đây là điều kiện trước cloud |

Không tạo cú ngã của người thật để kiểm thử. Việc xác nhận thuật toán ngã và BPM cần một kế hoạch dữ liệu/đối chiếu riêng.
