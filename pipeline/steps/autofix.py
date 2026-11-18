"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""

from collections import defaultdict

import yaml

from ..common import ERROR, parse_yolo_line


DROP_CODES = {
    "BAD_FORMAT",
    "BAD_CLASS_ID",
    "BOX_ZERO",
    "DUP_BOX",
}

REMOVE_CODES = {
    "LEAK_TEST",
    "CORRUPT_IMAGE",
    "BAD_SIZE",
}


def _record(image, line, action, before, after):
    """Tạo một dòng nhật ký thay đổi."""
    return {
        "image": image,
        "line": line,
        "action": action,
        "before": before,
        "after": after,
    }


def _clip_yolo(text):
    """Cắt bbox YOLO về [0, 1]; trả None nếu rỗng."""
    class_id, cx, cy, w, h = parse_yolo_line(text)

    x1 = max(0.0, cx - w / 2)
    y1 = max(0.0, cy - h / 2)
    x2 = min(1.0, cx + w / 2)
    y2 = min(1.0, cy + h / 2)

    if x2 <= x1 or y2 <= y1:
        return None

    new_cx = (x1 + x2) / 2
    new_cy = (y1 + y2) / 2
    new_w = x2 - x1
    new_h = y2 - y1

    return (
        f"{class_id} "
        f"{new_cx:.12g} {new_cy:.12g} "
        f"{new_w:.12g} {new_h:.12g}"
    )


def fix(ds, issues, cfg):
    """Sửa lỗi ERROR trong dataset làm việc và trả log."""
    changes = []

    # Không xử lý các cảnh báo WARN
    errors = [
        issue for issue in issues
        if issue.severity == ERROR
    ]

    # 1. Xác định những ảnh phải xóa
    remove_stems = set()

    for issue in errors:
        if (
            issue.code in REMOVE_CODES
            or issue.code.startswith("DUP_IMAGE_")
        ):
            remove_stems.add(issue.image)

    # Xử lý ảnh và nhãn theo từng stem
    for stem in sorted(remove_stems):
        img_path = ds.image_path(stem)
        label_path = ds.label_path(stem)

        existing = [
            p for p in (img_path, label_path)
            if p is not None and p.exists()
        ]

        if not existing:
            continue

        before = ", ".join(p.name for p in existing)

        for path in existing:
            path.unlink()

        ds._size_cache.pop(stem, None)

        changes.append(
            _record(
                stem, None, "remove_image",
                before, "(đã xoá)"
            )
        )

    # 2. Xử lý file nhãn bị thiếu
    missing_stems = {
        issue.image
        for issue in errors
        if issue.code == "MISSING_LABEL_FILE"
    }

    for stem in sorted(missing_stems - remove_stems):
        if not ds.label_path(stem).exists():
            changes.append(
                _record(
                    stem, None, "needs_label",
                    "(không có file)",
                    "chuyển người gán",
                )
            )

    # 3. Sửa tên các class trong data.yaml
    rename_needed = any(
        issue.code == "BAD_CLASS_NAME"
        for issue in errors
    )

    if rename_needed and ds.yaml_path.exists():
        data = yaml.safe_load(
            ds.yaml_path.read_text(encoding="utf-8")
        ) or {}

        target_names = {
            i: name
            for i, name in enumerate(cfg["classes"])
        }

        if ds.yaml_names() != target_names:
            before = str(data.get("names"))
            data["names"] = target_names

            ds.yaml_path.write_text(
                yaml.safe_dump(
                    data,
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            changes.append(
                _record(
                    "data.yaml",
                    None,
                    "rename_classes",
                    before,
                    str(target_names),
                )
            )

    # 4. Gom lỗi theo ảnh và số dòng gốc
    by_file = defaultdict(lambda: defaultdict(set))

    for issue in errors:
        if issue.image in remove_stems:
            continue

        if issue.line is None:
            continue

        if (
            issue.code in DROP_CODES
            or issue.code == "BOX_OUT_OF_IMAGE"
        ):
            by_file[issue.image][issue.line].add(
                issue.code
            )

    # 5. Đọc và sửa mỗi file đúng một lần
    for stem in sorted(by_file):
        label_path = ds.label_path(stem)

        if not label_path.exists():
            continue

        original = label_path.read_text(
            encoding="utf-8"
        ).splitlines()

        updated = []
        file_changes = []

        for line_no, text in enumerate(original, 1):
            codes = by_file[stem].get(line_no, set())

            # Dòng không có lỗi: giữ nguyên
            if not codes:
                updated.append(text)
                continue

            # Xóa dòng luôn ưu tiên hơn clip
            if codes & DROP_CODES:
                file_changes.append(
                    _record(
                        stem, line_no,
                        "drop_line", text, ""
                    )
                )
                continue

            # Cắt Bounding Box vượt biên
            if "BOX_OUT_OF_IMAGE" in codes:
                try:
                    new_text = _clip_yolo(text)
                except ValueError:
                    # Nhãn không còn parse được:
                    # ghi log rõ ràng và bỏ dòng hỏng
                    new_text = None

                if new_text is None:
                    file_changes.append(
                        _record(
                            stem, line_no,
                            "drop_line", text, ""
                        )
                    )
                    continue

                if new_text != text:
                    updated.append(new_text)
                    file_changes.append(
                        _record(
                            stem, line_no,
                            "clip_box",
                            text, new_text
                        )
                    )
                else:
                    updated.append(text)

                continue

            updated.append(text)

        # Chỉ ghi đè khi thực sự có thay đổi
        if file_changes:
            new_content = "\n".join(updated)

            if updated:
                new_content += "\n"

            label_path.write_text(
                new_content,
                encoding="utf-8",
            )

            changes.extend(file_changes)

    return changes

