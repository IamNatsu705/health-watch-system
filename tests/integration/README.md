# Kiểm tra tích hợp đầu-cuối

Kiểm tra đầu-cuối chỉ làm với Raspberry Pi thật, không có thiết bị giả lập. Các
kiểm tra tự động (schema, chống trùng, từ chối dữ liệu sai) nằm trong `backend/tests`.

## 1. Bước chân trên Pi thật

1. Start `health-watch.service` trên Pi. Log có `Đã nạp mô hình walk-gate-rf 1.0.0` và
   `MPU6050 ok`.
2. Xác nhận status MQTT online và telemetry tăng sequence.
3. Kiểm tra ingest ghi đúng `MQTT_DEVICE_ID`. Log không có `Rejected`.
4. Để thiết bị yên 2 phút: số bước không tăng.
5. Đeo ở cổ tay, đi 100 bước đếm tay: số bước AI trên TFT/web tăng khoảng 100. Ghi phiên
   bằng `record_imu.py` để có số liệu chính xác.
6. Ngồi gõ phím và khua tay 2 phút: số bước AI gần như không tăng.
7. Thử lỗi cảm biến an toàn: tắt nguồn Pi, tháo dây SDA của MPU6050 rồi bật lại. TFT
   phải hiện `LỖI CẢM BIẾN`, web hiện cảnh báo IMU, số bước không tăng và chương trình
   không thoát. Tắt nguồn, cắm lại dây, bật lại: mọi thứ hoạt động bình thường.
8. Nhập hồ sơ người đeo trên web: TFT/web hiện quãng đường và kcal; xóa hồ sơ thì trở về `--`.
9. Khởi động lại service: số bước hôm nay trên TFT giữ nguyên; tổng hôm nay trên web
   không bị đếm lại từ 0.

## 2. Mạng và dữ liệu

1. Kiểm tra API `devices`, `latest`, `history`, `steps/daily`, `events`.
2. Mở web và APK, kiểm tra số đo/thời điểm cập nhật thống nhất.
3. Nhấn SOS có kiểm soát, xác nhận event xuất hiện.
4. Ngắt broker ngắn: Pi vẫn chạy phần cứng; giao diện chuyển offline/dữ liệu cũ (thẻ mờ,
   ghi rõ tuổi dữ liệu).
5. Kết nối lại: status/telemetry phục hồi mà không tạo bản ghi trùng.

## 3. Tích hợp công tắc cảnh báo

Với Pi online:

1. Lấy trạng thái ban đầu OFF từ retained `alert-state`.
2. Gạt ON; API trả chấp nhận, Pi bật LED đỏ/còi và publish ON.
3. Khi ON, thử gửi ON lần nữa; giao diện khóa và API từ chối lệnh lặp.
4. Gạt OFF; Pi tắt ngay và publish OFF.
5. Gạt ON rồi để yên; Pi tự tắt sau khoảng 10 giây.
6. Restart API; API phải khôi phục trạng thái từ retained `alert-state`.
7. Xác nhận command không retained: restart Pi không được tự bật lại từ lệnh cũ.
8. Thử publish vào topic của Pi bằng tài khoản backend hoặc tài khoản Pi khác: broker
   từ chối (ACL), DB không có dữ liệu mới.

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
