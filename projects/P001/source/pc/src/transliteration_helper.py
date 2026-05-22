import re

# 현장 등록용 이름 변환 기준:
# OCR로 읽은 영문 이름을 공식 번역이 아니라 한국 현장에서 부르기 쉬운 발음 표기로 바꾼다.
# 정확한 현지 발음보다 현장에서 부르기 쉬운 한국식 표기를 우선하며, 자주 나오는 이름은 아래 TOKEN_MAP을 우선 보강한다.
TOKEN_MAP = {
    # 베트남 성/중간이름/이름에서 자주 나오는 표기
    "NGUYEN": "응우옌",
    "TRAN": "트란",
    "LE": "레",
    "PHAM": "팜",
    "HOANG": "호앙",
    "HUYNH": "후인",
    "PHAN": "판",
    "VU": "부",
    "VO": "보",
    "DANG": "당",
    "BUI": "부이",
    "DO": "도",
    "NGO": "응오",
    "DUONG": "즈엉",
    "DINH": "딘",
    "TRUONG": "쯔엉",
    "TRINH": "찐",
    "LY": "리",
    "HO": "호",

    "VAN": "반",
    "THI": "티",
    "HUU": "흐우",
    "CONG": "꽁",
    "QUOC": "꾸옥",
    "QUANG": "꽝",

    "AN": "안",
    "ANH": "아인",
    "BAO": "바오",
    "BAC": "박",
    "BINH": "빈",
    "CHAU": "쩌우",
    "CUONG": "끄엉",
    "DAT": "닷",
    "DUC": "득",
    "DUNG": "중",
    "DUY": "주이",
    "GIANG": "장",
    "HA": "하",
    "HAI": "하이",
    "HANH": "하인",
    "HIEU": "히에우",
    "HIEN": "히엔",
    "HOA": "화",
    "HOAI": "호아이",
    "HOAN": "호안",
    "HONG": "홍",
    "HUNG": "훙",
    "HUONG": "흐엉",
    "KHA": "카",
    "KHAI": "카이",
    "KHANH": "카인",
    "KHANG": "캉",
    "KHOA": "코아",
    "KIEN": "끼엔",
    "LAN": "란",
    "LINH": "린",
    "LONG": "롱",
    "MAI": "마이",
    "MINH": "민",
    "NAM": "남",
    "NGA": "응아",
    "NGOC": "응옥",
    "NHAN": "년",
    "NHAT": "녓",
    "NHI": "니",
    "NHU": "뉴",
    "NHUNG": "늉",
    "PHAT": "팟",
    "PHONG": "퐁",
    "PHUC": "푹",
    "SANG": "상",
    "SON": "선",
    "TAM": "땀",
    "TAN": "떤",
    "THAI": "타이",
    "THANH": "타인",
    "THAO": "타오",
    "THIEN": "티엔",
    "THINH": "틴",
    "THU": "투",
    "THUY": "투이",
    "TIEN": "띠엔",
    "TOAN": "또안",
    "TRANG": "짱",
    "TRI": "찌",
    "TRUC": "쭉",
    "TUNG": "뚱",
    "TU": "뚜",
    "TUAN": "뚜언",
    "VY": "비",
    "XUAN": "쑤언",
    "YEN": "옌",

    # 중국식 이름에서 자주 나오는 표기
    "ZHANG": "장",
    "WANG": "왕",
    "LI": "리",
    "CHEN": "천",
    "LIU": "류",
    "YANG": "양",
    "HUANG": "황",
    "ZHAO": "자오",
    "WU": "우",
    "ZHOU": "저우",
    "XU": "쉬",
    "SUN": "쑨",
    "MA": "마",
    "ZHU": "주",
    "GUO": "궈",
    "HE": "허",
    "LUO": "뤄",
    "GAO": "가오",
    "LIN": "린",
    "XIAO": "샤오",
    "WEI": "웨이",
    "MING": "밍",
    "JUN": "쥔",
    "JIE": "지에",
    "HUA": "화",
    "YING": "잉",
    "FANG": "팡",
    "QIANG": "창",
    "XIN": "신",
    "TAO": "타오",
    "XIA": "샤",
    "QIN": "친",
    "QING": "칭",
    "YAN": "옌",
    "YU": "위",
    "YUE": "위에",
    "HUI": "후이",

    # 우즈베키스탄/러시아식 이름에서 자주 나오는 표기
    "ABDULLAEV": "압둘라예프",
    "ABDULLAYEV": "압둘라예프",
    "ABDULLOEV": "압둘로예프",
    "AKHMADOV": "아흐마도프",
    "AHMADOV": "아흐마도프",
    "AKHMEDOV": "아흐메도프",
    "RUSTAM": "루스탐",
    "BEKZOD": "벡조드",
    "BEKZOT": "벡조트",
    "KARIMOV": "카리모프",
    "KARIMOVA": "카리모바",
    "ALIEV": "알리예프",
    "ALIYEV": "알리예프",
    "MAMATOV": "마마토프",
    "MAMADOV": "마마도프",
    "TURSUNOV": "투르수노프",
    "RAKHIMOV": "라히모프",
    "IBRAGIMOV": "이브라기모프",
    "ISLOMOV": "이슬로모프",
    "SHERZOD": "셰르조드",
    "AZIZ": "아지즈",
    "AZIZBEK": "아지즈벡",
    "FARRUKH": "파르루흐",
    "JASUR": "자수르",
    "JAMSHID": "잠시드",
    "DILSHOD": "딜쇼드",
    "OYBEK": "오이벡",
    "NODIR": "노디르",
    "SARDOR": "사르도르",
    "TEMUR": "테무르",
    "UMID": "우미드",
    "ALEXANDER": "알렉산더",
    "ALEXANDR": "알렉산드르",
    "ALEKSANDR": "알렉산드르",
    "SERGEY": "세르게이",
    "SERGEI": "세르게이",
    "ANDREY": "안드레이",
    "ANDREI": "안드레이",
    "DMITRY": "드미트리",
    "DMITRII": "드미트리",
    "IVAN": "이반",
    "KIM": "킴",
    "KLIUEV": "클리우예프",
    "AMANGELDIYEVA": "아만겔디예바",
    "AMANGELDIYE": "아만겔디예바",
    "AMANGELDIVEVA": "아만겔디예바",
    "AY": "아이",
    "AULYM": "아울림",

    # 태국 여권/현장 등록에서 확인된 이름 표기
    "THAMMASAREEPONG": "탐마사리퐁",
    "TANASAK": "타나삭",
}

