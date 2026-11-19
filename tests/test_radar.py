# D:\alfa\Documents\Antigravity\lomba-it-radar\tests\test_radar.py
from __future__ import annotations

from datetime import date
from pathlib import Path

from src.classifier import (
    evaluate_competition_relevance,
    extract_registration_deadline,
    is_closed_event_text,
    is_deadline_expired,
    is_deadline_valid_and_open,
    parse_deadline_date,
)
from src.models import (
    CompetitionCategory,
    CompetitionItem,
    are_same_competition,
    canonicalize_url,
)
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
        ("Lomba Menulis Surat untuk Ibu Pertiwi 2026 Gratis, Hadiah Rp237 Juta", "Deadline: 12 Desember 2026 literasi dan kebudayaan"),
        ("Lomba Kaligrafi Arab POSCA 2027 Gratis, Hadiah Uang Tunai Rp5 Juta", "Deadline: 31 Januari 2027 seni kaligrafi dan desain dekoratif"),
        ("ITB Insight 2026 Digelar 28 November di Kampus Ganesha, Registrasi Gratis untuk Umum", "Acara pengenalan kampus ITB"),
        ("TI Usakti sukses gelar Kompetisi Rekayasa Kualitas Tingkat Nasional IX", "Teknik Industri Usakti"),
        ("Lomba Desain Poster Hari AIDS Sedunia 2026 Gratis untuk Umum", "Hadiah jutaan rupiah"),
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


def test_classifier_rejects_post_event_completed_news() -> None:
    post_event_cases = [
        ("Mahasiswa UNAIR Lolos Final GEMASTIK XIX", "Inovasi pemulihan adiksi"),
        ("Tim FILKOM Raih Juara Pertama Kompetisi UI/UX Nasional", "Berhasil mengalahkan puluhan tim"),
        ("Pelepasan Kontingen PIMNAS dan Gemastik 2026 oleh Rektor", "Doa bersama sebelum berangkat"),
        ("TI Usakti sukses gelar Kompetisi Rekayasa Kualitas Tingkat Nasional IX", "Kegiatan berlangsung meriah"),
        ("30 Tim Startup Ikuti Hackathon MAJU ON 2026 27 di Jakarta", "Acara dibuka untuk para finalis"),
        ("Diikuti 98 Mahasiswa, BEM FIKOM Umuslim Gelar Lomba Website dan Blogspot", "Berlangsung di aula"),
        ("Lomba Reels Competition Nasional 2026 untuk Mahasiswa Kesehatan, Hadiah Uang Pembinaan", "Buat video pendek"),
        ("Lomba Business Model Canvas NBMC 1.0 2026-2027, Hadiah dan Beasiswa UMY", "Kompetisi BMC"),
    ]
    for title, snippet in post_event_cases:
        is_valid, _, _, _ = evaluate_competition_relevance(title, snippet)
        assert is_valid is False


def test_extract_registration_deadline() -> None:
    text1 = "Pendaftaran Hackathon Nasional dibuka! Batas pendaftaran: 25 November 2026."
    assert extract_registration_deadline(text1) == "25 November 2026"

    text2 = "Open Registration UI/UX Competition hingga 10 Desember 2026, daftar sekarang!"
    assert extract_registration_deadline(text2) == "10 Desember 2026"

    text3 = "Kompetisi Coding Nasional tanpa info tanggal"
    assert extract_registration_deadline(text3) is None

    # Cross-month range on infolomba.id
    text4 = "Online | 13 Okt - 24 Nov 2026 | Diselenggarakan oleh BNCC"
    assert extract_registration_deadline(text4) == "24 Nov 2026"

    # Reverse timeline format on infolomba.id detail page
    text5 = "TIMELINE PENTING: • 20 November 2026: Penutupan Pendaftaran • 29 November 2026: Pengumpulan"
    assert extract_registration_deadline(text5) == "20 November 2026"

    # Extended registration announcement
    text6 = "Kompetisi Budaya Go! 2026 diperpanjang hingga 21 November 2026"
    assert extract_registration_deadline(text6) == "21 November 2026"


