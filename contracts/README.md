# Hợp đồng dữ liệu dùng chung

`mqtt/` là nguồn chuẩn cho topic, trường và phiên bản bản tin từ Pi tới backend. Pi tạo payload theo hợp đồng này; ingest phải kiểm tra nó trước khi ghi DB. [Xem MQTT v1](mqtt/README.md).

`api/` sẽ lưu mô tả OpenAPI được xuất từ FastAPI khi API hoạt động. Web dùng mô tả đó để thống nhất kiểu dữ liệu với backend; không tự đặt tên trường khác.

Nguyên tắc: thay đổi tương thích có thể thêm trường tùy chọn; thay đổi tên/ý nghĩa trường, đơn vị đo hoặc xóa trường bắt buộc cần phiên bản mới. `schema_version` đi cùng từng bản tin. Không đặt khóa bí mật vào contract.
