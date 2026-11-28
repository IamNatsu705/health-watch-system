# Web dashboard và ứng dụng Android

Thư mục này chứa một giao diện Vue 3 dùng chung cho:

- dashboard web chạy bằng Vite tại `http://localhost:5173`;
- ứng dụng Android được đóng gói bằng Capacitor 8;
- màn hình theo dõi thiết bị, số đo, lịch sử, sự kiện và điều khiển cảnh báo từ xa.

Giao diện chỉ gọi FastAPI. Nó không kết nối trực tiếp tới MQTT hoặc PostgreSQL.

## 1. Cấu trúc

| Đường dẫn | Chức năng |
| --- | --- |
| `src/` | Mã Vue, CSS và logic gọi API |
| `android/` | Dự án Android do Capacitor tạo |
| `vite.config.js` | Cấu hình Vite và proxy API khi chạy web local |
| `capacitor.config.json` | Cấu hình đóng gói ứng dụng Android |
| `package.json` | Lệnh cài, chạy, build và đồng bộ Android |

## 2. Chạy web bằng Docker Compose

Từ thư mục gốc dự án:

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml up --build -d
```

Mở <http://localhost:5173>. Mã nguồn `web/` được mount vào container nên phần lớn thay đổi giao diện sẽ được Vite cập nhật tự động.

Nếu trình duyệt vẫn giữ bản cũ, dùng `Ctrl+F5` hoặc chạy:

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml restart web
```

## 3. Chạy web trực tiếp bằng Node.js

Yêu cầu Node.js 20 trở lên. Từ `web/`:

```powershell
npm.cmd install
npm.cmd run dev
```

Proxy mặc định chuyển `/api` tới `http://localhost:8000`, vì vậy backend phải đang chạy. Muốn thử trên điện thoại cùng LAN, mở:

```text
http://<IP-LAN-của-máy-tính>:5173
```

Ví dụ trong mạng đã dùng khi triển khai: `http://172.20.10.11:5173`. Không dùng địa chỉ ví dụ nếu IP hiện tại đã thay đổi; kiểm tra bằng `ipconfig`.

## 4. Cách dùng dashboard

1. Chọn thiết bị trong danh sách. Danh sách chỉ có Pi đã đăng ký (`MQTT_DEVICES`);
   thiết bị đang gửi dữ liệu được xếp lên đầu, và lựa chọn được nhớ lại.
2. Kiểm tra trạng thái online và thời điểm server nhận dữ liệu cuối.
3. **Bước chân**: tổng hôm nay (theo `/steps/daily`), nguồn đếm (AI + phiên bản mô hình,
   hoặc thuật toán khi Pi chưa nạp mô hình), trạng thái đang đi bộ/nhịp bước, số đếm
   của phiên hiện tại. Biểu đồ 7 ngày ở bên dưới.
4. **Quãng đường/kcal**: nhập chiều cao, cân nặng thật (và có thể nhập chiều dài bước tự
   đo) ở mục **Hồ sơ người đeo**. Chưa có hồ sơ thì hiển thị `--`.
5. `--` nghĩa là chưa có phép đo/ước tính hợp lệ, không phải 0.
6. Dữ liệu làm mới khoảng 3 giây. Khi Pi ngừng gửi, các thẻ mờ đi kèm dòng "không gửi
   dữ liệu mới từ …". Khi API lỗi, số liệu bị xóa khỏi màn hình thay vì đứng yên ở số cũ.
7. Lỗi cảm biến chuyển động (MPU6050) hiện thành cảnh báo đỏ; khi đó bước chân không
   được đếm.
8. Mục **"Có AI và không AI"** (bấm "Ẩn so sánh" để ẩn; trình duyệt nhớ lựa chọn):
   - trực tiếp từ Pi: số bước hôm nay có AI và không AI, đường cộng dồn của phiên đang
     chạy, cột 7 ngày; Pi luôn gửi cả hai bộ đếm;
   - kiểm định trên dữ liệu thật có video (OxWalk, Clemson): sai số thuật toán cũ, thuật
     toán mới và AI, cùng 2 ví dụ 60 giây. Số liệu ở `src/data/step_evaluation.json` do
     `ml/plot_comparison.py` sinh ra, không nhập tay.

### Công tắc cảnh báo ON/OFF

Công tắc điều khiển LED đỏ và còi trên đúng Raspberry Pi đang chọn:

