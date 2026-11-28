# Kế hoạch chuyển Health Watch lên cloud

Thư mục này hiện **chưa có Terraform, Kubernetes, VM setup hoặc cloud
deployment chạy thật**. README là checklist thiết kế để tránh đưa cấu hình
local thiếu bảo mật lên Internet.

## 1. Kiến trúc mục tiêu

```text
Raspberry Pi ── MQTT TLS ──► Cloud MQTT broker ──► ingest ──► PostgreSQL
       ▲                            ▲                              │
       └──── commands/alert-state ──┘                              ▼
Web HTTPS / Android HTTPS ─────────────────────────────────────► API
```

Pi vẫn xử lý cảm biến/cảnh báo tại chỗ. Cloud chạy broker, ingest, database,
API và host web. APK gọi API bằng domain HTTPS, không dùng IP LAN.

## 2. Điều kiện bắt buộc trước khi triển khai

### MQTT

- TLS server certificate và kiểm tra hostname.
- Credential riêng cho từng Pi; không dùng tài khoản chung local.
- ACL theo topic. Pi chỉ publish telemetry/event/status/alert-state của chính
  nó và chỉ subscribe commands của chính nó.
- Giới hạn payload, connection rate, publish rate và session timeout.
- Theo dõi connect/disconnect, auth failure và retained message.

### API và người dùng

- HTTPS bắt buộc; không cho HTTP cleartext.
- Đăng nhập, access token ngắn hạn và refresh token an toàn.
- Phân quyền user ↔ device ở mọi endpoint, kể cả remote command.
- Rate limit command, audit ai bật/tắt còi và chống replay.
- CORS chỉ cho domain chính thức.
- Không tin `session_id` ẩn danh hiện tại như danh tính người dùng.

### PostgreSQL

- Không public port database ra Internet.
- Managed DB hoặc private network.
- Migration trước deploy, backup tự động, point-in-time recovery nếu cần.
- Kiểm tra phục hồi backup định kỳ; mã hóa ổ đĩa và secret rotation.
- Chính sách retention cho telemetry/event/user activity.

### Vận hành

- Healthcheck, log tập trung, metric, dashboard và alert.
- Theo dõi lag ingest, lỗi schema, Pi offline và command không ACK.
- Rolling/blue-green deploy và phương án rollback.
- Đồng bộ UTC/NTP ở Pi và server.
- Tách dev/staging/production và tách credential.

## 3. Secret cần đưa ra khỏi source

| Secret | Nơi lưu cloud đề xuất |
| --- | --- |
| PostgreSQL password/URL | Secret manager của cloud |
| MQTT credential thiết bị | Provisioning service/secret manager |
| TLS private key | Certificate/secret manager |
| JWT signing key | KMS/secret manager |
| Android signing key | CI secret + kho lưu ngoại tuyến |

Không commit `.env`, keystore, certificate private key hoặc database dump.

## 4. Thay đổi cấu hình khi chuyển môi trường

- Pi: `MQTT_HOST`, `MQTT_PORT`, credential và cấu hình TLS.
- API/ingest: `DATABASE_URL`, MQTT TLS URL/credential, auth config.
- Web/Android: API base URL HTTPS.
- Mosquitto local không dùng nguyên trạng cho production.

MQTT topic/schema v1 có thể giữ nguyên. Thay đổi không tương thích cần version
mới, không sửa âm thầm payload đang dùng.

## 5. Lộ trình đề xuất

1. Tạo staging cloud với dữ liệu giả.
2. Thêm TLS/ACL MQTT và credential riêng cho một Pi thử nghiệm.
3. Thêm bảng user/device assignment và auth API.
4. Chạy migration, backup/restore drill và kiểm tra đầu-cuối bằng Pi thật.
5. Build web production và APK/AAB release ký chính thức.
6. Thử mất mạng, reconnect, duplicate QoS 1, clock lệch và command timeout.
7. Chỉ sau đó mới đưa thiết bị thật lên production.

## 6. Tiêu chí hoàn thành

- Không service dữ liệu nào public ngoài HTTPS và MQTT TLS cần thiết.
- Người dùng chỉ đọc/điều khiển thiết bị được cấp quyền.
- Một Pi không thể publish/subscribe topic của Pi khác.
- Backup khôi phục được, migration rollback có kế hoạch.
- Command có audit, ACK/timeout rõ ràng và không bật lặp.
- Có cảnh báo khi Pi, ingest, API hoặc DB bất thường.
