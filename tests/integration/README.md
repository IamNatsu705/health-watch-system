# Kiểm tra tích hợp dự kiến

Các test ở đây sẽ kiểm tra đường đi của dữ liệu sau khi broker, ingest và API tồn tại. Chưa có test tích hợp chạy được trong bộ khung hiện tại.

Các kịch bản tối thiểu:

1. Publish một telemetry hợp schema → ingest ghi PostgreSQL → API trả đúng `latest` và `history`.
2. Publish cùng `(device_id, boot_id, sequence)` hai lần → chỉ có một hàng DB.
3. Publish một event `fall_detected`, rồi lại cùng `event_id` → chỉ có một sự kiện.
4. Publish dữ liệu sai schema hoặc `device_id` không khớp topic → bị từ chối và có log chẩn đoán.
5. Pi/broker ngắt kết nối → API hiển thị thời điểm cuối, web/Android đánh dấu offline; phần cảnh báo trên Pi vẫn chạy.
6. Người dùng không được gán thiết bị → API không trả dữ liệu thiết bị đó.

Test logic Pi hiện có vẫn nằm trong `health_watch/tests/` và có thể chạy riêng mà không cần broker hay PostgreSQL.