def test_mandatory_future_deadline_and_closed_event_gate(tmp_path: Path) -> None:
    ref_today = date(2026, 11, 19)
    # Undated ceremonial news MUST fail is_deadline_valid_and_open
    assert is_deadline_valid_and_open(None, reference_date=ref_today) is False
    # Expired GEMASTIK Aug 17 deadline MUST fail
    assert is_deadline_valid_and_open("17 Agustus 2026", reference_date=ref_today) is False
    # Active future deadlines MUST pass
    assert is_deadline_valid_and_open("20 November 2026", reference_date=ref_today) is True
    assert is_deadline_valid_and_open("26 November 2026", reference_date=ref_today) is True
    assert is_deadline_valid_and_open("6 Februari 2027", reference_date=ref_today) is True

    # Closed event detection
    assert is_closed_event_text("Pendaftaran telah ditutup pada 17 Agustus 2026 dan babak final berlangsung di BINUS") is True
    assert is_closed_event_text("UMS Hackathon seleksi 15 tim terbaik") is True
    assert is_closed_event_text("Pendaftaran Hackathon Nasional dibuka hingga 26 November 2026") is False

    # Storage active items gate excludes undated and expired rows
    st = RadarStorage(tmp_path / "active_gate.db")
    st.save_item(
        CompetitionItem(
            title="GEMASTIK XIX 2026 Buka 11 Lomba",
            url="https://example.com/gemastik",
            source_name="News",
            registration_deadline=None,
        )
    )
    st.save_item(
        CompetitionItem(
            title="Hackathon Lama 2026",
            url="https://example.com/old",
            source_name="Portal",
            registration_deadline="10 Oktober 2026",
        )
    )
    st.save_item(
        CompetitionItem(
            title="SpaceXAI Hackathon Indonesia",
            url="https://indonesiahackathons.com/events/spacexai-hackathon-indonesia",
            source_name="IndonesiaHackathons.com",
            registration_deadline="6 Februari 2027",
        )
    )
    active = st.get_active_items(limit=10)
    assert len(active) == 1
    assert active[0].title == "SpaceXAI Hackathon Indonesia"


def test_expired_deadline_is_hard_rejected() -> None:
    ref_today = date(2026, 11, 15)
    assert parse_deadline_date("13 November 2026", reference_date=ref_today) == date(2026, 11, 13)
    assert is_deadline_expired("13 November 2026", reference_date=ref_today) is True
    assert is_deadline_expired("15 November 2026", reference_date=ref_today) is False
    assert is_deadline_expired("28 November 2026", reference_date=ref_today) is False

    # Exact case reported by user: deadline 13 November 2026 when today is 15 November 2026
    is_valid_past, _, _, _ = evaluate_competition_relevance(
        "Kementerian Desa Buka Lomba Website Desa Nasional 2027, Pendaftaran hingga 13 November 2026",
        "Pendaftaran hingga 13 November 2026",
        reference_date=ref_today,
    )
    assert is_valid_past is False

    # Also test a real IT hackathon with an expired deadline
    is_valid_expired_it, _, _, _ = evaluate_competition_relevance(
        "Pendaftaran Hackathon Nasional ITB Dibuka hingga 10 November 2026",
        "Segera daftar hackathon software development nasional.",
        reference_date=ref_today,
    )
    assert is_valid_expired_it is False

    # And a real IT hackathon with a future deadline
    is_valid_future_it, _, _, _ = evaluate_competition_relevance(
        "Pendaftaran Hackathon Nasional ITB Dibuka hingga 28 November 2026",
        "Segera daftar hackathon software development nasional.",
        reference_date=ref_today,
    )
    assert is_valid_future_it is True


def test_telegram_html_formatting() -> None:
    item = CompetitionItem(
        title="Lomba AI & Data Science <Nasional> & Hackathon",
        url="https://dicoding.com/challenges/123",
        source_name="Dicoding",
        categories=[CompetitionCategory.DATA_AI, CompetitionCategory.HACKATHON],
        registration_deadline="30 November 2026",
        matched_keywords=["hackathon", "data science"],
    )
    msg = format_telegram_message(item)
    assert "<b>[LOMBA IT NASIONAL — BUKA PENDAFTARAN]</b>" in msg
    assert "30 November 2026" in msg
    assert "&lt;Nasional&gt; &amp; Hackathon" in msg
    assert "https://dicoding.com/challenges/123" in msg


