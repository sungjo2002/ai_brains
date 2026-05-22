from __future__ import annotations

# 사업장별 시간 환산 기준 기본값.
# 이 값은 프로그램 기능에 고정 계산식으로 쓰는 값이 아니라,
# 설정 화면의 [기본 사업장 환산표 불러오기] 버튼을 눌렀을 때
# 일반 설정 데이터로 저장되는 초기 입력값이다.


def _rule(
    work_site_name: str,
    area_name: str = "",
    conversion_type: str = "시간대별",
    day_type: str = "",
    shift_type: str = "",
    start_time: str = "",
    end_time: str = "",
    base_hours: float = 0,
    over_hours: float = 0,
    night_hours: float = 0,
    special_hours: float = 0,
    special_over_hours: float = 0,
    holiday_special_hours: float = 0,
    weekly_holiday_hours: float = 0,
    value_type: str = "실제시간",
    memo: str = "",
    business_name: str = "",
) -> dict:
    return {
        "business_name": business_name,
        "work_site_name": work_site_name,
        "area_name": area_name,
        "conversion_type": conversion_type,
        "day_type": day_type,
        "shift_type": shift_type,
        "start_time": start_time,
        "end_time": end_time,
        "base_hours": base_hours,
        "over_hours": over_hours,
        "night_hours": night_hours,
        "special_hours": special_hours,
        "special_over_hours": special_over_hours,
        "holiday_special_hours": holiday_special_hours,
        "weekly_holiday_hours": weekly_holiday_hours,
        "value_type": value_type,
        "memo": memo,
    }


def _add_day_rows(rows: list[dict], day_type: str, start: str, ends: list[str], base: float, overs: list[float], nights: list[float], *, area: str = "무진") -> None:
    for end, over, night in zip(ends, overs, nights):
        rows.append(_rule("광명산업", area, "시간대별", day_type, "야간", start, end, base, over, night, value_type="실제시간"))


def _add_weekend_rows(rows: list[dict], day_type: str, start: str, ends: list[str], special: float, special_overs: list[float], nights: list[float], *, area: str = "무진") -> None:
    for end, special_over, night in zip(ends, special_overs, nights):
        rows.append(_rule("광명산업", area, "시간대별", day_type, "야간", start, end, 0, 0, night, special, special_over, value_type="실제시간"))


def _build_gwangmyeong_mujin_rows() -> list[dict]:
    rows: list[dict] = []
    day_ends = ["16:00", "17:00", "18:00", "19:00", "20:00", "21:00"]
    for idx, end in enumerate(day_ends):
        rows.append(_rule("광명산업", "무진", "시간대별", "평일", "주간", "07:00", end, 8, idx, 0, value_type="실제시간"))
    _add_day_rows(rows, "평일", "16:00", ["01:00", "02:00", "03:00", "04:00", "05:00", "06:00", "07:00"], 8, [0, 1, 2, 3, 4, 5, 6], [3, 4, 5, 6, 7, 8, 8])
    _add_day_rows(rows, "평일", "17:00", ["02:00", "03:00", "04:00", "05:00", "06:00", "07:00", "08:00"], 8, [0, 1, 2, 3, 4, 5, 6], [4, 5, 6, 7, 8, 8, 8])
    _add_day_rows(rows, "평일", "18:00", ["03:00", "04:00", "05:00", "06:00", "07:00", "08:00", "09:00"], 8, [0, 1, 2, 3, 4, 5, 6], [5, 6, 7, 8, 8, 8, 8])

    for idx, end in enumerate(day_ends):
        rows.append(_rule("광명산업", "무진", "시간대별", "주말", "주간", "07:00", end, 0, 0, 0, 8, idx, value_type="실제시간"))
    _add_weekend_rows(rows, "주말", "16:00", ["01:00", "02:00", "03:00", "04:00", "05:00", "06:00", "07:00"], 8, [0, 1, 2, 3, 4, 5, 6], [3, 4, 5, 6, 7, 8, 8])
    _add_weekend_rows(rows, "주말", "17:00", ["02:00", "03:00", "04:00", "05:00", "06:00", "07:00", "08:00"], 8, [0, 1, 2, 3, 4, 5, 6], [4, 5, 6, 7, 8, 8, 8])
    _add_weekend_rows(rows, "주말", "18:00", ["03:00", "04:00", "05:00", "06:00", "07:00", "08:00", "09:00"], 8, [0, 1, 2, 3, 4, 5, 6], [5, 6, 7, 8, 8, 8, 8])

    # 무진 2장: 배율이 반영된 마감환산표 예시값.
    # 이미지에서 식별 가능한 핵심값 위주로 넣고, 확인이 필요한 행은 메모에 표시한다.
    rows.extend([
        _rule("광명산업", "무진", "마감환산표", "평일", "주간", "07:00", "16:00", 8, 0, 0, value_type="마감환산값"),
        _rule("광명산업", "무진", "마감환산표", "평일", "주간", "07:00", "17:00", 8, 1.5, 0, value_type="마감환산값"),
        _rule("광명산업", "무진", "마감환산표", "평일", "주간", "07:00", "18:00", 8, 3, 0, value_type="마감환산값"),
        _rule("광명산업", "무진", "마감환산표", "평일", "야간", "18:00", "03:00", 8, 0, 2.5, value_type="마감환산값", memo="무진 2장 이미지 기준"),
        _rule("광명산업", "무진", "마감환산표", "토요일", "야간", "18:00", "03:00", 8, 4, 2.5, value_type="마감환산값", memo="무진 2장 이미지 기준"),
        _rule("광명산업", "무진", "마감환산표", "일요일공휴일", "주간", "07:00", "16:00", 8, 12, 0, value_type="마감환산값", memo="무진 2장 이미지 기준"),
    ])
    return rows


