# D:\alfa\Documents\Antigravity\lomba-it-radar\src\classifier.py
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple

from src.models import CompetitionCategory

WIB_TZ = timezone(timedelta(hours=7))

MONTH_NAME_TO_NUM: dict[str, int] = {
    "jan": 1,
    "januari": 1,
    "january": 1,
    "feb": 2,
    "februari": 2,
    "february": 2,
    "mar": 3,
    "maret": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "mei": 5,
    "may": 5,
    "jun": 6,
    "juni": 6,
    "june": 6,
    "jul": 7,
    "juli": 7,
    "july": 7,
    "agu": 8,
    "agustus": 8,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "okt": 10,
    "oktober": 10,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "des": 12,
    "desember": 12,
    "dec": 12,
    "december": 12,
}

# Category keyword mapping (Indonesian & English terms)
CATEGORY_PATTERNS: dict[CompetitionCategory, list[str]] = {
    CompetitionCategory.HACKATHON: [
        r"\bhackathon\b",
        r"\bsoftware\s+development\b",
        r"\bweb\s+dev(?:elopment)?\b",
        r"\bmobile\s+dev(?:elopment)?\b",
        r"\bapp(?:lication)?\s+development\b",
        r"\blomba\s+web\b",
        r"\blomba\s+aplikasi\b",
        r"\binovasi\s+digital\b",
        r"\biot\b",
        r"\binternet\s+of\s+things\b",
        r"\bgame\s+dev(?:elopment)?\b",
    ],
    CompetitionCategory.CYBERSECURITY: [
        r"\bctf\b",
        r"\bcapture\s+the\s+flag\b",
        r"\bcyber\s*security\b",
        r"\bkeamanan\s+siber\b",
        r"\bpentest(?:ing)?\b",
        r"\bbug\s+bounty\b",
        r"\binformation\s+security\b",
        r"\bforensik\s+digital\b",
    ],
    CompetitionCategory.DATA_AI: [
        r"\bdata\s+science\b",
        r"\bdatathon\b",
        r"\bmachine\s+learning\b",
        r"\bartificial\s+intelligence\b",
        r"\blomba\s+ai\b",
        r"\bkompetisi\s+ai\b",
        r"\bgen\s*ai\b",
        r"\bdata\s+analytics\b",
        r"\bbig\s+data\b",
        r"\bsatria\s+data\b",
    ],
    CompetitionCategory.UI_UX: [
        r"\bui\s*/?\s*ux\b",
        r"\bux\s+design\b",
        r"\bproduct\s+design\b",
        r"\bdesain\s+antarmuka\b",
        r"\bdesain\s+aplikasi\b",
        r"\bit\s+business\s+case\b",
        r"\bbusiness\s+it\s+case\b",
    ],
    CompetitionCategory.COMPETITIVE_PROG: [
        r"\bcompetitive\s+programming\b",
        r"\blomba\s+coding\b",
        r"\blomba\s+koding\b",
        r"\blomba\s+pemrograman\b",
        r"\balgoritma\b",
        r"\bicpc\b",
    ],
}

# General IT & National prestige competition triggers
PRESTIGE_IT_KEYWORDS: list[str] = [
    r"\bgemastik\b",
    r"\bcompfest\b",
    r"\barkavidia\b",
    r"\bschematics\b",
    r"\bfind\s*it\b",
    r"\bmage\s+its\b",
    r"\bhology\b",
    r"\bit\s+today\b",
    r"\btechnofest\b",
    r"\binfest\b",
    r"\bdicoding\s+challenge\b",
    r"\blomba\s+it\b",
    r"\bkompetisi\s+it\b",
    r"\blomba\s+teknologi\b",
    r"\bkompetisi\s+teknologi\b",
    r"\blomba\s+informatika\b",
    r"\bolimpiade\s+informatika\b",
]

# Competition action indicators (must indicate an actual competition/challenge/registration)
COMPETITION_ACTION_KEYWORDS: list[str] = [
    r"\blomba\b",
    r"\bkompetisi\b",
    r"\bhackathon\b",
    r"\bdatathon\b",
    r"\bchallenge\b",
    r"\bcompetition\b",
    r"\bpendaftaran\b",
    r"\bregistrasi\b",
    r"\bearly\s+bird\b",
    r"\bopen\s+registration\b",
    r"\bhadiah\b",
    r"\bprize\s+pool\b",
    r"\bgemastik\b",
    r"\bcompfest\b",
    r"\barkavidia\b",
    r"\bschematics\b",
    r"\bctf\b",
]

# High-priority registration/open call boosters
REGISTRATION_BOOST_KEYWORDS: list[str] = [
    r"\bpendaftaran\b",
    r"\bregistrasi\b",
    r"\bdibuka\b",
    r"\bmembuka\b",
    r"\bbuka\s+(?:pendaftaran|registrasi|lomba|kompetisi)\b",
    r"\bopen\s+registration\b",
    r"\bearly\s+bird\b",
    r"\bdaftar(?:\s+sekarang)?\b",
    r"\bguidebook\b",
    r"\boprec\b",
    r"\bcall\s+for\b",
    r"\bditantang\b",
    r"\bhadiah\b",
    r"\bprize\s+pool\b",
]