def test_semantic_event_deduplication_same_competition() -> None:
    # 1. Exact duplicate GEMASTIK variants from user screenshot
    assert are_same_competition(
        "GEMASTIK XIX 2026 Buka 11 Lomba untuk Talenta Digital",
        "GEMASTIK 2026 Digelar, Incar Talenta Digital di 11 Cabang Lomba",
    ) is True
    assert are_same_competition(
        "GEMASTIK XIX 2026 Buka 11 Lomba untuk Talenta Digital",
        "GEMASTIK XIX 2026 Resmi Dibuka di BINUS University Alam Sutera, Perlombakan 11 Cabang Inovasi - Akurat Jakarta",
    ) is True

    # 2. Exact duplicate UMS Health Innovation Hackathon variants from user screenshot
    assert are_same_competition(
        "UMSHealth Innovation Hackathon 2026 Dibuka, Tantang Peserta Ciptakan Solusi Halaman all - Kompasiana.com",
        "Health Innovation Hackathon 2026 UMS Dibuka, Gaet Inovator Lintas Ilmu Berhadiah Ratusan Juta Rupiah - PWM Jateng",
    ) is True
    assert are_same_competition(
        "Health Innovation Hackathon 2026 UMS Dibuka, Gaet Inovator Lintas Ilmu Berhadiah Ratusan Juta Rupiah - PWM Jateng",
        "Pendaftaran UMS Health Innovation Hackathon 2026 Resmi Dibuka, Peserta Ditantang Hadirkan Solusi Kesehatan - PWM Jateng",
    ) is True

    # 3. Distinct competitions MUST NOT be merged
    assert are_same_competition(
        "BRI FinTech Hackathon 2026 Dibuka",
        "Mandiri FinTech Hackathon 2026 Dibuka",
    ) is False
    assert are_same_competition(
        "Shopee Code League 2026 Dibuka",
        "BRI Code League 2026 Dibuka",
    ) is False
    assert are_same_competition(
        "GEMASTIK XIX 2026 Buka 11 Lomba",
        "GEMASTIK XX 2027 Buka 11 Lomba",
    ) is False


def test_storage_deduplicates_cross_media_articles(tmp_path: Path) -> None:
    storage = RadarStorage(tmp_path / "dedup_events.db")

    gemastik_1 = CompetitionItem(
        title="GEMASTIK XIX 2026 Buka 11 Lomba untuk Talenta Digital",
        url="https://journalarta.com/news/gemastik",
        source_name="Bing Web Radar ID",
        relevance_score=80,
    )
    gemastik_2 = CompetitionItem(
        title="GEMASTIK 2026 Digelar, Incar Talenta Digital di 11 Cabang Lomba",
        url="https://inet.detik.com/gemastik-2026",
        source_name="Google Radar (detikInet)",
        relevance_score=60,
    )
    ums_1 = CompetitionItem(
        title="Pendaftaran UMS Health Innovation Hackathon 2026 Resmi Dibuka - News UMS",
        url="https://news.ums.ac.id/hackathon",
        source_name="Google Radar (News UMS)",
        relevance_score=75,
    )
    ums_2 = CompetitionItem(
        title="UMSHealth Innovation Hackathon 2026 Dibuka, Tantang Peserta Ciptakan Solusi - Kompasiana.com",
        url="https://kompasiana.com/umshealth",
        source_name="Google Radar (Kompasiana.com)",
        relevance_score=55,
    )

    assert storage.is_seen(gemastik_1) is False
    storage.save_item(gemastik_1, notified=True)
    # Different URL & different headline for the SAME event MUST be seen!
    assert storage.is_seen(gemastik_2) is True

    assert storage.is_seen(ums_1) is False
    storage.save_item(ums_1, notified=True)
    assert storage.is_seen(ums_2) is True

    # Simulate legacy duplicate rows already in DB and verify cleanup collapses them
    storage.save_item(gemastik_2, notified=True)
    storage.save_item(ums_2, notified=True)
    assert storage.count_total() == 4
    removed = storage.deduplicate_existing_records()
    assert removed == 2
    assert storage.count_total() == 2
