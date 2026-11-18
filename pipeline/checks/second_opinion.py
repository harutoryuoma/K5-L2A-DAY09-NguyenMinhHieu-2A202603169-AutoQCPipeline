"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""

from ..common import WARN, Issue, iou_xywh, parse_yolo_line
from ..model_cache import get_preds


def run(ds, cfg, preds=None):
    """So sánh nhãn YOLO với dự đoán model lớn hơn."""

    issues = []

    # Đọc ngưỡng từ cấu hình
    settings = cfg["second_opinion"]

    conf_threshold = settings["conf"]
    min_area_px = settings["min_area_px"]
    fp_conf = settings["fp_conf"]
    iou_missing = settings["iou_missing"]
    iou_match = settings["iou_match"]
    iou_loose = settings["iou_loose"]

    # Nếu không cung cấp preds, lấy từ model cache
    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    # Duyệt theo thứ tự ảnh trong dataset
    for image_path in ds.image_files():
        stem = image_path.stem

        # Bỏ qua ảnh không có dự đoán
        if stem not in preds:
            continue

        # Bỏ qua ảnh chưa có file nhãn
        label_lines = ds.read_label_lines(stem)
        if label_lines is None:
            continue

        image_size = ds.image_size(stem)
        if image_size is None:
            continue

        img_w, img_h = image_size

        predictions = preds[stem]

        # Các nhãn hợp lệ
        labels = ds.valid_boxes(stem)

        # Giữ số dòng gốc để báo FALSE_POS
        valid_lines = []

        for line_number, text in label_lines:
            try:
                label = parse_yolo_line(text)
            except ValueError:
                continue

            if not 0 <= label[0] < len(ds.classes):
                continue

            valid_lines.append((line_number, label))

        # Dự đoán dùng để phát hiện missing,
        # wrong class và loose box
        strong_preds = []

        for prediction in predictions:
            class_id, confidence, cx, cy, w, h = prediction

            area_px = w * img_w * h * img_h

            if confidence < conf_threshold:
                continue

            if area_px < min_area_px:
                continue

            strong_preds.append(prediction)

        # 1. Kiểm tra từng dự đoán đủ điều kiện
        for prediction in strong_preds:
            pred_class = prediction[0]
            confidence = prediction[1]
            pred_box = prediction[2:6]

            # Tìm mọi nhãn có IoU đủ ngưỡng
            candidates = []

            for label in labels:
                label_class = label[0]
                label_box = label[1:5]

                iou = iou_xywh(pred_box, label_box)

                if iou >= iou_missing:
                    candidates.append((label_class, iou))

            # Không có nhãn phù hợp
            if not candidates:
                issues.append(Issue(
                    "second_opinion",
                    WARN,
                    "POSSIBLE_MISSING",
                    stem,
                    "Model phát hiện đối tượng chưa có nhãn phù hợp",
                    extra={"conf": confidence},
                ))
                continue

            # Tìm các nhãn cùng lớp
            same_class_ious = [
                iou
                for label_class, iou in candidates
                if label_class == pred_class
            ]

            # Có nhãn cùng lớp: chỉ kiểm tra box lỏng
            if same_class_ious:
                best_iou = max(same_class_ious)

                if best_iou < iou_loose:
                    issues.append(Issue(
                        "second_opinion",
                        WARN,
                        "POSSIBLE_LOOSE_BOX",
                        stem,
                        "Box nhãn cùng lớp nhưng IoU thấp",
                        extra={
                            "conf": confidence,
                            "iou": best_iou,
                        },
                    ))

                # Đã có nhãn cùng lớp, không báo sai lớp
                continue

            # Không có nhãn cùng lớp:
            # kiểm tra nhãn khác lớp
            other_class_ious = [
                iou
                for label_class, iou in candidates
                if label_class != pred_class
            ]

            if other_class_ious:
                best_iou = max(other_class_ious)

                if best_iou >= iou_match:
                    issues.append(Issue(
                        "second_opinion",
                        WARN,
                        "POSSIBLE_WRONG_CLASS",
                        stem,
                        "Nhãn có thể sai lớp so với model",
                        extra={
                            "conf": confidence,
                            "iou": best_iou,
                        },
                    ))

        # 2. Kiểm tra nhãn có thể là false positive
        # Không lọc diện tích ở bước này
        fp_predictions = [
            prediction
            for prediction in predictions
            if prediction[1] >= fp_conf
        ]

        for line_number, label in valid_lines:
            label_box = label[1:5]

            best_iou = max(
                (
                    iou_xywh(label_box, prediction[2:6])
                    for prediction in fp_predictions
                ),
                default=0.0,
            )

            if best_iou < iou_missing:
                issues.append(Issue(
                    "second_opinion",
                    WARN,
                    "POSSIBLE_FALSE_POS",
                    stem,
                    "Box nhãn không khớp dự đoán model",
                    line=line_number,
                    extra={"iou": best_iou},
                ))

    return issues
