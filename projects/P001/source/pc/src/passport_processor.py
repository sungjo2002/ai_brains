import cv2
import numpy as np
from PIL import Image


def _estimate_horizontal_angle_and_residual(cv_img_bgr: np.ndarray) -> tuple[float, float]:
    """Estimate dominant near-horizontal angle and residual absolute angle."""
    h, w = cv_img_bgr.shape[:2]
    gray = cv2.cvtColor(cv_img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(gray, 60, 170)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180.0,
        threshold=max(70, int(w * 0.10)),
        minLineLength=max(50, int(w * 0.25)),
        maxLineGap=14,
    )

    angles: list[float] = []
    weights: list[float] = []
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            dx = float(x2 - x1)
            dy = float(y2 - y1)
            length = float(np.hypot(dx, dy))
            if length < max(45.0, w * 0.18):
                continue
            angle = float(np.degrees(np.arctan2(dy, dx)))
            while angle <= -90.0:
                angle += 180.0
            while angle > 90.0:
                angle -= 180.0
            if abs(angle) <= 30.0:
                angles.append(angle)
                weights.append(length)

    if not angles:
        return 0.0, 999.0

    arr_a = np.array(angles, dtype=np.float32)
    arr_w = np.array(weights, dtype=np.float32)
    dominant = float(np.average(arr_a, weights=arr_w))
    residual = float(np.average(np.abs(arr_a), weights=arr_w))
    return dominant, residual


def auto_deskew_image(pil_image: Image.Image, max_abs_angle: float = 12.0) -> tuple[Image.Image, float]:
    """
    Apply small-angle deskew to an already corrected passport page.
    Returns (rotated_image, applied_rotation_degrees).
    Positive degree means CCW(left), negative means CW(right).
    """
    rgb = pil_image.convert("RGB")
    cv_img = np.array(rgb)[:, :, ::-1]
    h, w = cv_img.shape[:2]
    if h < 40 or w < 40:
        return rgb, 0.0

    dominant, residual_before = _estimate_horizontal_angle_and_residual(cv_img)
    if residual_before > 80.0:  # no reliable lines found
        return rgb, 0.0

    angle = float(np.clip(dominant, -max_abs_angle, max_abs_angle))
    if abs(angle) < 0.15:
        return rgb, 0.0

    # Test both directions and choose the one that actually improves horizontality.
    cand_cw = rgb.rotate(
        -angle,
        resample=getattr(Image, "Resampling", Image).BICUBIC,
        expand=False,
        fillcolor=(245, 245, 245),
    )
    cand_ccw = rgb.rotate(
        angle,
        resample=getattr(Image, "Resampling", Image).BICUBIC,
        expand=False,
        fillcolor=(245, 245, 245),
    )

    _, residual_cw = _estimate_horizontal_angle_and_residual(np.array(cand_cw)[:, :, ::-1])
    _, residual_ccw = _estimate_horizontal_angle_and_residual(np.array(cand_ccw)[:, :, ::-1])

    best_img = cand_cw
    best_residual = residual_cw
    best_rotation = -angle
    if residual_ccw < residual_cw:
        best_img = cand_ccw
        best_residual = residual_ccw
        best_rotation = angle

    # Only apply when it clearly improves; prevents repeated drift on each click.
    if best_residual >= (residual_before - 0.15):
        return rgb, 0.0

    return best_img, float(best_rotation)



def _find_mrz_text_angle(cv_img_bgr: np.ndarray) -> tuple[float, float]:
    """
    Estimate passport MRZ baseline angle from the lower area of a corrected passport page.
    Returns (angle_degrees_in_image_coordinates, confidence).
    confidence <= 0 means no reliable MRZ-like text line was found.
    """
    h, w = cv_img_bgr.shape[:2]
    if h < 80 or w < 160:
        return 0.0, 0.0

    # MRZ is printed in the lower part of passport data pages. Try several starts
    # because manual 4-point crops may include different amounts of top/bottom margin.
    best: tuple[float, float] = (0.0, 0.0)
    for y_start_ratio in (0.52, 0.58, 0.64, 0.70):
        y0 = int(h * y_start_ratio)
        roi = cv_img_bgr[y0:h, :]
        if roi.size == 0:
            continue

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        clahe = cv2.createCLAHE(clipLimit=2.4, tileGridSize=(8, 8))
        gray = clahe.apply(gray)

        # Dark MRZ text -> white blobs.
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        # Remove small speckles and join characters on each MRZ row.
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)), iterations=1)
        join_w = max(18, int(w * 0.035))
        joined = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (join_w, 3)), iterations=2)
        joined = cv2.dilate(joined, cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, int(w * 0.008)), 1)), iterations=1)

        cnts, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates: list[tuple[float, float]] = []
        for c in cnts:
            x, y, cw, ch = cv2.boundingRect(c)
            if cw < w * 0.22:
                continue
            if ch < 6 or ch > roi.shape[0] * 0.35:
                continue
            # Prefer lower/wide text bands and avoid page border lines.
            area = float(cv2.contourArea(c))
            if area < max(30.0, cw * ch * 0.04):
                continue
            pts = c.reshape(-1, 2).astype(np.float32)
            if len(pts) < 8:
                continue
            vx, vy, _, _ = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01).flatten()
            angle = float(np.degrees(np.arctan2(float(vy), float(vx))))
            while angle <= -90.0:
                angle += 180.0
            while angle > 90.0:
                angle -= 180.0
            if abs(angle) > 15.0:
                continue
            lower_bias = (y + ch / 2.0) / max(roi.shape[0], 1)
            score = (cw / max(w, 1)) * 2.0 + min(area / max(w * roi.shape[0], 1), 0.10) * 8.0 + lower_bias * 0.8
            candidates.append((angle, score))

        if candidates:
            weights = np.array([s for _, s in candidates], dtype=np.float32)
            angles = np.array([a for a, _ in candidates], dtype=np.float32)
            angle = float(np.average(angles, weights=weights))
            confidence = float(weights.sum())
            if confidence > best[1]:
                best = (angle, confidence)

    return best


