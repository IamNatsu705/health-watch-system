# AI đếm bước chân: dữ liệu, mô hình, đánh giá

Thư mục này chạy **trên máy tính**, không chạy trên Pi. Nó huấn luyện và đánh giá
mô hình mà Pi dùng (`health_watch/models/walk_gate.json`), bằng **chính mã xử lý
tín hiệu chạy trên Pi** (`health_watch/processing/`). Chỉ dùng dữ liệu ghi từ
người thật; không có bước nào sinh tín hiệu tổng hợp để huấn luyện.

## 1. AI làm gì

Lỗi lớn nhất của máy đếm bước đeo cổ tay không nằm ở việc tìm đỉnh, mà ở việc
**đếm khống khi không đi bộ**: vẫy tay, khua tay khi nói chuyện, việc nhà, rung
xe máy. Vì vậy AI được dùng làm **cổng "đang đi bộ hay không"**:

1. Pi lọc độ lớn gia tốc 0,5–3 Hz và tìm các đỉnh ứng viên (ngưỡng thích nghi).
2. Cứ mỗi cửa sổ 5 giây, Pi tính 16 đặc trưng (cùng 16 đặc trưng của cửa sổ trước)
   từ độ lớn gia tốc: độ biến thiên, tự tương quan ở chu kỳ bước/sải, phân bố phổ
   0,5–4 Hz, năng lượng rung >5 Hz, độ đều của khoảng cách đỉnh...
3. Random Forest (100 cây, độ sâu ≤10) cho xác suất đang đi bộ. Nếu xác suất ≥ ngưỡng
   thì cộng các đỉnh trong cửa sổ đó vào `steps_ai`, ngược lại bỏ qua.

Song song, Pi vẫn chạy thuật toán xử lý tín hiệu không AI (`peak-bout-v2`: chỉ cộng
khi có ≥6 đỉnh liên tiếp đều nhịp). Cả hai số đều gửi lên backend; giao diện dùng
số của AI khi Pi nạp được mô hình.

Vì sao chọn cách này thay vì mạng sâu đếm trực tiếp: với dữ liệu đúng là đi bộ,
chỉ riêng bộ đếm đỉnh đã sai khoảng 4% (xem mục 4, "cổng hoàn hảo"). Phần còn lại
là quyết định có đang đi bộ hay không, và Random Forest trên đặc trưng làm tốt việc
này với vài chục nghìn cửa sổ. Mô hình được xuất ra JSON, suy luận bằng Python thuần
trên Pi trong khoảng 1 ms, không cần scikit-learn hay numpy trên Pi, và không dùng
pickle. Hướng này giống phương pháp đã công bố của nhóm Oxford (Small et al., 2024),
nhưng mô hình ở đây nhỏ hơn nhiều.

## 2. Dữ liệu

