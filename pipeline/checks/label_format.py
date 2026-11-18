"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""

from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line


def run(ds, cfg):
    """Kiểm tra định dạng và hình học của nhãn YOLO."""
    issues = []
    settings = cfg["label_format"]

    overflow_tol = settings["overflow_tol"]
    min_box_px = settings["min_box_px"]
    max_box_frac = settings["max_box_frac"]
    dup_box_iou = settings["dup_box_iou"]

    for label_file in ds.label_files():
        stem = label_file.stem
        lines = ds.read_label_lines(stem) or []
        image_size = ds.image_size(stem)

        previous_boxes = []

        for line_number, text in lines:
            # 1. Kiểm tra định dạng YOLO
            try:
                class_id, cx, cy, w, h = parse_yolo_line(text)
            except ValueError as exc:
                issues.append(Issue(
                    "label_format", ERROR, "BAD_FORMAT",
                    stem, f"Sai định dạng YOLO: {exc}",
                    line=line_number
                ))
                continue

            # 2. Kiểm tra class ID
            if not 0 <= class_id < len(ds.classes):
                issues.append(Issue(
                    "label_format", ERROR, "BAD_CLASS_ID",
                    stem, f"Class ID không hợp lệ: {class_id}",
                    line=line_number
                ))
                continue

            # 3. Kiểm tra box rỗng hoặc âm
            if w <= 0 or h <= 0:
                issues.append(Issue(
                    "label_format", ERROR, "BOX_ZERO",
                    stem, "Chiều rộng hoặc chiều cao không dương",
                    line=line_number
                ))
                continue

            box = (cx, cy, w, h)

            # 4. Kiểm tra box vượt biên
            x1 = cx - w / 2
            y1 = cy - h / 2
            x2 = cx + w / 2
            y2 = cy + h / 2

            overflow = max(
                0.0, -x1, -y1, x2 - 1.0, y2 - 1.0
            )

            if overflow > overflow_tol:
                issues.append(Issue(
                    "label_format", ERROR, "BOX_OUT_OF_IMAGE",
                    stem, f"Box vượt biên: {overflow:.6f}",
                    line=line_number,
                    extra={"overflow": overflow}
                ))

            # 5. Kiểm tra box trùng cùng class
            for old_class, old_box in previous_boxes:
                if old_class == class_id:
                    if iou_xywh(box, old_box) > dup_box_iou:
                        issues.append(Issue(
                            "label_format", ERROR, "DUP_BOX",
                            stem, "Box trùng với box trước đó",
                            line=line_number
                        ))
                        break

            previous_boxes.append((class_id, box))

            # 6. Kiểm tra box quá nhỏ
            if image_size is not None:
                img_w, img_h = image_size
                short_side = min(w * img_w, h * img_h)

                if short_side < min_box_px:
                    issues.append(Issue(
                        "label_format", WARN, "BOX_TINY",
                        stem, "Box có cạnh quá nhỏ",
                        line=line_number
                    ))

            # 7. Kiểm tra box quá lớn
            if w * h > max_box_frac:
                issues.append(Issue(
                    "label_format", WARN, "BOX_HUGE",
                    stem, "Box chiếm quá nhiều diện tích ảnh",
                    line=line_number
                ))

    return issues