def level_passport_by_mrz(pil_image: Image.Image, max_abs_angle: float = 8.0) -> tuple[Image.Image, float]:
    """
    Extra passport-only leveling pass using the MRZ baseline.

    General Hough deskew can be confused by passport page borders, stamps or security
    patterns. For passports, the lower MRZ two rows are the best horizontal reference.
    This function only rotates when MRZ-like text bands are detected with confidence,
    so residence cards are normally left unchanged.
    """
    rgb = pil_image.convert("RGB")
    cv_img = np.array(rgb)[:, :, ::-1]
    h, w = cv_img.shape[:2]
    if h < 80 or w < 160:
        return rgb, 0.0

    angle, confidence = _find_mrz_text_angle(cv_img)
    if confidence <= 0.35 or abs(angle) < 0.18:
        return rgb, 0.0
    angle = float(np.clip(angle, -max_abs_angle, max_abs_angle))

    def residual(img: Image.Image) -> float:
        a, c = _find_mrz_text_angle(np.array(img.convert("RGB"))[:, :, ::-1])
        if c <= 0.0:
            return 999.0
        return abs(a)

    before_res = abs(angle)
    # PIL rotation sign can be counter-intuitive relative to image-coordinate line angles.
    # Test both directions and keep only the one that improves the MRZ baseline.
    candidates: list[tuple[float, Image.Image, float]] = []
    for rotation in (-angle, angle):
        rotated = rgb.rotate(
            rotation,
            resample=getattr(Image, "Resampling", Image).BICUBIC,
            expand=False,
            fillcolor=(245, 245, 245),
        )
        candidates.append((residual(rotated), rotated, float(rotation)))
    candidates.sort(key=lambda item: item[0])
    best_res, best_img, best_rotation = candidates[0]
    if best_res >= max(0.12, before_res - 0.10):
        return rgb, 0.0
    return best_img, best_rotation



def _find_visible_mrz_bbox(small_bgr: np.ndarray) -> tuple[float, float, float, float] | None:
    """Return a wide MRZ-like text bbox in the lower half of a passport image."""
    h, w = small_bgr.shape[:2]
    if h < 120 or w < 180:
        return None
    y0 = int(h * 0.48)
    roi = small_bgr[y0:h, :]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    try:
        gray = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8)).apply(gray)
    except Exception:
        pass
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)), iterations=1)
    join_w = max(18, int(w * 0.035))
    joined = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (join_w, 3)), iterations=2)
    joined = cv2.dilate(joined, cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, int(w * 0.008)), 1)), iterations=1)
    cnts, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[tuple[int, int, int, int]] = []
    for c in cnts:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw < w * 0.30:
            continue
        if ch < 5 or ch > roi.shape[0] * 0.22:
            continue
        if y < roi.shape[0] * 0.18:
            continue
        area = float(cv2.contourArea(c))
        if area < max(25.0, cw * ch * 0.035):
            continue
        boxes.append((x, y + y0, x + cw, y + y0 + ch))
    if not boxes:
        return None
    x1 = min(b[0] for b in boxes)
    y1 = min(b[1] for b in boxes)
    x2 = max(b[2] for b in boxes)
    y2 = max(b[3] for b in boxes)
    if (x2 - x1) < w * 0.48:
        return None
    return float(x1), float(y1), float(x2), float(y2)

def _find_lower_page_quad(small_bgr: np.ndarray) -> np.ndarray | None:
    """Fallback detector focused on the lower passport data page."""
    h, w = small_bgr.shape[:2]
    y0 = int(h * 0.42)
    roi = small_bgr[y0:h, :]
    if roi.size == 0:
        return None

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    clahe = cv2.createCLAHE(clipLimit=2.6, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    edges = cv2.Canny(gray, 40, 130)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 5))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)

    cnts, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    roi_area = float(roi.shape[0] * roi.shape[1])
    best_score = -1.0
    best_quad: np.ndarray | None = None
    for c in cnts:
        area = float(cv2.contourArea(c))
        if not (roi_area * 0.10 <= area <= roi_area * 0.92):
            continue
        peri = cv2.arcLength(c, True)
        rect = cv2.minAreaRect(c)
        quad = cv2.boxPoints(rect).astype(np.float32)
        for eps in (0.016, 0.022, 0.03):
            approx = cv2.approxPolyDP(c, eps * peri, True)
            if len(approx) == 4:
                quad = approx.reshape(4, 2).astype(np.float32)
                break

        rect2 = cv2.minAreaRect(quad.reshape(4, 1, 2))
        rw, rh = rect2[1]
        if rw <= 1 or rh <= 1:
            continue
        aspect = max(rw, rh) / (min(rw, rh) + 1e-6)
        if not (1.2 <= aspect <= 2.35):
            continue
        q_area = abs(cv2.contourArea(quad))
        fill_ratio = q_area / ((rw * rh) + 1e-6)
        cx, cy = np.mean(quad, axis=0)
        center_x = float(cx / max(roi.shape[1], 1))
        center_y = float(cy / max(roi.shape[0], 1))

        # Prefer broad, lower-center, page-like rectangle.
        score = (
            (q_area / roi_area) * 1.8
            + fill_ratio * 1.4
            + (1.0 - min(abs(center_x - 0.5), 0.5) / 0.5) * 0.8
            + (1.0 - min(abs(center_y - 0.55), 0.55) / 0.55) * 0.9
            - min(abs(aspect - 1.55), 1.0) * 0.9
        )
        if score > best_score:
            best_score = score
            best_quad = quad

    if best_quad is None:
        return None

    # ROI -> full image coordinates
    best_quad[:, 1] += float(y0)
    return best_quad.reshape(4, 1, 2)


