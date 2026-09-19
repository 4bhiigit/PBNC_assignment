import uuid

from app.pipeline.extractors.rules import RulesExtractor
from app.pipeline.extractors.schemas import PageContext


def test_rules_extractor_multi_question_mcq() -> None:
    text = """
    Section A - Physics

    1. What is the unit of electric current?
    (A) Volt
    (B) Ampere
    (C) Ohm
    (D) Watt

    2. Newton's third law states that every action has:
    (a) No reaction
    (b) Equal and opposite reaction
    (c) Unequal reaction
    (d) Unpredictable reaction
    Ans: (b)
    """
    ctx = PageContext(
        document_id=uuid.uuid4(),
        page_no=1,
        total_pages=1,
        text=text,
        text_source="text_layer",
    )
    extractor = RulesExtractor()
    extraction = extractor.extract_page(ctx)

    assert extraction.page_type == "questions"
    assert extraction.section_heading is not None
    assert "Physics" in extraction.section_heading
    assert len(extraction.items) == 2

    # Item 1
    q1 = extraction.items[0]
    assert q1.number_norm == "1"
    assert "unit of electric current" in q1.text
    assert len(q1.options) == 4
    assert [o.label for o in q1.options] == ["A", "B", "C", "D"]
    assert q1.question_type == "mcq_single"

    # Item 2
    q2 = extraction.items[1]
    assert q2.number_norm == "2"
    assert "third law" in q2.text
    assert len(q2.options) == 4
    assert q2.inline_answer_raw == "b"


def test_rules_extractor_inline_options_and_types() -> None:
    text = """
    Q1. Sound waves in air are:
    (A) Transverse  (B) Longitudinal  (C) Electromagnetic  (D) None

    Q2. Light travels in a straight line.
    (1) True  (2) False

    Q3. Fill in the blank: The nucleus of an atom contains ___ and neutrons.
    """
    ctx = PageContext(
        document_id=uuid.uuid4(),
        page_no=1,
        total_pages=1,
        text=text,
        text_source="text_layer",
    )
    extractor = RulesExtractor()
    extraction = extractor.extract_page(ctx)

    assert len(extraction.items) == 3
    assert extraction.items[0].question_type == "mcq_single"
    assert len(extraction.items[0].options) == 4

    assert extraction.items[1].question_type == "true_false"
    assert len(extraction.items[1].options) == 2

    assert extraction.items[2].question_type == "fill_blank"
    assert len(extraction.items[2].options) == 0


def test_rules_extractor_answer_key_page() -> None:
    text = """
    Answer Key
    1 - A
    2 - C
    3 - B
    4 - D
    5 - A
    """
    ctx = PageContext(
        document_id=uuid.uuid4(),
        page_no=2,
        total_pages=2,
        text=text,
        text_source="text_layer",
    )
    extractor = RulesExtractor()
    extraction = extractor.extract_page(ctx)

    assert extraction.page_type == "answer_key"
    assert len(extraction.answer_key_entries) == 5
    assert extraction.answer_key_entries[0].number_raw == "1"
    assert extraction.answer_key_entries[0].answer_raw == "A"
    assert extraction.answer_key_entries[1].answer_raw == "C"