| Dataset | Dùng để | Nội dung | Giấy phép |
| --- | --- | --- | --- |
| [OxWalk](https://doi.org/10.5287/bodleian:ORQ2abnbR) | Huấn luyện + đánh giá chéo | 39 người, AX3 ở cổ tay, 100 Hz, ±8 g, ~38 giờ sinh hoạt tự do, 62.904 bước gán nhãn từng bước bằng video quay chân | CC BY 4.0 |
| [Clemson Pedometer](https://cecas.clemson.edu/~ahoover/pedometer/) | Kiểm định độc lập (chưa từng dùng để huấn luyện) | 30 người, cổ tay, 15 Hz, 56.668 bước gán nhãn bằng video; đi đều / bán đều / lộn xộn trong phòng | Xem trang dự án |
| Bản ghi của nhóm (`record_imu.py`) | Fine-tune và đánh giá trên đúng MPU6050 | Xem [docs/data-collection.md](../docs/data-collection.md) | Dữ liệu cá nhân, không commit |

Đặc trưng chỉ dùng độ lớn gia tốc và các đại lượng tương đối, nên không phụ thuộc
hướng gắn cảm biến hay sai số offset tĩnh của MPU6050. Pi lấy mẫu 100 Hz, ±8 g, đúng
như OxWalk. Dữ liệu Clemson 15 Hz được nội suy lên 100 Hz.

## 3. Chạy lại

```powershell
python -m venv .venv-ml
.\.venv-ml\Scripts\python -m pip install -r ml\requirements.txt
# Tải OxWalk (zip ~290 MB) và Clemson Data.zip (31 MB), giải nén vào ml\data\ (đã gitignore)
.\.venv-ml\Scripts\python ml\train_walk_gate.py `
    --oxwalk ml\data\OxWalk_Dec2022\Wrist_100Hz `
    --clemson ml\data\clemson `
    --team ml\data\team_recordings `
    --version 1.1.0
.\.venv-ml\Scripts\python ml\evaluate_legacy.py --oxwalk ml\data\OxWalk_Dec2022\Wrist_100Hz --clemson ml\data\clemson
```

`--team` là tùy chọn. Script tự kiểm tra file JSON xuất ra cho đúng xác suất của
scikit-learn (lệch < 1e-5), rồi ghi kết quả đánh giá vào ngay trong file mô hình.
Sau khi huấn luyện lại, chạy `python -m unittest discover -s tests` trong
`health_watch/` rồi triển khai lên Pi.

## 4. Kết quả (mô hình `walk-gate-rf 1.0.0`)

Chỉ số chính là **sai số đếm bước tuyệt đối trung bình theo người/phiên** (MAPE):
|đếm − thật| / thật, tính riêng cho từng người rồi lấy trung bình. Đây là chỉ số
khắt khe, vì người đi ít bước mà bị đếm khống vài trăm bước sẽ có sai số rất lớn.

**OxWalk, đánh giá chéo lồng nhau theo người**: 5 fold, mỗi fold giữ riêng ~8 người
chưa từng thấy. Ngưỡng quyết định được chọn bằng 4 fold bên trong (0,575–0,625).

| Bộ đếm | MAPE theo người | Trung vị | Tổng số bước |
| --- | ---: | ---: | ---: |
| Thuật toán cũ `peak-v1` (25 Hz đều, trường hợp tốt nhất) | 80,1% | 43,2% | +13,3% |
| Thuật toán mới `peak-bout-v2` (không AI) | 17,9% | 10,7% | −9,0% |
| **AI + `peak-bout-v2`** | **13,5%** | **9,0%** | **−3,6%** |
| Tham khảo: cổng hoàn hảo (nhãn thật) + đếm đỉnh | 4,1% | | −1,8% |

Phân loại cửa sổ đi bộ: F1 = 0,883, độ chính xác cân bằng = 0,913. Để so sánh,
phương pháp tự giám sát của Small et al. (2024) báo cáo 12,5% trong điều kiện sinh
hoạt tự do.

**Clemson, kiểm định độc lập**: cùng file JSON mà Pi dùng, chạy qua đúng đường suy luận của Pi.

| Kiểu đi | Thuật toán cũ | Thuật toán mới | **AI** |
| --- | ---: | ---: | ---: |
| Đi đều (đường thẳng) | 20,0% | 12,3% | **6,7%** |
| Bán đều (quanh tòa nhà) | 18,4% | 22,6% | **8,6%** |
| Lộn xộn (trong phòng, bước ngắn, xoay người) | 48,6% | 24,0% | 37,8% (đếm dư) |
| Tất cả 90 phiên | 29,0% | 19,6% | **17,7%** |

## 5. Giới hạn cần nói rõ

- **Chưa đánh giá trên MPU6050 của nhóm.** Mọi con số trên đo bằng cảm biến AX3
  (OxWalk) và Shimmer (Clemson) đeo ở cổ tay. Cần ghi dữ liệu theo
  [docs/data-collection.md](../docs/data-collection.md) để đo sai số trên chính thiết
  bị, rồi huấn luyện lại với `--team`.
- **Đi lộn xộn trong phòng bị đếm dư** khoảng 35%: bước ngắn, xoay người, dồn trọng tâm.
- Hai bộ dữ liệu là người trưởng thành khỏe mạnh ở Anh/Mỹ, nên không đại diện cho người
  già đi chậm, người dùng dụng cụ hỗ trợ hay trẻ em.
- **Rung xe máy chưa có trong dữ liệu huấn luyện.** Bộ lọc DLPF 44 Hz và đặc trưng năng
  lượng >5 Hz giúp loại rung, nhưng cần dữ liệu `motorbike_passenger` thật để kiểm chứng.
- Quãng đường và kcal là **ước tính** từ số bước và hồ sơ người dùng (chiều dài bước
  0,414 × chiều cao hoặc tự đo; phương trình ACSM), không phải phép đo.
- Không phải thiết bị y tế.

## 6. Trích dẫn

- Small, S., von Fritsch, L., Doherty, A., Khalid, S., Price, A. (2022). *OxWalk: Wrist
  and hip-based activity tracker dataset for free-living step detection and gait
  recognition*. University of Oxford. https://doi.org/10.5287/bodleian:ORQ2abnbR (CC BY 4.0)
- Small, S. R. et al. (2024). *Self-Supervised Machine Learning to Characterize Step
  Counts from Wrist-Worn Accelerometers in the UK Biobank*. Med Sci Sports Exerc 56:1945–1953.
- Mattfeld, R., Jesch, E., Hoover, A. (2021). *Evaluating Pedometer Algorithms on
  Semi-Regular and Unstructured Gaits*. Sensors 21(13):4260. Dữ liệu:
  https://cecas.clemson.edu/~ahoover/pedometer/
- American College of Sports Medicine. *ACSM's Guidelines for Exercise Testing and
  Prescription*: phương trình năng lượng đi bộ/chạy.
