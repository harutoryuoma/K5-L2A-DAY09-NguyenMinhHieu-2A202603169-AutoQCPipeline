# Báo cáo Day 09 — Nguyễn Minh Hiếu, 2A202603169

## 1. Kết luận trước

Auto QC Pipeline xử lý **224 ảnh raw**, nhận 193 ảnh và loại 31 ảnh tại cửa vào (13,84%). QC vòng 1 phát hiện 36 lỗi bắt buộc (ERROR) và 149 cảnh báo (WARN). Máy thực hiện 35 thay đổi tự động; sau autofix còn 6 ERROR và 121 ảnh trong hàng đợi review. Human review mô phỏng có ngân sách 80 ảnh.

**Kết luận cuối: HOLD (exit code 10).** Sau vòng duyệt, còn 34/193 ảnh có cảnh báo (17,62%), vượt ngưỡng Hold 10%. Dataset `clean_v1` chỉ là bản nháp, chưa được phát hành.

## 2. Lỗi và phân việc

Sau khi chạy Auto QC Pipeline với `duplicates.phash_dist = 16` và `second_opinion.conf = 0.60`, tôi thống kê các lỗi từ `submission/reports/02_error_list_v1.csv`.

| Mã lỗi/cảnh báo | Số lượng | Phân công xử lý |
|---|---:|---|
| BAD_CLASS_ID | 6 | Máy xóa dòng nhãn sai class |
| BAD_CLASS_NAME | 2 | Máy sửa tên class trong `data.yaml` |
| BAD_FORMAT | 3 | Máy xóa dòng sai định dạng |
| BAD_SIZE | 3 | Máy loại ảnh có kích thước không hợp lệ |
| BOX_HUGE | 3 | Người kiểm tra box quá lớn |
| BOX_OUT_OF_IMAGE | 8 | Máy cắt box về biên ảnh |
| BOX_TINY | 6 | Người kiểm tra box quá nhỏ |
| BOX_ZERO | 4 | Máy xóa box không có diện tích |
| CLASS_RARE | 4 | Người kiểm tra phân bố lớp hiếm |
| CORRUPT_IMAGE | 2 | Máy loại ảnh hỏng |
| DUP_BOX | 7 | Máy xóa dòng box trùng |
| DUP_IMAGE_EXACT | 8 | Máy loại ảnh trùng hoàn toàn |
| DUP_IMAGE_NEAR | 7 | Máy phát hiện gần trùng; người kiểm tra cặp ảnh |
| EMPTY_LABEL | 11 | Người xác nhận ảnh nền hay thiếu nhãn |
| LEAK_TEST | 11 | Máy loại ảnh rò rỉ tập test |
| MISSING_LABEL_FILE | 6 | Người gán nhãn bổ sung |
| POSSIBLE_FALSE_POS | 28 | Người kiểm tra nhãn thừa |
| POSSIBLE_LOOSE_BOX | 27 | Người kiểm tra vị trí và kích thước box |
| POSSIBLE_MISSING | 53 | Người kiểm tra đối tượng chưa gán nhãn |
| POSSIBLE_WRONG_CLASS | 17 | Người kiểm tra class có thể bị gán sai |

**Nhận xét:** Các cảnh báo từ `second_opinion` chiếm phần lớn, đặc biệt POSSIBLE_MISSING (53), POSSIBLE_FALSE_POS (28), POSSIBLE_LOOSE_BOX (27) và POSSIBLE_WRONG_CLASS (17). Đây là các lỗi liên quan đến nội dung hình ảnh mà kiểm tra cú pháp không thể xác nhận hoàn toàn.

**Phân công:** Máy xử lý các lỗi có quy tắc sửa xác định như sai định dạng, class ID không hợp lệ, box trùng và ảnh hỏng. Con người xử lý cảnh báo ngữ nghĩa và ảnh thiếu nhãn.

**Giới hạn:** Số liệu là số bản ghi QC vòng 1, không phải số ảnh khác nhau. Sau autofix và human review, pipeline vẫn HOLD vì 34/193 ảnh còn cảnh báo (17,62%), vượt ngưỡng 10%.

## 3. Calibration hai ngưỡng

Sử dụng 39 ảnh trong `data/calib/`, đối chiếu `MANIFEST.csv`.

