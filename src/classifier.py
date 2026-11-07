# D:\alfa\Documents\Antigravity\lomba-it-radar\src\classifier.py
from __future__ import annotations

import re
from typing import Tuple

from src.models import CompetitionCategory

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
    r"\bopen\s+registration\b",
    r"\bearly\s+bird\b",
    r"\bdaftar\s+sekarang\b",
    r"\bguidebook\b",
    r"\boprec\b",
    r"\bcall\s+for\b",
    r"\bditantang\b",
    r"\bikuti\b",
    r"\bhadiah\b",
    r"\bprize\s+pool\b",
]

# Post-event ceremonial news penalty (unless registration is also mentioned)
POST_EVENT_CEREMONIAL_PATTERNS: list[str] = [
    r"\bpelepasan\s+kontingen\b",
    r"\bdoa\s+bersama\b",
    r"\braih\s+juara\b",
    r"\bsabet\s+juara\b",
    r"\bjuara\s+umum\b",
    r"\btembus\s+semifinal\b",
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
    r"\bcpns\b",
    r"\blowongan\s+kerja\s+admin\b",
    r"\b201[5-9]\b",
    r"\b202[0-4]\b",
]


def evaluate_competition_relevance(
    title: str, snippet: str = ""
) -> Tuple[bool, int, list[CompetitionCategory], list[str]]:
    """
    Evaluate whether a scraped article/post is a valid Indonesian IT competition.

    Returns:
        (is_valid, score, matched_categories, matched_keywords)
    """
    combined_text = f"{title} {snippet}".lower()

    # 1. Check hard negative filters
    for neg_pattern in NEGATIVE_NOISE_PATTERNS:
        if re.search(neg_pattern, combined_text, flags=re.IGNORECASE):
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
    for pattern in REGISTRATION_BOOST_KEYWORDS:
        match = re.search(pattern, combined_text, flags=re.IGNORECASE)
        if match:
            score += 20
            kw = match.group(0).strip().lower()
            if kw not in matched_keywords:
                matched_keywords.append(kw)

    # Penalize ceremonial post-event news (e.g., "raih juara", "pelepasan kontingen")
    for pattern in POST_EVENT_CEREMONIAL_PATTERNS:
        if re.search(pattern, combined_text, flags=re.IGNORECASE):
            score -= 18

    if not matched_categories and score >= 20:
        matched_categories.append(CompetitionCategory.GENERAL_IT)

    is_valid = has_competition_intent and (len(matched_categories) > 0) and (score >= 25)
    return is_valid, score, matched_categories, matched_keywords