# 긴 철자부터 먼저 처리해야 NGUYEN, ABDULLAEV 같은 이름이 깨지지 않는다.
MULTI_RULES = [
    ("DZH", "즈"), ("KH", "흐"), ("SH", "시"), ("ZH", "즈"), ("CH", "치"),
    ("TS", "츠"), ("DZ", "즈"), ("TH", "트"), ("PH", "프"), ("QU", "쿠"),
    ("NG", "응"), ("OO", "우"), ("EE", "이"), ("OU", "우"), ("AU", "아우"),
    ("AI", "아이"), ("EI", "에이"), ("OI", "오이"), ("UY", "우이"),
    ("YE", "예"), ("YA", "야"), ("YU", "유"), ("YO", "요"),
    ("IA", "이아"), ("IE", "이에"), ("IO", "이오"),
]

SYLLABLE_RULES = [
    ("BA", "바"), ("BE", "베"), ("BI", "비"), ("BO", "보"), ("BU", "부"),
    ("CA", "카"), ("CE", "세"), ("CI", "시"), ("CO", "코"), ("CU", "쿠"),
    ("DA", "다"), ("DE", "데"), ("DI", "디"), ("DO", "도"), ("DU", "두"),
    ("FA", "파"), ("FE", "페"), ("FI", "피"), ("FO", "포"), ("FU", "푸"),
    ("GA", "가"), ("GE", "게"), ("GI", "기"), ("GO", "고"), ("GU", "구"),
    ("HA", "하"), ("HE", "헤"), ("HI", "히"), ("HO", "호"), ("HU", "후"),
    ("JA", "자"), ("JE", "제"), ("JI", "지"), ("JO", "조"), ("JU", "주"),
    ("KA", "카"), ("KE", "케"), ("KI", "키"), ("KO", "코"), ("KU", "쿠"),
    ("LA", "라"), ("LE", "레"), ("LI", "리"), ("LO", "로"), ("LU", "루"),
    ("MA", "마"), ("ME", "메"), ("MI", "미"), ("MO", "모"), ("MU", "무"),
    ("NA", "나"), ("NE", "네"), ("NI", "니"), ("NO", "노"), ("NU", "누"),
    ("PA", "파"), ("PE", "페"), ("PI", "피"), ("PO", "포"), ("PU", "푸"),
    ("RA", "라"), ("RE", "레"), ("RI", "리"), ("RO", "로"), ("RU", "루"),
    ("SA", "사"), ("SE", "세"), ("SI", "시"), ("SO", "소"), ("SU", "수"),
    ("TA", "타"), ("TE", "테"), ("TI", "티"), ("TO", "토"), ("TU", "투"),
    ("VA", "바"), ("VE", "베"), ("VI", "비"), ("VO", "보"), ("VU", "부"),
    ("WA", "와"), ("WE", "웨"), ("WI", "위"), ("WO", "워"), ("WU", "우"),
    ("XA", "자"), ("XE", "제"), ("XI", "시"), ("XO", "조"), ("XU", "주"),
    ("ZA", "자"), ("ZE", "제"), ("ZI", "지"), ("ZO", "조"), ("ZU", "주"),
]