- **OFF → ON**: API gửi lệnh MQTT; giao diện hiển thị trạng thái đang chờ cho tới khi Pi xác nhận.
- **ON**: Pi đã báo trạng thái còi đang bật. Giao diện không gửi thêm lệnh bật trùng.
- **ON → OFF**: gửi lệnh tắt sớm.
- Pi tự tắt sau 10 giây mặc định nếu không có lệnh khác; thời lượng tối đa API chấp nhận là 60 giây.
- Công tắc bị vô hiệu hóa khi thiết bị offline, chưa xác định được trạng thái cảnh báo hoặc đang chờ phản hồi.

Trạng thái trên giao diện là trạng thái Pi xác nhận qua topic `alert-state`, không phải phỏng đoán từ lần bấm gần nhất. Nếu giao diện kẹt ở “đang chờ”, xem mục xử lý lỗi phía dưới.

## 5. Build APK debug

Yêu cầu:

- Node.js 20 trở lên;
- JDK 21;
- Android SDK, Android platform API 36 và build-tools 35;
- biến môi trường Android SDK được cấu hình nếu Gradle không tự tìm thấy.

Từ thư mục `web/`:

```powershell
npm.cmd install
npm.cmd run android:apk
```

Lệnh này build Vue, đồng bộ tài nguyên sang Capacitor và build APK tại:

```text
web/android/app/build/outputs/apk/debug/app-debug.apk
```

Repo cũng có thể chứa bản sao tiện cài ở thư mục gốc: `HealthWatch-debug.apk`. Khi giao diện thay đổi, phải build lại; không mặc định coi bản APK cũ là mới nhất.

Chỉ đồng bộ mã web sang dự án Android mà chưa build APK:

```powershell
npm.cmd run android:sync
```

## 6. Cài và cấu hình app Android

Cài qua ADB khi đã bật USB debugging:

```powershell
adb install -r .\android\app\build\outputs\apk\debug\app-debug.apk
```

Điện thoại và máy chạy backend phải ở cùng mạng. Trong app, nhập API theo dạng:

```text
http://<IP-LAN-của-máy-tính>:8000
```

Sau đó nhấn **Lưu và kết nối**. Không nhập `localhost`, vì trên điện thoại địa chỉ đó trỏ về chính điện thoại. Windows Firewall phải cho phép TCP 8000 trên mạng Private.

## 7. Kiểm tra sau khi sửa giao diện

```powershell
Set-Location C:\Project\health_watch_system\web
npm.cmd run build
npm.cmd run android:apk
```

Kiểm tra thủ công cả web và app:

- danh sách thiết bị và số đo tải được;
- trạng thái offline/dữ liệu cũ hiển thị đúng;
- công tắc chuyển qua trạng thái chờ, ON rồi tự về OFF sau khi Pi xác nhận;
- bấm ON khi đã ON không tạo lệnh trùng;
- APK truy cập được API bằng IP LAN.

## 8. Xử lý lỗi

| Hiện tượng | Cách kiểm tra |
| --- | --- |
| Web báo không gọi được API | `Invoke-RestMethod http://localhost:8000/health`; xem log container `api` |
| Điện thoại không kết nối | Dùng IP LAN thay vì `localhost`; kiểm tra cùng Wi-Fi và firewall TCP 8000 |
| Không thấy giao diện mới | `Ctrl+F5`, restart container web; APK phải được build và cài lại |
| Công tắc bị khóa | Kiểm tra thiết bị online và trạng thái `alert-state` |
| Bước chân/quãng đường hiện `--` | Chưa có dữ liệu v2 hôm nay, hoặc chưa nhập hồ sơ người đeo (quãng đường/kcal) |
| Thẻ số đo bị mờ, ghi "Dữ liệu cũ" | Pi ngừng gửi; số hiển thị là lần đo cuối, không phải hiện tại |
| Công tắc chờ quá lâu | Xem log API, Mosquitto và `journalctl -u health-watch`; kiểm tra credential MQTT |
| Pi đã tắt nhưng web vẫn ON | Kiểm tra Pi có publish retained `alert-state` và API có kết nối MQTT hay không |

## 9. Giới hạn bảo mật

APK debug đang cho phép HTTP cleartext để thử trong LAN. Cấu hình local chưa có đăng nhập người dùng và CORS còn mở. Trước khi phát hành thật cần HTTPS, xác thực/phân quyền, giới hạn CORS, API domain cố định, APK/AAB release được ký và cất keystore ngoài Git.
