# D:\alfa\Documents\Antigravity\lomba-it-radar\tests\test_radar.py
from __future__ import annotations

from pathlib import Path

from src.classifier import evaluate_competition_relevance
from src.models import CompetitionCategory, CompetitionItem, canonicalize_url
from src.notifier import format_telegram_message
from src.storage import RadarStorage


def test_canonicalize_url_strips_utm() -> None:
    raw = "https://compfest.id/competition/ctf?utm_source=instagram&utm_medium=story&id=42#top"
    canon = canonicalize_url(raw)
    assert canon == "https://compfest.id/competition/ctf?id=42"


def test_classifier_accepts_valid_it_competitions() -> None:
    cases = [
        (
            "Pendaftaran Hackathon Nasional Arkavidia 9.0 ITB Resmi Dibuka!",
            "Ikuti kompetisi software development, datathon, dan capture the flag tingkat nasional.",
            CompetitionCategory.HACKATHON,
        ),
        (
            "Lomba Cyber Security & Capture The Flag (CTF) Mahasiswa Indonesia",
            "Hadiah jutaan rupiah untuk tim keamanan siber terbaik.",
            CompetitionCategory.CYBERSECURITY,
        ),
        (
            "Kompetisi UI/UX Design & IT Business Case Find IT UGM",
            "Pendaftaran early bird lomba desain aplikasi nasional.",
            CompetitionCategory.UI_UX,
        ),
    ]
    for title, snippet, expected_cat in cases:
        is_valid, score, cats, _ = evaluate_competition_relevance(title, snippet)
        assert is_valid is True
        assert score >= 25
        assert expected_cat in cats


def test_classifier_rejects_non_it_noise() -> None:
    noise_cases = [
        ("Lomba Mewarnai dan Menggambar Anak Tingkat Nasional", "Hadiah piala bergilir"),
        ("Lomba Mancing Ikan Mas Akhir Pekan", "Pendaftaran terbuka untuk umum"),
        ("Lowongan Kerja Admin Gudang Jakarta", "Syarat minimal SMA/SMK"),
    ]
    for title, snippet in noise_cases:
        is_valid, _, _, _ = evaluate_competition_relevance(title, snippet)
        assert is_valid is False


def test_sqlite_deduplication(tmp_path: Path) -> None:
    db_file = tmp_path / "test_history.db"
    storage = RadarStorage(db_file)

    item1 = CompetitionItem(
        title="Pendaftaran Lomba Hackathon Nasional GEMASTIK Mahasiswa Indonesia",
        url="https://pusatprestasinasional.kemdikbud.go.id/gemastik?utm_source=ig",
        source_name="Puspresnas",
        categories=[CompetitionCategory.HACKATHON],
        relevance_score=50,
    )
    # Same competition with different tracking param
    item2 = CompetitionItem(
        title="Pendaftaran Lomba Hackathon Nasional GEMASTIK Mahasiswa Indonesia!",
        url="https://pusatprestasinasional.kemdikbud.go.id/gemastik?fbclid=12345",
        source_name="Portal Kampus",
        categories=[CompetitionCategory.HACKATHON],
        relevance_score=45,
    )

    assert storage.is_seen(item1) is False
    storage.save_item(item1, notified=True)
    assert storage.is_seen(item1) is True
    # Deduplicated via title_fingerprint and canonical URL fingerprint
    assert storage.is_seen(item2) is True
    assert storage.count_total() == 1


def test_telegram_html_formatting() -> None:
    item = CompetitionItem(
        title="Lomba AI & Data Science <Nasional> & Hackathon",
        url="https://dicoding.com/challenges/123",
        source_name="Dicoding",
        categories=[CompetitionCategory.DATA_AI, CompetitionCategory.HACKATHON],
        matched_keywords=["hackathon", "data science"],
    )
    msg = format_telegram_message(item)
    assert "<b>[RADAR LOMBA IT NASIONAL BARU]</b>" in msg
    assert "&lt;Nasional&gt; &amp; Hackathon" in msg
    assert "https://dicoding.com/challenges/123" in msg