def _find_card_outer_quad_by_color(small_bgr: np.ndarray) -> np.ndarray | None:
    """
    Detect the outer boundary of landscape residence-card style IDs by color region.

    Residence/overseas cards often contain many strong inner rectangles (portrait box,
    QR code, hologram, text panels). For 4-point document correction, those inner
    boxes must be ignored and the larger card body should be selected. This detector
    is intentionally used only when no MRZ is visible, so passport pages keep the MRZ
    based logic.
    """
    h, w = small_bgr.shape[:2]
    if h < 120 or w < 160:
        return None

    img_area = float(h * w)
    lab = cv2.cvtColor(small_bgr, cv2.COLOR_BGR2LAB)
    hsv = cv2.cvtColor(small_bgr, cv2.COLOR_BGR2HSV)

    masks: list[np.ndarray] = []
    # Blue / cyan / purple residence cards on light fabric or dark desk.
    masks.append(((lab[:, :, 2] < 142) & (lab[:, :, 0] > 65)).astype("uint8") * 255)
    masks.append(((hsv[:, :, 0] > 70) & (hsv[:, :, 0] < 145) & (hsv[:, :, 1] > 14) & (hsv[:, :, 2] > 58)).astype("uint8") * 255)
    # Yellow / gold overseas-resident cards. This is not used alone unless the shape
    # looks like a large landscape card, so wood backgrounds are usually rejected.
    masks.append(((hsv[:, :, 0] >= 12) & (hsv[:, :, 0] <= 44) & (hsv[:, :, 1] > 22) & (hsv[:, :, 2] > 70)).astype("uint8") * 255)

    best_score = -1.0
    best_quad: np.ndarray | None = None

    for raw_mask in masks:
        mask = cv2.morphologyEx(
            raw_mask,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (max(19, int(w * 0.035)), max(11, int(h * 0.018)))),
            iterations=2,
        )
        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)),
            iterations=1,
        )
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            area = float(cv2.contourArea(c))
            area_ratio = area / max(img_area, 1.0)
            # Reject tiny inner objects and almost-full image/background masks.
            if not (0.055 <= area_ratio <= 0.78):
                continue
            rect = cv2.minAreaRect(c)
            rw, rh = rect[1]
            if rw <= 1 or rh <= 1:
                continue
            aspect = max(float(rw), float(rh)) / (min(float(rw), float(rh)) + 1e-6)
            if not (1.25 <= aspect <= 1.95):
                continue

            box = cv2.boxPoints(rect).astype(np.float32)
            ordered = np.array(_sort_corners(box), dtype=np.float32)
            q_area = abs(cv2.contourArea(ordered))
            fill_ratio = area / (q_area + 1e-6)
            if fill_ratio < 0.38:
                continue
            cx = float(np.mean(ordered[:, 0])) / max(float(w), 1.0)
            cy = float(np.mean(ordered[:, 1])) / max(float(h), 1.0)
            if not (0.12 <= cx <= 0.88 and 0.14 <= cy <= 0.88):
                continue

            border_touch = 0
            margin = min(w, h) * 0.018
            for x, y in ordered:
                if x <= margin or x >= w - margin or y <= margin or y >= h - margin:
                    border_touch += 1
            # If many corners touch the image boundary, this is usually the phone
            # screenshot/background frame, not the card.
            if border_touch >= 3:
                continue

            aspect_bias = 1.0 - min(abs(aspect - 1.58), 0.45) / 0.45
            center_bias_x = 1.0 - min(abs(cx - 0.50), 0.50) / 0.50
            center_bias_y = 1.0 - min(abs(cy - 0.52), 0.52) / 0.52
            # Prefer the largest good landscape region, but keep center/aspect checks.
            score = (
                area_ratio * 3.0
                + fill_ratio * 1.2
                + aspect_bias * 1.4
                + center_bias_x * 0.7
                + center_bias_y * 0.5
                - border_touch * 0.8
            )
            if score > best_score:
                best_score = score
                best_quad = ordered.reshape(4, 1, 2)

    return best_quad