| Tham số | Khởi đầu | Đã chọn | Precision / Recall trước → sau |
|---|---:|---:|---|
| `duplicates.phash_dist` | 2 | **16** | Near duplicate: 1.00/0.50 → 1.00/0.83 |
| `second_opinion.conf` | 0.25 | **0.60** | Missing: 0.50/1.00 → 0.57/1.00; Wrong class: 0.56/0.83 → 0.62/0.83 |

Chọn `phash_dist=16` vì F1 phát hiện ảnh gần trùng tăng từ 0.67 lên 0.91, trong khi precision trên calib vẫn đạt 1.00. Chọn `conf=0.60` để giảm cảnh báo sai đối với Missing và Wrong Class mà không giảm recall của hai nhóm này. Đánh đổi là recall Loose Box giảm từ 0.40 xuống 0.20.

**Điểm calibration có thể đánh lừa:** Calib chỉ có 39 ảnh với lỗi chèn có chủ đích. Precision 1.00 trên calib không bảo đảm sẽ không xóa nhầm ảnh thực tế. Sau calibration, số ảnh bị loại tăng từ 19 lên 31 (+12 ảnh), cần kiểm tra các cặp ảnh gần trùng bằng mắt.

## 4. Cửa chặn và điểm mù

**Kết quả cửa chặn:** Sau autofix và human review mô phỏng, báo cáo `07_error_list_v3.csv` không còn bản ghi ERROR. Tuy nhiên, vẫn còn 66 WARN trên 34/193 ảnh (17,62%), vượt ngưỡng Hold 10%. Vì vậy, pipeline kết luận **HOLD (exit code 10)** và không cho phép phát hành dataset chính thức.

**Điểm mù 1 — Box lỏng:** Sau review còn 18 cảnh báo POSSIBLE_LOOSE_BOX. Trên tập calib, tại `second_opinion.conf = 0.60`, recall chỉ đạt 0.20. Bộ kiểm tra có thể bỏ sót các box bị lệch hoặc chưa bao sát đối tượng.

**Điểm mù 2 — Ảnh gần trùng:** Với `duplicates.phash_dist = 16`, recall phát hiện near-duplicate trên calib đạt 0.83, chưa đạt 1.00. Số ảnh bị loại tăng từ 19 lên 31 sau calibration nên cần xác minh các cặp ảnh được đánh dấu gần trùng nhằm tránh loại nhầm dữ liệu.

## 5. Train: raw vs clean (tùy chọn)

**Chưa thực hiện train Colab.** Tôi ưu tiên hoàn thành phần lõi Auto QC Pipeline, hiệu chỉnh hai ngưỡng và kiểm tra an toàn dữ liệu. Do chưa có kết quả huấn luyện raw/clean trên nhiều seed, chưa thể kết luận model có cải thiện chất lượng nhờ pipeline QC.

## 6. Quyết định và ghi chú AI

**(a) Quyết định cuối: HOLD**

Pipeline xử lý 224 ảnh raw, nhận 193 ảnh và loại 31 ảnh. Sau ba vòng QC, báo cáo cuối không còn ERROR nhưng có 66 WARN trên 34 ảnh (17,62%), cao hơn ngưỡng 10%.

Để đạt Release, cần tiếp tục kiểm tra các ảnh chưa duyệt hoặc còn cảnh báo, ưu tiên POSSIBLE_FALSE_POS, POSSIBLE_LOOSE_BOX và POSSIBLE_MISSING. Nếu giữ nguyên 193 ảnh, phải giảm số ảnh còn cảnh báo xuống tối đa 19 ảnh, đồng thời bảo đảm không phát sinh ERROR mới.

**(b) Ghi chú sử dụng AI**

1. **Prompt chính:** Tôi sử dụng ChatGPT hỗ trợ triển khai bốn module `label_format.py`, `gate.py`, `autofix.py`, `second_opinion.py`; cung cấp docstring, yêu cầu đầu vào/đầu ra, quy tắc kiểm tra và giới hạn bảo vệ dữ liệu.
2. **Cách kiểm code AI:** Tôi đối chiếu mã với docstring, rà soát thao tác đọc/ghi/xóa file, chạy test và pipeline. Toàn bộ **79/79 test PASSED**; pipeline chạy thành công và kết luận HOLD với exit code 10.
3. **Một thiếu sót của AI:** Code đề xuất cho `autofix.py` chưa chủ động chặn trường hợp sử dụng nhầm đường dẫn dữ liệu gốc, có nguy cơ xóa hoặc ghi đè dữ liệu. Tôi phát hiện khi rà soát `unlink()` và `write_text()`; cần bảo đảm chỉ chạy autofix trên bản sao dataset.