def _build_hyunwoo_rows() -> list[dict]:
    return [
        _rule("현우", "", "시간대별", "평일", "주간", "08:00", "17:00", 8, 0, 0, value_type="실제시간"),
        _rule("현우", "", "시간대별", "평일", "주간", "08:00", "19:30", 8, 3, 0, value_type="실제시간"),
        _rule("현우", "", "시간대별", "평일", "주간", "08:00", "19:30", 8, 2.25, 0, value_type="실제시간", memo="30분 지각"),
        _rule("현우", "", "시간대별", "평일", "주간", "08:00", "19:30", 8, 2.5, 0, value_type="실제시간", memo="20분 지각"),
        _rule("현우", "", "시간대별", "평일", "야간", "20:00", "01:00", 4, 0, 1, value_type="실제시간"),
        _rule("현우", "", "시간대별", "평일", "야간", "20:00", "05:00", 8, 0, 3, value_type="실제시간"),
        _rule("현우", "", "시간대별", "평일", "야간", "20:00", "07:30", 8, 3, 3.25, value_type="실제시간"),
        _rule("현우", "", "시간대별", "토요일", "주간", "08:00", "17:00", 8, 4, 0, value_type="실제시간"),
        _rule("현우", "", "시간대별", "토요일", "야간", "20:00", "05:00", 8, 4, 3, value_type="실제시간"),
        _rule("현우", "", "시간대별", "공휴일", "주간", "08:00", "17:00", 8, 12, 0, value_type="실제시간"),
        _rule("현우", "", "시간대별", "공휴일", "야간", "20:00", "05:00", 8, 12, 3, value_type="실제시간"),
    ]


def _build_gsteel_rows() -> list[dict]:
    rows: list[dict] = []
    for day in [1]:
        rows.append(_rule("지스틸", "강동", "날짜별월간", "평일", "월간", str(day), "", 8, 0, 0, value_type="날짜별"))
    rows.append(_rule("지스틸", "강동", "날짜별월간", "평일", "월간", "2", "", 8, 0, 0, value_type="날짜별", memo="여름휴가"))
    for day in [5, 6, 7, 8, 9]:
        rows.append(_rule("지스틸", "강동", "날짜별월간", "평일", "월간", str(day), "", 8, 2, 7, value_type="날짜별"))
    rows.append(_rule("지스틸", "강동", "날짜별월간", "토요일", "월간", "10", "", 0, 0, 0, 8, 4, value_type="날짜별"))
    for day in [12, 13, 14]:
        rows.append(_rule("지스틸", "강동", "날짜별월간", "평일", "월간", str(day), "", 8, 2, 0, value_type="날짜별"))
    rows.append(_rule("지스틸", "강동", "날짜별월간", "공휴일", "월간", "15", "", 8, 0, 0, 0, 0, 8, value_type="날짜별"))
    rows.append(_rule("지스틸", "강동", "날짜별월간", "평일", "월간", "16", "", 8, 2, 0, value_type="날짜별"))
    rows.append(_rule("지스틸", "강동", "날짜별월간", "토요일", "월간", "17", "", 0, 0, 0, 8, 5, value_type="날짜별"))
    rows.append(_rule("지스틸", "강동", "날짜별월간", "주휴", "월간", "18", "", 0, 0, 0, 0, 0, 0, 8, value_type="날짜별"))
    for day in [19, 20]:
        rows.append(_rule("지스틸", "강동", "날짜별월간", "평일", "월간", str(day), "", 8, 2, 7, value_type="날짜별"))
    return rows


def _build_ecoinsutech_rows() -> list[dict]:
    return [
        _rule("에코인슈텍", "양산", "항목별배율", "전체", "배율", "", "", 1, 1.5, 0, 1.5, 2, 0, 1, value_type="배율계산"),
    ]


DEFAULT_SITE_TIME_CONVERSION_RULES: list[dict] = [
    *_build_gwangmyeong_mujin_rows(),
    *_build_hyunwoo_rows(),
    *_build_gsteel_rows(),
    *_build_ecoinsutech_rows(),
]