def find_document_corners(pil_image: Image.Image) -> list[tuple[float, float]] | None:
    """Find passport/document corners robustly with contour scoring."""
    cv_img = np.array(pil_image.convert("RGB"))[:, :, ::-1]
    orig_h, orig_w = cv_img.shape[:2]
    if orig_h < 20 or orig_w < 20:
        return None

    resize_ratio = 900.0 / max(orig_h, orig_w)
    small = cv2.resize(cv_img, None, fx=resize_ratio, fy=resize_ratio, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    edge_maps: list[np.ndarray] = []
    for ksize in (3, 5):
        blurred = cv2.GaussianBlur(gray, (ksize, ksize), 0)
        edge_maps.append(cv2.Canny(blurred, 30, 100))
        edge_maps.append(cv2.Canny(blurred, 50, 150))
    edge_maps.append(cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 4))
    edge_maps.append(cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 4))

    img_area = float(small.shape[0] * small.shape[1])
    best_score = -1.0
    best_quad: np.ndarray | None = None
    valid_cnts: list[np.ndarray] = []
    candidates: list[dict[str, float | np.ndarray]] = []

    h, w = small.shape[:2]
    margin = min(w, h) * 0.03
    # Card color fallback is used only when no MRZ-like text is visible.
    # This prevents passport pages from being misclassified as residence cards.
    initial_mrz_bbox = _find_visible_mrz_bbox(small)
    card_color_quad: np.ndarray | None = None
    card_color_score = -1.0


    def _quad_metrics(quad: np.ndarray) -> dict[str, float]:
        pts = quad.reshape(4, 2).astype(np.float32)
        area = abs(cv2.contourArea(pts))
        if area <= img_area * 0.03:
            return {"valid": 0.0}
        rect = cv2.minAreaRect(pts)
        rw, rh = rect[1]
        if rw <= 1 or rh <= 1:
            return {"valid": 0.0}
        box_area = float(rw * rh)
        fill_ratio = float(area / (box_area + 1e-6))
        aspect = max(rw, rh) / (min(rw, rh) + 1e-6)

        # 문서 보정용 4점은 여권/카드 전체처럼 가로형 영역이어야 합니다.
        # 여권 내부의 증명사진 박스는 세로형 사각형이라 기존 minAreaRect 기준에서는
        # 문서 후보처럼 점수가 높아질 수 있으므로, 실제 좌상/우상/우하/좌하 기준의
        # 가로/세로 비율로 한 번 더 걸러냅니다. 사진 박스는 사진추출 단계에서만 사용합니다.
        ordered = np.array(_sort_corners(pts), dtype=np.float32)
        tl, tr, br, bl = ordered
        doc_w = 0.5 * (float(np.hypot(*(tr - tl))) + float(np.hypot(*(br - bl))))
        doc_h = 0.5 * (float(np.hypot(*(bl - tl))) + float(np.hypot(*(br - tr))))
        oriented_aspect = doc_w / max(doc_h, 1e-6)
        if oriented_aspect < 1.05:
            return {"valid": 0.0}

        target_aspects = (1.42, 1.58)
        aspect_penalty = min(min(abs(aspect - target) for target in target_aspects), 1.0)
        area_ratio = area / img_area

        # Penalize selecting the full image frame as a "document".
        border_touch = 0
        for x, y in pts:
            if x <= margin or x >= (w - margin) or y <= margin or y >= (h - margin):
                border_touch += 1
        center_x = float(np.mean(pts[:, 0])) / max(w, 1)
        center_y = float(np.mean(pts[:, 1])) / max(h, 1)
        return {
            "valid": 1.0,
            "area_ratio": float(area_ratio),
            "fill_ratio": float(fill_ratio),
            "aspect": float(aspect),
            "aspect_penalty": float(aspect_penalty),
            "border_touch": float(border_touch),
            "center_x": float(center_x),
            "center_y": float(center_y),
        }

    def score_quad(quad: np.ndarray) -> float:
        metrics = _quad_metrics(quad)
        if metrics.get("valid", 0.0) < 0.5:
            return -1.0

        area_ratio = float(metrics["area_ratio"])
        fill_ratio = float(metrics["fill_ratio"])
        aspect_penalty = float(metrics["aspect_penalty"])
        border_touch = float(metrics["border_touch"])

        border_penalty = border_touch * 1.0
        oversize_penalty = max(0.0, area_ratio - 0.80) * 9.0
        return (area_ratio * 2.1) + (fill_ratio * 1.3) - (aspect_penalty * 1.0) - border_penalty - oversize_penalty

    def try_update(quad: np.ndarray):
        nonlocal best_score, best_quad
        s = score_quad(quad)
        if s > best_score:
            best_score = s
            best_quad = quad
        metrics = _quad_metrics(quad)
        if metrics.get("valid", 0.0) < 0.5:
            return
        metrics["quad"] = quad
        candidates.append(metrics)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    for edges in edge_maps:
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)
        for mode in (cv2.RETR_EXTERNAL, cv2.RETR_LIST):
            cnts, _ = cv2.findContours(closed, mode, cv2.CHAIN_APPROX_SIMPLE)
            for c in cnts:
                area = cv2.contourArea(c)
                if not (img_area * 0.025 < area < img_area * 0.88):
                    continue
                valid_cnts.append(c)
                peri = cv2.arcLength(c, True)
                for eps in (0.018, 0.024, 0.03):
                    approx = cv2.approxPolyDP(c, eps * peri, True)
                    if len(approx) == 4:
                        try_update(approx.reshape(4, 1, 2))
                rect = cv2.minAreaRect(c)
                box = cv2.boxPoints(rect).astype(np.float32).reshape(4, 1, 2)
                try_update(box)

    # Card-specific color fallback. This catches cases where contour detection
    # locks on the inner portrait/text block instead of the full card body.
    if initial_mrz_bbox is None:
        color_quad = _find_card_outer_quad_by_color(small)
        if color_quad is not None:
            color_metrics = _quad_metrics(color_quad)
            if color_metrics.get("valid", 0.0) >= 0.5:
                card_color_quad = color_quad
                card_color_score = score_quad(color_quad) + float(color_metrics.get("area_ratio", 0.0)) * 1.5
                color_metrics["quad"] = color_quad
                candidates.append(color_metrics)

    # Secondary pass A:
    # Prefer card-like rectangles near the center for residence cards / ID cards.
    # This helps avoid selecting only a small left-side patch or photo box.
    card_preferred_quad: np.ndarray | None = None
    card_preferred_score = -1.0
    for c in candidates:
        area_ratio = float(c["area_ratio"])
        fill_ratio = float(c["fill_ratio"])
        aspect = float(c["aspect"])
        border_touch = float(c["border_touch"])
        center_x = float(c["center_x"])
        center_y = float(c["center_y"])

        if border_touch >= 3.0:
            continue
        if not (0.05 <= area_ratio <= 0.58):
            continue
        if not (1.30 <= aspect <= 1.90):
            continue

        center_bias_x = 1.0 - min(abs(center_x - 0.50), 0.50) / 0.50
        center_bias_y = 1.0 - min(abs(center_y - 0.56), 0.56) / 0.56
        aspect_bias = 1.0 - min(abs(aspect - 1.58), 0.50) / 0.50
        size_bias = 1.0 - min(abs(area_ratio - 0.22), 0.22) / 0.22
        card_score = (
            (fill_ratio * 1.4)
            + (center_bias_x * 1.2)
            + (center_bias_y * 0.9)
            + (aspect_bias * 1.5)
            + (size_bias * 1.0)
            - (border_touch * 0.8)
        )
        if card_score > card_preferred_score:
            card_preferred_score = card_score
            card_preferred_quad = c["quad"]  # type: ignore[assignment]

    # Secondary pass:
    # Prefer a lower-half passport data page candidate over the full-frame rectangle.
    # This avoids placing 4 points on the whole photo border for open-passport images.
    preferred_quad: np.ndarray | None = None
    preferred_score = -1.0
    for c in candidates:
        area_ratio = float(c["area_ratio"])
        fill_ratio = float(c["fill_ratio"])
        aspect = float(c["aspect"])
        aspect_penalty = float(c["aspect_penalty"])
        border_touch = float(c["border_touch"])
        center_x = float(c["center_x"])
        center_y = float(c["center_y"])
        if border_touch >= 2.0:
            continue
        # Avoid selecting tiny inner rectangles (e.g., portrait photo box).
        if not (0.16 <= area_ratio <= 0.68):
            continue
        # Passport data page is landscape-like; portrait-like boxes are invalid.
        if not (1.15 <= aspect <= 2.2):
            continue
        # Data page is usually near the horizontal center in full-passport photos.
        if not (0.33 <= center_x <= 0.70):
            continue

        # Data page tends to be in the lower half when a full open passport is shown.
        lower_bias = 1.0 - min(abs(center_y - 0.72), 0.60) / 0.60
        center_bias = 1.0 - min(abs(center_x - 0.50), 0.50) / 0.50
        data_score = (
            (area_ratio * 1.7)
            + (fill_ratio * 1.0)
            + (lower_bias * 1.8)
            + (center_bias * 0.7)
            - (aspect_penalty * 0.9)
            - (border_touch * 1.1)
        )
        if data_score > preferred_score:
            preferred_score = data_score
            preferred_quad = c["quad"]  # type: ignore[assignment]

    selected_mode = "generic"
    source_portrait_ratio = float(orig_h) / max(float(orig_w), 1.0)

    use_card_preferred = card_preferred_quad is not None and card_preferred_score >= max(1.55, preferred_score + 0.10)
    # In tall phone photos, open-passport images often contain a lower-half data page
    # that can accidentally look like a centered ID card. When a passport-page candidate
    # also exists, require a much larger score gap before overriding it with the card rule.
    if source_portrait_ratio > 1.10 and preferred_quad is not None and card_preferred_quad is not None:
        use_card_preferred = card_preferred_score >= max(1.85, preferred_score + 0.65)

    if use_card_preferred:
        best_quad = card_preferred_quad
        selected_mode = "card"
    elif preferred_quad is not None:
        best_quad = preferred_quad
        selected_mode = "passport_page"

    # If the color-based card body is clearly larger/better than the chosen
    # contour, prefer it. This mainly fixes cases where 4 points jump to the
    # portrait box or inner text area on residence cards.
    if card_color_quad is not None:
        use_color_card = False
        if best_quad is None:
            use_color_card = True
        else:
            current_metrics = _quad_metrics(best_quad)
            color_metrics = _quad_metrics(card_color_quad)
            cur_area = float(current_metrics.get("area_ratio", 0.0))
            color_area = float(color_metrics.get("area_ratio", 0.0))
            cur_aspect = float(current_metrics.get("aspect", 0.0))
            color_aspect = float(color_metrics.get("aspect", 0.0))
            # Strong preference when current selection is a smaller inner rectangle.
            if color_area >= cur_area * 1.18 and 1.25 <= color_aspect <= 1.95:
                use_color_card = True
            # Also allow if the normal card score was weak.
            if selected_mode == "generic" and card_color_score > best_score:
                use_color_card = True
        if use_color_card:
            best_quad = card_color_quad
            selected_mode = "card_color"

    # Tertiary fallback for hard cases (dark background / occlusion / off-center).
    if best_quad is None or preferred_score < 0.9:
        lower_quad = _find_lower_page_quad(small)
        if lower_quad is not None:
            best_quad = lower_quad
            selected_mode = "passport_lower"

    if best_quad is None:
        if valid_cnts:
            c = max(valid_cnts, key=cv2.contourArea)
            rect = cv2.minAreaRect(c)
            best_quad = cv2.boxPoints(rect).astype(np.float32).reshape(4, 1, 2)
            selected_mode = "generic"
        else:
            h, w = small.shape[:2]
            best_quad = np.array(
                [[[w * 0.02, h * 0.02]], [[w * 0.98, h * 0.02]], [[w * 0.98, h * 0.98]], [[w * 0.02, h * 0.98]]],
                dtype=np.float32,
            )
            selected_mode = "generic"

    # Landscape source photos usually contain a landscape ID/passport page filling
    # most of the frame. If the best contour is still a small inner rectangle
    # (portrait photo, hologram, QR area, etc.), use the visible frame as a safer
    # document start point. The user can still fine tune the 4 points manually.
    source_landscape_ratio = float(orig_w) / max(float(orig_h), 1.0)
    probe_bb = best_quad.reshape(4, 2).astype(np.float32)
    px1, py1 = float(np.min(probe_bb[:, 0])), float(np.min(probe_bb[:, 1]))
    px2, py2 = float(np.max(probe_bb[:, 0])), float(np.max(probe_bb[:, 1]))
    probe_w = px2 - px1
    probe_h = py2 - py1
    probe_area_ratio = abs(cv2.contourArea(probe_bb)) / max(img_area, 1.0)
    if (
        source_landscape_ratio >= 1.10
        and (probe_w < w * 0.76 or probe_h < h * 0.46 or probe_area_ratio < 0.36)
    ):
        inset_x = w * 0.018
        inset_y = h * 0.018
        best_quad = np.array(
            [[[inset_x, inset_y]], [[w - inset_x, inset_y]], [[w - inset_x, h - inset_y]], [[inset_x, h - inset_y]]],
            dtype=np.float32,
        )
        selected_mode = "landscape_frame"

    # If a wide MRZ exists but the selected rectangle only covers an inner box
    # (most commonly the face/photo area or a partial left block), expand the
    # correction target to the visible passport data page. This keeps "보정시작"
    # focused on the document page, while face boxes are reserved for "사진추출".
    mrz_bbox = initial_mrz_bbox
    if mrz_bbox is not None:
        mx1, my1, mx2, my2 = mrz_bbox
        quad_bb = best_quad.reshape(4, 2).astype(np.float32)
        qx1, qy1 = float(np.min(quad_bb[:, 0])), float(np.min(quad_bb[:, 1]))
        qx2, qy2 = float(np.max(quad_bb[:, 0])), float(np.max(quad_bb[:, 1]))
        q_w = qx2 - qx1
        q_h = qy2 - qy1
        mrz_w = mx2 - mx1
        # 기준 변경: 종이 외곽 전체보다 정보영역 + 얼굴사진 + MRZ 2줄이 중요합니다.
        # MRZ가 보이면 후보 사각형이 MRZ를 빠뜨리거나, MRZ 주변의 좁은 내부 박스만
        # 잡은 경우에는 MRZ 폭을 기준으로 여권 정보면 영역을 다시 구성합니다.
        selected_misses_mrz = q_w < (mrz_w * 0.82) or qx2 < (mx2 - w * 0.06) or qx1 > (mx1 + w * 0.06)
        selected_too_low_for_info = qy1 > max(0.0, my1 - h * 0.30)
        selected_too_short = q_h < h * 0.42
        if mrz_w >= w * 0.52 and (selected_misses_mrz or selected_too_low_for_info or selected_too_short):
            left = max(0.0, mx1 - w * 0.045)
            right = min(float(w), mx2 + w * 0.045)
            page_w = max(1.0, right - left)
            # MRZ 아래 글자만 잘리지 않으면 종이 여백은 조금 잘려도 됩니다.
            bottom = min(float(h), my2 + h * 0.075)
            # 위쪽은 이름/국적/생년월일/성별/얼굴 영역이 들어올 만큼 확보합니다.
            top_by_aspect = bottom - page_w / 1.42
            top_by_mrz = my1 - h * 0.62
            top = max(0.0, min(qy1, top_by_aspect, top_by_mrz))
            if bottom - top < h * 0.44:
                top = max(0.0, bottom - h * 0.76)
            best_quad = np.array(
                [[[left, top]], [[right, top]], [[right, bottom]], [[left, bottom]]],
                dtype=np.float32,
            )
            selected_mode = "passport_mrz_info_area"

    pts = best_quad.reshape(4, 2).astype("float32") / resize_ratio

    # Some open-passport photos still get classified as a centered card-like rectangle.
    # If the selected quad sits in the lower half of a tall phone image and looks like
    # a landscape data page, treat expansion as passport-like so the MRZ lines stay in.
    passport_like_card = False
    if selected_mode == "card":
        ordered_probe = np.array(_sort_corners(pts), dtype=np.float32)
        tlp, trp, brp, blp = ordered_probe
        probe_w = 0.5 * (float(np.hypot(*(trp - tlp))) + float(np.hypot(*(brp - blp))))
        probe_h = 0.5 * (float(np.hypot(*(blp - tlp))) + float(np.hypot(*(brp - trp))))
        probe_aspect = probe_w / max(probe_h, 1e-6)
        probe_area_ratio = abs(cv2.contourArea(ordered_probe)) / max(float(orig_w * orig_h), 1.0)
        probe_center_y = float(np.mean(ordered_probe[:, 1])) / max(float(orig_h), 1.0)
        passport_like_card = (
            source_portrait_ratio > 1.10
            and probe_center_y >= 0.58
            and probe_aspect >= 1.25
            and probe_area_ratio >= 0.12
        )

    # Open-passport photos often contain only the lower data page as the detected quad.
    # In those cases, the MRZ two lines sit very close to the bottom edge, so a larger
    # downward expansion is needed before perspective correction.
    if selected_mode.startswith("passport") or passport_like_card:
        side_ratio = 0.028 if source_portrait_ratio > 1.10 else 0.024
        top_ratio = 0.020 if source_portrait_ratio > 1.10 else 0.014
        bottom_ratio = 0.30 if source_portrait_ratio > 1.10 else 0.20
        pts = _expand_quad(
            pts,
            float(orig_w),
            float(orig_h),
            side_margin_ratio=side_ratio,
            top_margin_ratio=top_ratio,
            bottom_margin_ratio=bottom_ratio,
        )
    elif selected_mode in ("card", "card_color"):
        pts = _expand_quad(
            pts,
            float(orig_w),
            float(orig_h),
            side_margin_ratio=0.022,
            top_margin_ratio=0.012,
            bottom_margin_ratio=0.045,
        )
    else:
        pts = _expand_quad(pts, float(orig_w), float(orig_h))
    return _sort_corners(pts)



