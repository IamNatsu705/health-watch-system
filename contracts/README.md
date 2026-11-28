# Hợp đồng dữ liệu

`contracts/` là nguồn chuẩn giữa Pi, ingest, API, web và Android.

- [`mqtt/`](mqtt/README.md): topic, JSON Schema và QoS.
- [`api/`](api/README.md): quy ước HTTP API.

Nguyên tắc:

- Không đưa secret vào schema hoặc ví dụ.
- Timestamp dùng UTC ISO 8601.
- Đơn vị phải rõ (`bpm`, mét, kcal).
- Schema đặt `additionalProperties: false`, nên **mọi** thay đổi trường (kể cả thêm
  trường tùy chọn) phải tạo version mới và cập nhật ingest trước khi Pi gửi.
- Giá trị không đo được là `null`; không dùng 0 hay số mẫu thay cho `null`.
- Producer và consumer phải được test với cùng contract trước deploy.
