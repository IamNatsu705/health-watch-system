# Dữ liệu thật dùng trong test

Hai đoạn 60 giây trích từ **OxWalk** (dữ liệu thật, không phải tín hiệu tổng hợp):

| File | Nguồn | Nội dung |
| --- | --- | --- |
| `oxwalk_P01_walking_60s.csv.gz` | `Wrist_100Hz/P01_wrist100.csv`, mẫu 6000–11999 | Đi bộ liên tục, 114 bước gán nhãn bằng video |
| `oxwalk_P11_no_steps_60s.csv.gz` | `Wrist_100Hz/P11_wrist100.csv`, mẫu 72000–77999 | Cử động tay nhiều nhưng không có bước nào |

Cột: `ax_g, ay_g, az_g` (g, AX3 ở cổ tay, 100 Hz) và `step` (1 tại thời điểm gót
chạm đất). Thay đổi so với bản gốc: chỉ cắt đoạn, bỏ cột thời gian, làm tròn 6
chữ số thập phân.

Trích dẫn (giấy phép CC BY 4.0):

> Small, S., von Fritsch, L., Doherty, A., Khalid, S., Price, A. (2022).
> *OxWalk: Wrist and hip-based activity tracker dataset for free-living step
> detection and gait recognition*. University of Oxford.
> https://doi.org/10.5287/bodleian:ORQ2abnbR

Hai đoạn này dùng để kiểm tra hồi quy toàn bộ đường xử lý trên Pi (bộ lọc,
đỉnh, mô hình JSON). Mô hình đã thấy dữ liệu của hai người này khi huấn luyện,
nên đây **không** phải phép đo độ chính xác; số liệu đánh giá thật nằm ở
[`ml/README.md`](../../../ml/README.md).