# Post-event / ongoing-event / completed competition news (HARD REJECT: bukan lomba yang baru buka pendaftaran)
POST_EVENT_CEREMONIAL_PATTERNS: list[str] = [
    r"\bpelepasan\s+kontingen\b",
    r"\bdoa\s+bersama\b",
    r"\braih\s+juara\b",
    r"\bmeraih\s+juara\b",
    r"\bsabet\s+juara\b",
    r"\bmenyabet\b",
    r"\bjuara\s+umum\b",
    r"\bjuara\s+(?:1|2|3|pertama|kedua|ketiga|harapan)\b",
    r"\blolos\s+final\b",
    r"\btembus\s+(?:final|semifinal)\b",
    r"\bmelaju\s+ke\s+(?:final|tingkat\s+nasional)\b",
    r"\bsukses\s+(?:di|meng)?gelar\b",
    r"\bresmi\s+ditutup\b",
    r"\btelah\s+berakhir\b",
    r"\bpenutupan\b",
    r"\bpemenang\b",
    r"\bapresiasi\b",
    r"\bantarkan\b",
    r"\bmengantarkan\b",
    r"\bkalahkan\b",
    r"\bposisi\s+strategis\b",
    r"\bdiikuti\s+\d+\b",
    r"\b\d+\s+(?:tim|mahasiswa|peserta|orang)(?:\s+startup)?\s+(?:ikuti|mengikuti)\b",
    r"\bsoroti\b",
]

# Negative noise filters (non-IT competitions or unrelated news)
NEGATIVE_NOISE_PATTERNS: list[str] = [
    r"\blomba\s+mewarnai\b",
    r"\blomba\s+menyanyi\b",
    r"\blomba\s+memasak\b",
    r"\blomba\s+mancing\b",
    r"\blomba\s+burung\b",
    r"\blomba\s+lari\b",
    r"\blomba\s+senam\b",
    r"\blomba\s+puisi\b",
    r"\blomba\s+cerpen\b",
    r"\blomba\s+menggambar\s+anak\b",
    r"\blomba\s+(?:desain\s+|kreatif\s+)?poster\b",
    r"\bposter\s+competition\b",
    r"\blomba\s+fotografi\b",
    r"\blomba\s+jurnalistik\b",
    r"\blomba\s+artikel\b",
    r"\blomba\s+esai\b",
    r"\blomba\s+(?:karya\s+tulis|lkti)\b",
    r"\blomba\s+debat\b",
    r"\blomba\s+infografis\b",
    r"\blomba\s+video\b",
    r"\breels\b",
    r"\bvideo\s+pendek\b",
    r"\bbusiness\s+model\s+canvas\b",
    r"\bcpns\b",
    r"\blowongan\s+kerja\s+admin\b",
    r"\bwebsite\s+desa\b",
    r"\bdesa\s+wisata\b",
    r"\bkelurahan\b",
    r"\b(?:antar|ingatkan)\s+opd\b",
    r"\bhadirkan\s+aplikasi\s+penilaian\b",
    r"\b201[5-9]\b",
    r"\b202[0-4]\b",
]


MONTHS_ID_EN = (
    r"(?:jan(?:uari|uary)?|feb(?:ruari|ruary)?|mar(?:et|ch)?|apr(?:il)?|"
    r"mei|may|jun(?:i|e)?|jul(?:i|y)?|agu(?:stus)?|aug(?:ust)?|"
    r"sep(?:tember)?|okt(?:ober)?|oct(?:ober)?|nov(?:ember)?|des(?:ember)?|dec(?:ember)?)"
)