SINGLE_MAP = {
    "A": "아", "B": "브", "C": "크", "D": "드", "E": "에", "F": "프", "G": "그",
    "H": "흐", "I": "이", "J": "즈", "K": "크", "L": "르", "M": "므", "N": "느",
    "O": "오", "P": "프", "Q": "크", "R": "르", "S": "스", "T": "트", "U": "우",
    "V": "브", "W": "우", "X": "크스", "Y": "이", "Z": "즈",
}


def _clean_token(token: str) -> str:
    return re.sub(r"[^A-Z]", "", token.upper())


def _fallback_token_to_korean(token: str) -> str:
    text = _clean_token(token)
    if not text:
        return ""
    for eng, kor in MULTI_RULES + SYLLABLE_RULES:
        text = text.replace(eng, kor)
    return "".join(SINGLE_MAP.get(ch, ch) for ch in text).strip()


def transliterate_english_to_korean(name: str) -> str:
    """
    영문 이름을 현장에서 부르기 쉬운 한국식 발음 표기로 변환한다.
    예: TRAN VAN BAO -> 트란 반 바오
    """
    if not name:
        return ""

    cleaned = re.sub(r"[^A-Za-z\s'\-.]", " ", str(name).upper())
    cleaned = re.sub(r"[\-'.]+", " ", cleaned)
    tokens = [tok for tok in cleaned.split() if tok]
    result: list[str] = []

    for token in tokens:
        key = _clean_token(token)
        if not key:
            continue
        result.append(TOKEN_MAP.get(key) or _fallback_token_to_korean(key))

    return " ".join(part for part in result if part).strip()


if __name__ == "__main__":
    samples = [
        "NGUYEN VAN AN", "TRAN VAN MINH", "PHAM THI HOA", "LE VAN DUC",
        "HOANG MINH TUAN", "ZHANG WEI", "WANG LI", "ABDULLAEV", "RUSTAM", "BEKZOD",
        "THAMMASAREEPONG TANASAK",
    ]
    for sample in samples:
        print(sample, "->", transliterate_english_to_korean(sample))
