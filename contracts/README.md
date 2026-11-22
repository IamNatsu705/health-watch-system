# Hợp đồng dữ liệu

`contracts/` là nguồn chuẩn giữa Pi, mock, ingest, API, web và Android.

- [`mqtt/`](mqtt/README.md): topic, JSON Schema và QoS.
- [`api/`](api/README.md): quy ước HTTP API.

Nguyên tắc:

- Không đưa secret vào schema hoặc ví dụ.
- Timestamp dùng UTC ISO 8601.
- Đơn vị phải rõ (`bpm`, mét, kcal).
- Thêm trường tùy chọn có thể giữ version; đổi tên/ý nghĩa/đơn vị hoặc xóa
  trường bắt buộc phải tạo version mới.
- Producer và consumer phải được test với cùng contract trước deploy.