def extract_registration_deadline(text: str) -> Optional[str]:
    """Extract registration deadline string from title/snippet if available."""
    if not text:
        return None

    patterns = [
        # e.g., "batas pendaftaran: 25 November 2026" / "deadline: 30 Nov 2026"
        rf"(?:batas\s+(?:akhir\s+)?pendaftaran|deadline|tutup\s+pendaftaran|closed?\s+registration|registrasi\s+(?:hingga|sampai|s\.?d\.?))\s*[:\-]?\s*(\d{{1,2}}\s+{MONTHS_ID_EN}(?:\s+\d{{4}})?)",
        # e.g., "hingga 25 November 2026" / "sampai 30 Nov 2026" / "s.d. 15 Des 2026"
        rf"(?:hingga|sampai(?:\s+dengan)?|s\.?d\.?|before|until)\s+(\d{{1,2}}\s+{MONTHS_ID_EN}(?:\s+\d{{4}})?)",
        # e.g., "1 - 25 November 2026" or "10–30 Nov 2026"
        rf"\d{{1,2}}\s*[-–—]\s*(\d{{1,2}}\s+{MONTHS_ID_EN}(?:\s+\d{{4}})?)",
        # Numeric date after deadline keyword: "deadline 25/11/2026" or "25-11-2026"
        r"(?:batas\s+pendaftaran|deadline|hingga|sampai)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    ]
    for pat in patterns:
        match = re.search(pat, text, flags=re.IGNORECASE)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()
    return None


def parse_deadline_date(
    deadline_str: Optional[str], reference_date: Optional[date] = None
) -> Optional[date]:
    """Parse an Indonesian/English deadline string into a concrete `datetime.date`."""
    if not deadline_str:
        return None

    today = reference_date or datetime.now(WIB_TZ).date()
    cleaned = deadline_str.strip().lower()

    # 1. Text month format: "13 november 2026" or "13 nov"
    m_text = re.search(
        rf"(\d{{1,2}})\s+({MONTHS_ID_EN})(?:\s+(\d{{4}}))?",
        cleaned,
        flags=re.IGNORECASE,
    )
    if m_text:
        day_num = int(m_text.group(1))
        month_raw = m_text.group(2).lower()
        month_num = MONTH_NAME_TO_NUM.get(month_raw)
        if not month_num:
            # prefix fallback
            for k, v in MONTH_NAME_TO_NUM.items():
                if month_raw.startswith(k):
                    month_num = v
                    break
        year_num = int(m_text.group(3)) if m_text.group(3) else today.year
        if month_num:
            try:
                return date(year_num, month_num, day_num)
            except ValueError:
                return None

    # 2. Numeric format: "25/11/2026" or "25-11-26"
    m_num = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", cleaned)
    if m_num:
        day_num = int(m_num.group(1))
        month_num = int(m_num.group(2))
        year_num = int(m_num.group(3))
        if year_num < 100:
            year_num += 2000
        try:
            return date(year_num, month_num, day_num)
        except ValueError:
            return None

    return None


def is_deadline_expired(
    deadline_str: Optional[str], reference_date: Optional[date] = None
) -> bool:
    """Return True if a parsed deadline date is strictly in the past (< today WIB)."""
    parsed = parse_deadline_date(deadline_str, reference_date=reference_date)
    if parsed is None:
        return False
    today = reference_date or datetime.now(WIB_TZ).date()
    return parsed < today


def evaluate_competition_relevance(
    title: str, snippet: str = "", reference_date: Optional[date] = None
) -> Tuple[bool, int, list[CompetitionCategory], list[str]]:
    """
    Evaluate whether a scraped article/post is an active/upcoming Indonesian IT competition.

    Returns:
        (is_valid, score, matched_categories, matched_keywords)
    """
    combined_text = f"{title} {snippet}".lower()

    # 1. Check hard negative filters
    for neg_pattern in NEGATIVE_NOISE_PATTERNS:
        if re.search(neg_pattern, combined_text, flags=re.IGNORECASE):
            return False, 0, [], []

    # 2. Hard-reject post-event / completed competition news
    for post_pattern in POST_EVENT_CEREMONIAL_PATTERNS:
        if re.search(post_pattern, combined_text, flags=re.IGNORECASE):
            return False, 0, [], []

    # 3. Hard-reject if extracted registration deadline has already passed!
    extracted_deadline = extract_registration_deadline(f"{title} {snippet}")
    if is_deadline_expired(extracted_deadline, reference_date=reference_date):
        return False, 0, [], []

    matched_categories: list[CompetitionCategory] = []
    matched_keywords: list[str] = []
    score = 0

    # 2. Match specific IT competition categories
    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, combined_text, flags=re.IGNORECASE)
            if match:
                if category not in matched_categories:
                    matched_categories.append(category)
                kw = match.group(0).strip().lower()
                if kw not in matched_keywords:
                    matched_keywords.append(kw)
                score += 15

    # 3. Match prestige event & general IT competition keywords
    for pattern in PRESTIGE_IT_KEYWORDS:
        match = re.search(pattern, combined_text, flags=re.IGNORECASE)
        if match:
            kw = match.group(0).strip().lower()
            if kw not in matched_keywords:
                matched_keywords.append(kw)
            score += 20

    # 4. Verify competition action context
    has_competition_intent = False
    for pattern in COMPETITION_ACTION_KEYWORDS:
        if re.search(pattern, combined_text, flags=re.IGNORECASE):
            has_competition_intent = True
            score += 5
            break

    # Bonus if title itself explicitly mentions competition/hackathon
    if re.search(
        r"\b(lomba|kompetisi|hackathon|datathon|ctf|challenge|gemastik|compfest|arkavidia|schematics)\b",
        title.lower(),
    ):
        score += 15

    # Boost if registration/open call keywords are present
    has_registration_intent = False
    for pattern in REGISTRATION_BOOST_KEYWORDS:
        match = re.search(pattern, combined_text, flags=re.IGNORECASE)
        if match:
            has_registration_intent = True
            score += 20
            kw = match.group(0).strip().lower()
            if kw not in matched_keywords:
                matched_keywords.append(kw)

    if not matched_categories and score >= 20:
        matched_categories.append(CompetitionCategory.GENERAL_IT)

    is_valid = (
        has_competition_intent
        and has_registration_intent
        and (len(matched_categories) > 0)
        and (score >= 35)
    )
    return is_valid, score, matched_categories, matched_keywords
