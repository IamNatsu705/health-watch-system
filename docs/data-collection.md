# Thu dữ liệu thật để kiểm định và huấn luyện AI đếm bước

Mô hình hiện tại được huấn luyện và đánh giá trên dữ liệu thật của người khác, đo
bằng cảm biến khác (xem [ml/README.md](../ml/README.md)). Tài liệu này hướng dẫn
nhóm ghi dữ liệu bằng **chính MPU6050 của thiết bị** để:

1. đo sai số thật của hệ thống trên phần cứng của nhóm;
2. huấn luyện lại mô hình với cả dữ liệu đó (`--team`).

## 1. Chuẩn bị

- Cố định thiết bị lên **cổ tay** người đeo bằng dây đeo hoặc băng dán, để mạch không
  lỏng và dây I2C không tuột. Ghi rõ tay trái hay tay phải.
- Hướng gắn cảm biến không quan trọng, vì mô hình chỉ dùng độ lớn gia tốc. Chỉ cần giữ
  cố định trong suốt một phiên.
- Mỗi người tham gia dùng một **mã ẩn danh** (S01, S02…). Không ghi tên thật. Hỏi người
  tham gia có đồng ý không trước khi ghi.
- Người đếm dùng bộ bấm đếm (tally counter), hoặc quay video phần chân rồi đếm lại.
  Cách quay video chính xác hơn khi đi nhanh hay đi cầu thang.

## 2. Ghi một phiên

Trên Pi:

```bash
sudo systemctl stop health-watch
cd /home/pi/projects/health_watch
.venv/bin/python record_imu.py --subject S01 --activity walk_normal --placement wrist_left --duration 120
# hết giờ: nhập số bước đã đếm
sudo systemctl start health-watch
```

Kết thúc phiên, script in ngay số bước của thuật toán và của AI kèm sai số so với số
bạn đã đếm. File `recordings/<phiên>.csv` (100 Hz, gia tốc + gyro) và
`recordings/<phiên>.json` (nhãn, thông tin cảm biến) được giữ lại khi triển khai code mới.

## 3. Danh sách phiên cho mỗi người

Mục tiêu tối thiểu là **8 người**, mỗi người làm đủ các phiên dưới đây (khoảng 25 phút).

| `--activity` | Thời lượng | Đếm bước | Ghi chú |
| --- | --- | --- | --- |
| `walk_normal` | 2 × 120 s | Có | Hành lang, đường thẳng |
| `walk_slow` | 120 s | Có | Chậm như đi dạo |
| `walk_fast` | 120 s | Có | Nhanh như sắp trễ giờ |
| `stairs_up`, `stairs_down` | mỗi loại 60 s | Có | Có tay vịn, an toàn |
| `run` | 60 s | Có | Chạy nhẹ, chỉ người khỏe |
| `free_living` | 300 s | Có (quay video) | Đi lại trong phòng/nhà, mở tủ, rót nước |
| `desk_work` | 120 s | 0 | Gõ phím, viết |
| `gesture_talk` | 120 s | 0 | Nói chuyện có khua tay |
| `brush_teeth`, `wash_hands` | mỗi loại 60 s | 0 | Làm động tác thật |
| `household` | 120 s | 0 | Lau bàn, gấp quần áo tại chỗ |
| `stand`, `sit` | mỗi loại 60 s | 0 | Đứng, ngồi yên |
| `motorbike_passenger` | 300 s | 0 | **Chỉ người ngồi sau** đeo thiết bị; người lái không cầm gì |
| `bus_or_car` | 300 s | 0 | Ngồi trên xe |

**An toàn:** không để người thử ngã, không chạy trên cầu thang, không đeo thiết bị
khi đang lái xe. Kiểm tra mạch không nóng và không có dây hở trước khi đeo.

## 4. Chép về máy tính và đánh giá

```powershell
scp -r pi@pi.local:/home/pi/projects/health_watch/recordings ml\data\team_recordings
.\.venv-ml\Scripts\python ml\train_walk_gate.py --oxwalk ml\data\OxWalk_Dec2022\Wrist_100Hz `
    --clemson ml\data\clemson --team ml\data\team_recordings --version 1.1.0
```

Khi có `--team`, phần đánh giá chéo theo người gồm cả dữ liệu của nhóm. Một người
không bao giờ xuất hiện đồng thời trong cả tập huấn luyện và tập kiểm tra.

**Tiêu chí chấp nhận đề xuất**, đo trên dữ liệu của nhóm:

| Chỉ số | Mục tiêu |
| --- | --- |
| Sai số mỗi phiên đi bộ có đếm (`walk_*`, `stairs_*`) | ≤ 10% (mức chuẩn cho máy đếm bước thương mại khi thử có kiểm soát) |
| Bước giả trong các phiên đếm 0 (`desk_work`, `motorbike_passenger`, …) | ≤ 5 bước/phút |
| Đứt mẫu (`gap_count`) | 0 trong phần lớn phiên |

Chỉ thay mô hình trên Pi khi mô hình mới tốt hơn mô hình cũ trên cùng tập kiểm tra.
Ghi phiên bản mới vào `--version`. Phiên bản này đi kèm mọi số bước AI gửi lên
backend, nên kết quả luôn truy được về mô hình đã tạo ra nó.

## 5. Bảo mật dữ liệu

`health_watch/recordings/`, `ml/data/` và `ml/cache/` đều nằm trong `.gitignore`.
Không commit, không đẩy dữ liệu ghi lên GitHub hay dịch vụ ngoài. Xóa dữ liệu của
người tham gia nếu họ yêu cầu.