def analyze_passport_correction_quality(pil_image: Image.Image | None) -> dict:
    """
    Analyze whether the corrected document image is suitable for passport OCR.

    기준은 종이 전체가 아니라 정보 영역 + 하단 MRZ 2줄입니다.
    Empty paper margins may be cropped, but MRZ visibility and horizontal alignment
    are important for stable extraction.
    """
    if pil_image is None:
        return {
            "mrz_present": False,
            "mrz_angle": 0.0,
            "mrz_confidence": 0.0,
            "mrz_width_ratio": 0.0,
            "mrz_bottom_margin_ratio": 0.0,
            "issues": ["이미지가 없습니다."],
            "warnings": [],
        }

    rgb = pil_image.convert("RGB")
    cv_img = np.array(rgb)[:, :, ::-1]
    h, w = cv_img.shape[:2]
    issues: list[str] = []
    warnings: list[str] = []

    angle, confidence = _find_mrz_text_angle(cv_img)
    bbox = _find_visible_mrz_bbox(cv_img)
    mrz_present = bbox is not None and confidence > 0.15
    width_ratio = 0.0
    bottom_margin_ratio = 1.0
    left_margin_ratio = 1.0
    right_margin_ratio = 1.0

    if bbox is not None:
        x1, y1, x2, y2 = bbox
        width_ratio = float((x2 - x1) / max(w, 1))
        bottom_margin_ratio = float((h - y2) / max(h, 1))
        left_margin_ratio = float(x1 / max(w, 1))
        right_margin_ratio = float((w - x2) / max(w, 1))

    if not mrz_present:
        issues.append("MRZ 하단 2줄이 뚜렷하게 보이지 않습니다. 4점 보정에서 하단 MRZ를 포함해 주세요.")
    else:
        if width_ratio < 0.48:
            issues.append("MRZ 폭이 너무 짧게 잡혔습니다. 좌우가 잘리지 않게 4점을 넓혀 주세요.")
        elif width_ratio < 0.58:
            warnings.append("MRZ 폭이 조금 짧습니다. 좌우 여백을 조금 더 포함하면 인식률이 올라갑니다.")

        if abs(angle) >= 2.2:
            issues.append(f"MRZ 기울기 {angle:+.1f}° - 4점 보정에서 MRZ를 더 가로로 맞춰 주세요.")
        elif abs(angle) >= 1.1:
            warnings.append(f"MRZ 기울기 {angle:+.1f}° - 가능하면 더 수평으로 맞추면 좋습니다.")

        if bottom_margin_ratio <= 0.004:
            issues.append("MRZ 아래쪽이 거의 붙어 있습니다. 하단이 잘렸을 수 있으니 조금 아래까지 포함해 주세요.")
        elif bottom_margin_ratio <= 0.018:
            warnings.append("MRZ 아래 여백이 적습니다. 하단 2줄이 완전히 보이는지 확인해 주세요.")

        if left_margin_ratio <= 0.004 or right_margin_ratio <= 0.004:
            warnings.append("MRZ 좌우 끝이 화면 가장자리에 가깝습니다. 여권 번호/체크문자가 잘리지 않았는지 확인해 주세요.")

    return {
        "mrz_present": bool(mrz_present),
        "mrz_angle": round(float(angle), 3),
        "mrz_confidence": round(float(confidence), 3),
        "mrz_width_ratio": round(float(width_ratio), 4),
        "mrz_bottom_margin_ratio": round(float(bottom_margin_ratio), 4),
        "issues": issues,
        "warnings": warnings,
    }


