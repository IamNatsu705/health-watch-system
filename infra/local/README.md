# Chạy môi trường local

Docker Compose ở [compose.yaml](compose.yaml) gồm PostgreSQL, Mosquitto, migration, MQTT ingest, FastAPI, Vite web và mock publisher (profile `mock`). Xem lệnh chạy đầy đủ ở [README gốc](../../README.md).

```powershell
Copy-Item .\.env.example .\.env
docker compose --env-file .env -f compose.yaml --profile mock up --build -d
docker compose --env-file .env -f compose.yaml ps
```

Các lệnh trên chạy khi đang đứng trong `infra/local/`. Nếu đứng ở thư mục dự án gốc, dùng đường dẫn trong README gốc. `.env` được Git bỏ qua; `.env.example` chứa mật khẩu demo để thử local. Broker mở cổng `1883`, API `8000`, web `5173`; PostgreSQL chỉ ở mạng nội bộ Compose.

Khi đổi mật khẩu PostgreSQL sau lần khởi tạo đầu, volume DB cũ vẫn giữ mật khẩu ban đầu; cần đổi mật khẩu trong DB hoặc tạo một môi trường dữ liệu mới có chủ ý. `docker compose down` không xóa volume. Không dùng `down -v` nếu muốn giữ dữ liệu.
