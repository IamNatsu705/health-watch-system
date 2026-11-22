# Mock Raspberry Pi

`mock-pi` cho phép kiểm thử broker → ingest → PostgreSQL → API → web mà không
có Raspberry Pi.

## Dữ liệu tạo ra

- Telemetry mỗi giây.
- BPM dao động giả lập; có lúc `finger_present=false`, BPM `null`.
- Bước tăng theo thời gian; mét/kcal tính từ bước.
- Chu kỳ event 60 giây: `fall_detected`, `fall_acknowledged`, `sos_pressed`,
  `sos_released`.
- Status online/offline retained.

Mock **không** mô phỏng `commands`, GPIO hoặc `alert-state`. Vì vậy công tắc
còi trên web/app bị khóa với mock; hãy dùng Pi thật để test điều khiển hai chiều.

## Chạy

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml --profile mock up --build -d
docker compose --env-file infra/local/.env -f infra/local/compose.yaml --profile mock logs -f mock-pi
```

ID lấy từ `MOCK_DEVICE_ID`, mặc định `pi-watch-mock-001`.

## Tắt trước khi dùng Pi thật

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml --profile mock stop mock-pi
```

Mock chỉ phục vụ kiểm thử phần mềm; không dùng số liệu mock để đánh giá cảm
biến hoặc thuật toán sức khỏe.