def extract_portrait_aligned(rectified_image: Image.Image) -> Image.Image | None:
    """
    보정된(수평이 맞춰진) 여권 이미지에서 인물 사진 영역을 추출합니다.
    """
    cv_img = np.array(rectified_image.convert("RGB"))[:, :, ::-1]
    h, w = cv_img.shape[:2]

    # 여권 데이터 페이지에서 얼굴은 보통 좌측 5~42% 사이에 위치
    # 상하 위치는 5~90% 사이
    roi_x2 = int(w * 0.45) if w > 400 else w
    portrait_roi = cv_img[int(h*0.05):int(h*0.9), int(w*0.02):roi_x2]
    
    # ── [AI 옵션] 얼굴 인식 시도 ─────────────────────────────────────────────
    try:
        gray_roi = cv2.cvtColor(portrait_roi, cv2.COLOR_BGR2GRAY)
        # Haar Cascade 경로 확인
        xml_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        face_cascade = cv2.CascadeClassifier(xml_path)
        faces = face_cascade.detectMultiScale(gray_roi, 1.1, 4)

        if len(faces) > 0:
            # 가장 큰 얼굴 선택
            fx, fy, fw, fh = max(faces, key=lambda f: f[2]*f[3])
            # 얼굴 주위로 여유 공간(Padding) 추가 (증명사진 느낌)
            pad_w = int(fw * 0.5)
            pad_h = int(fh * 0.7)
            
            y1 = max(0, fy - pad_h)
            y2 = min(portrait_roi.shape[0], fy + fh + int(pad_h * 0.5))
            x1 = max(0, fx - pad_w)
            x2 = min(portrait_roi.shape[1], fx + fw + pad_w)
            
            final_portrait = portrait_roi[y1:y2, x1:x2]
        else:
            final_portrait = portrait_roi
    except Exception:
        # 실패 시 ROI 전체 사용
        final_portrait = portrait_roi

    # PIL 이미지로 변환해 반환
    res = cv2.cvtColor(final_portrait, cv2.COLOR_BGR2RGB)
    return Image.fromarray(res)


