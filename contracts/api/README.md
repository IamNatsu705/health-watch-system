# Hợp đồng HTTP API v1

FastAPI chạy thật là nguồn chuẩn và tự sinh OpenAPI tại:

```text
http://localhost:8000/openapi.json
http://localhost:8000/docs
```

Mọi endpoint ứng dụng nằm dưới `/api/v1`; `/health` dành cho healthcheck.
Danh sách endpoint, request, response và mã lỗi nằm tại
[backend/api/README.md](../../backend/api/README.md).

Có thể xuất OpenAPI để review hoặc sinh client:

```powershell
Invoke-WebRequest http://localhost:8000/openapi.json -OutFile contracts/api/openapi.json
```

Chỉ commit file OpenAPI xuất ra khi nhóm quyết định quản lý snapshot; phải cập
nhật nó cùng thay đổi API. Web hiện gọi API bằng wrapper `web/src/api.js`, chưa
sinh TypeScript client tự động.

Quy ước lỗi FastAPI:

```json
{ "detail": "Mô tả lỗi" }
```

Web/app phải dựa vào HTTP status và `detail`, không suy đoán từ text giao diện.
