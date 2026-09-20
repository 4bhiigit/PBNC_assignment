import json

import fitz

from scripts.generate_samples import EXPECTED_DIR, INPUT_DIR, INVALID_DIR, generate_all_samples


def test_generate_samples_creates_all_expected_files() -> None:
    generate_all_samples()

    expected_inputs = [
        "digital_paper_mcq.pdf",
        "digital_paper_spanning.pdf",
        "paper_with_key_at_end.pdf",
        "paper_with_key_at_start.pdf",
        "answer_key_separate.pdf",
        "scanned_clean.pdf",
        "scanned_lowquality.pdf",
        "scan_page.png",
        "scan_page.jpg",
        "low_confidence.pdf",
    ]

    for fname in expected_inputs:
        fpath = INPUT_DIR / fname
        assert fpath.exists(), f"Expected input file {fname} not found"
        assert fpath.stat().st_size > 0, f"File {fname} is empty"


def test_digital_paper_mcq_structure() -> None:
    doc = fitz.open(INPUT_DIR / "digital_paper_mcq.pdf")
    assert doc.page_count == 4
    doc.close()

    expected_path = EXPECTED_DIR / "digital_paper_mcq.json"
    assert expected_path.exists()
    data = json.loads(expected_path.read_text(encoding="utf-8"))
    assert data["questions_count"] == 20
    assert len(data["questions"]) == 20


def test_digital_paper_spanning_structure() -> None:
    doc = fitz.open(INPUT_DIR / "digital_paper_spanning.pdf")
    assert doc.page_count == 4

    # Verify that Question 2 text is present on Page 1 and continuation on Page 2
    p1_text = doc[0].get_text()
    p2_text = doc[1].get_text()
    doc.close()

    assert "2. A block of mass 10 kg" in p1_text
    assert "(C) 3.50 seconds" in p2_text  # Continuation option on Page 2

    expected_path = EXPECTED_DIR / "digital_paper_spanning.json"
    assert expected_path.exists()
    data = json.loads(expected_path.read_text(encoding="utf-8"))
    assert data["questions_count"] == 5
    assert data["questions"][1]["source_pages"] == [1, 2]
    assert data["questions"][3]["source_pages"] == [2, 3, 4]


def test_invalid_files_created() -> None:
    expected_invalids = [
        "fake.pdf",
        "truncated.pdf",
        "notes.txt",
        "encrypted.pdf",
        "bomb.png",
    ]
    for fname in expected_invalids:
        fpath = INVALID_DIR / fname
        assert fpath.exists(), f"Expected invalid file {fname} not found"
        assert fpath.stat().st_size > 0