def _detect_largest_face(cv_img_bgr: np.ndarray) -> tuple[int, int, int, int] | None:
    try:
        gray = cv2.cvtColor(cv_img_bgr, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 40))
        if len(faces) == 0:
            return None
        fx, fy, fw, fh = max(faces, key=lambda f: int(f[2]) * int(f[3]))
        return int(fx), int(fy), int(fw), int(fh)
    except Exception:
        return None

def _clamp_norm_rect(x: float, y: float, width: float, height: float) -> tuple[float, float, float, float]:
    width = max(0.04, min(1.0, float(width)))
    height = max(0.06, min(1.0, float(height)))
    x = max(0.0, min(1.0 - width, float(x)))
    y = max(0.0, min(1.0 - height, float(y)))
    return (x, y, width, height)


def _score_portrait_candidate_roi(roi: np.ndarray) -> float:
    if roi is None or roi.size == 0:
        return -1.0
    try:
        rh, rw = roi.shape[:2]
        if rh < 40 or rw < 30:
            return -1.0
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(28, 28))
        face_bonus = 0.0
        if len(faces) > 0:
            _fx, _fy, fw, fh = max(faces, key=lambda f: int(f[2]) * int(f[3]))
            face_bonus = float(fw * fh) / float(max(1, rw * rh)) * 2500.0
        edge_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        contrast_score = float(gray.std())
        # 사진 영역은 배경/얼굴/옷 때문에 일정한 질감과 대비가 있고, 빈 홀로그램·QR 단독 영역보다 점수가 안정적입니다.
        return face_bonus + edge_score * 0.45 + contrast_score * 2.0
    except Exception:
        return -1.0


def estimate_portrait_rect(image: Image.Image) -> tuple[float, float, float, float] | None:
    """
    Returns normalized (x, y, width, height) from 0.0 to 1.0 of the expected portrait location,
    to safely initialize an interactive cropping overlay for the user.
    """
    cv_img = np.array(image.convert("RGB"))[:, :, ::-1]
    h, w = cv_img.shape[:2]
    if h < 40 or w < 40:
        return None

    face = _detect_largest_face(cv_img)
    if face is not None:
        fx, fy, fw, fh = face
        pad_w = int(fw * 0.65)
        pad_h = int(fh * 0.85)
        x1 = max(0, fx - pad_w)
        y1 = max(0, fy - pad_h)
        x2 = min(w, fx + fw + pad_w)
        y2 = min(h, fy + fh + int(pad_h * 0.45))
        return _clamp_norm_rect(x1 / w, y1 / h, (x2 - x1) / w, (y2 - y1) / h)

    ratio = (w / h) if h else 0
    if 1.30 <= ratio <= 1.95:  # ID Card
        # 카드형은 사진이 좌측/우측 모두 가능하므로 양쪽 큰 사진 후보를 점수화합니다.
        candidates = [
            (0.02, 0.08, 0.34, 0.74),
            (0.58, 0.08, 0.39, 0.74),
        ]
        scored: list[tuple[float, tuple[float, float, float, float]]] = []
        for box in candidates:
            x, y, bw, bh = box
            roi = cv_img[int(h * y):int(h * (y + bh)), int(w * x):int(w * (x + bw))]
            scored.append((_score_portrait_candidate_roi(roi), box))
        scored.sort(key=lambda item: item[0], reverse=True)
        if scored and scored[0][0] >= 12.0:
            return _clamp_norm_rect(*scored[0][1])
        return (0.60, 0.10, 0.35, 0.70)

    # Passport
    return (0.05, 0.18, 0.28, 0.51)

def extract_card_portrait(card_image: Image.Image) -> Image.Image | None:
    """Extract the main portrait from residence-card style documents."""
    cv_img = np.array(card_image.convert("RGB"))[:, :, ::-1]
    h, w = cv_img.shape[:2]
    if h < 40 or w < 40:
        return None

    # 1) Full-image face detection first. Choose the largest face only.
    face = _detect_largest_face(cv_img)
    if face is not None:
        fx, fy, fw, fh = face
        pad_w = int(fw * 0.65)
        pad_h = int(fh * 0.85)
        x1 = max(0, fx - pad_w)
        y1 = max(0, fy - pad_h)
        x2 = min(w, fx + fw + pad_w)
        y2 = min(h, fy + fh + int(pad_h * 0.45))
        crop = cv_img[y1:y2, x1:x2]
        if crop.size > 0:
            return Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))

    # 2) Fallback to the large portrait zones only.
    candidates = [
        cv_img[int(h * 0.08):int(h * 0.82), int(w * 0.02):int(w * 0.36)],
        cv_img[int(h * 0.08):int(h * 0.82), int(w * 0.58):int(w * 0.97)],
    ]
    best = None
    best_score = -1.0
    for roi in candidates:
        if roi.size == 0:
            continue
        rh, rw = roi.shape[:2]
        if rh < 40 or rw < 40:
            continue
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        score = float(gray.var()) + float(cv2.Laplacian(gray, cv2.CV_64F).var()) * 0.6
        if score > best_score:
            best_score = score
            best = roi
    if best is None:
        return None
    return Image.fromarray(cv2.cvtColor(best, cv2.COLOR_BGR2RGB))


def extract_main_portrait(image: Image.Image | None) -> Image.Image | None:
    if image is None:
        return None
    width, height = image.size
    ratio = (width / height) if height else 0.0

    # Card-shaped document: extract only the large main portrait.
    if ratio >= 1.30 and ratio <= 1.95:
        card_portrait = extract_card_portrait(image)
        if card_portrait is not None:
            return card_portrait

    portrait = extract_portrait_aligned(image)
    if portrait is not None:
        return portrait
    return None


def _sort_corners(pts: np.ndarray) -> list[tuple[float, float]]:
    """4점을 Top-Left, Top-Right, Bottom-Right, Bottom-Left 순으로 정렬"""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return [(float(p[0]), float(p[1])) for p in rect]


def _expand_quad(
    pts: np.ndarray,
    img_w: float,
    img_h: float,
    side_margin_ratio: float = 0.02,
    top_margin_ratio: float = 0.01,
    bottom_margin_ratio: float = 0.05,
) -> np.ndarray:
    """
    Expand detected quad with stronger bottom margin.
    This keeps lower MRZ text and bottom border from being clipped.
    """
    # Ensure order: tl, tr, br, bl
    ordered = np.array(_sort_corners(pts), dtype=np.float32)
    tl, tr, br, bl = ordered

    def _normalize(v: np.ndarray) -> np.ndarray:
        n = float(np.hypot(v[0], v[1]))
        if n < 1e-6:
            return np.array([0.0, 0.0], dtype=np.float32)
        return (v / n).astype(np.float32)

    top_edge = _normalize(tr - tl)
    bottom_edge = _normalize(br - bl)
    left_edge = _normalize(bl - tl)
    right_edge = _normalize(br - tr)

    xdir = _normalize(top_edge + bottom_edge)
    ydir = _normalize(left_edge + right_edge)
    if float(np.hypot(xdir[0], xdir[1])) < 1e-6:
        xdir = np.array([1.0, 0.0], dtype=np.float32)
    if float(np.hypot(ydir[0], ydir[1])) < 1e-6:
        ydir = np.array([0.0, 1.0], dtype=np.float32)

    width = 0.5 * (float(np.hypot(*(tr - tl))) + float(np.hypot(*(br - bl))))
    height = 0.5 * (float(np.hypot(*(bl - tl))) + float(np.hypot(*(br - tr))))

    mx = max(2.0, width * side_margin_ratio)
    my_top = max(1.0, height * top_margin_ratio)
    my_bottom = max(3.0, height * bottom_margin_ratio)

    tl2 = tl - xdir * mx - ydir * my_top
    tr2 = tr + xdir * mx - ydir * my_top
    bl2 = bl - xdir * mx + ydir * my_bottom
    br2 = br + xdir * mx + ydir * my_bottom

    expanded = np.array([tl2, tr2, br2, bl2], dtype=np.float32)
    expanded[:, 0] = np.clip(expanded[:, 0], 0.0, img_w - 1.0)
    expanded[:, 1] = np.clip(expanded[:, 1], 0.0, img_h - 1.0)
    return expanded

