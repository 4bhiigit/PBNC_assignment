import uuid

from app.pipeline.answer_key.detect import (
    detect_document_role,
    is_answer_key_heading,
    is_answer_key_page,
)
from app.pipeline.answer_key.match import match_question_answers
from app.pipeline.answer_key.normalize import (
    map_digits_to_letters_if_applicable,
    normalize_answer_string,
    normalize_answer_token,
)
from app.pipeline.answer_key.parse import (
    merge_llm_answer_key_entries,
    parse_answer_key_text,
)


def test_answer_key_detection() -> None:
    assert is_answer_key_heading("Answer Key")
    assert is_answer_key_heading("ANSWERS")
    assert is_answer_key_heading("Solutions")
    assert is_answer_key_heading("उत्तर कुंजी")
    assert not is_answer_key_heading("Question 1: What is kinetic energy?")

    assert is_answer_key_page("answer_key", "Any text")
    assert is_answer_key_page("questions", "Answer Key\n1. A\n2. B")
    dense_text = "1-A 2-B 3-C 4-D 5-A 6-B 7-C 8-D"
    assert is_answer_key_page(None, dense_text)
    assert not is_answer_key_page(None, "This is a regular question text without answers.")


def test_detect_document_role() -> None:
    assert detect_document_role(["questions", "questions"]) == "question_paper"
    assert detect_document_role(["answer_key"]) == "answer_key"
    assert detect_document_role(["questions", "answer_key"]) == "combined"
    assert detect_document_role([]) == "unknown"


def test_normalize_answer_string() -> None:
    assert normalize_answer_token("(a)") == "A"
    assert normalize_answer_token("[B]") == "B"

    assert normalize_answer_string("Ans: (b)") == ["B"]
    assert normalize_answer_string("A, C") == ["A", "C"]
    assert normalize_answer_string("A & D") == ["A", "D"]
    assert normalize_answer_string("AC") == ["A", "C"]
    assert normalize_answer_string("1") == ["1"]
    assert normalize_answer_string("12.5") == ["12.5"]


def test_map_digits_to_letters_if_applicable() -> None:
    letter_options = [{"label": "A"}, {"label": "B"}, {"label": "C"}, {"label": "D"}]
    mapped, was_mapped = map_digits_to_letters_if_applicable(["2"], letter_options)
    assert was_mapped is True
    assert mapped == ["B"]

    # Numbered options should not be mapped
    number_options = [{"label": "1"}, {"label": "2"}, {"label": "3"}]
    not_mapped, was_mapped = map_digits_to_letters_if_applicable(["2"], number_options)
    assert was_mapped is False
    assert not_mapped == ["2"]


def test_parse_single_lines_and_ranges() -> None:
    text = """
    Section A - Physics
    1. A
    2 - (b)
    Q3: C
    4-6: D
    """
    entries = parse_answer_key_text(text, page_no=1)
    assert len(entries) == 6
    assert entries[0].number_norm == "1"
    assert entries[0].answer_value == ["A"]
    assert entries[0].section == "Section A - Physics"
    assert entries[1].number_norm == "2"
    assert entries[1].answer_value == ["B"]
    assert entries[2].number_norm == "3"
    assert entries[2].answer_value == ["C"]
    # Range 4-6 expanded
    assert entries[3].number_norm == "4"
    assert entries[3].answer_value == ["D"]
    assert entries[4].number_norm == "5"
    assert entries[4].answer_value == ["D"]
    assert entries[5].number_norm == "6"
    assert entries[5].answer_value == ["D"]


def test_parse_dense_pairs_and_table_rows() -> None:
    dense_text = """
    1-A 2-B 3-C 4-D
    5 A 6 B 7 C 8 D
    """
    entries = parse_answer_key_text(dense_text, page_no=2)
    nums = [e.number_norm for e in entries]
    assert nums == ["1", "2", "3", "4", "5", "6", "7", "8"]
    assert entries[0].answer_value == ["A"]
    assert entries[3].answer_value == ["D"]


def test_merge_llm_answer_key_entries() -> None:
    det_entries = parse_answer_key_text("1. A", page_no=1)
    llm_entries = [
        {"number_raw": "1", "answer_raw": "Z"},  # Duplicate: deterministic should win
        {"number_raw": "2", "answer_raw": "B", "section": "Math"},
    ]
    merged = merge_llm_answer_key_entries(det_entries, llm_entries, page_no=1)
    assert len(merged) == 2
    assert merged[0].number_norm == "1"
    assert merged[0].answer_value == ["A"]
    assert merged[1].number_norm == "2"
    assert merged[1].answer_value == ["B"]
    assert merged[1].parse_confidence == 0.90


def test_matching_precedence_and_statuses() -> None:
    q1_id = uuid.uuid4()
    q2_id = uuid.uuid4()
    q3_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    linked_doc_id = uuid.uuid4()

    questions = [
        {
            "id": q1_id,
            "number_norm": "1",
            "section": "Physics",
            "options": [{"label": "A"}, {"label": "B"}, {"label": "C"}],
            "inline_answer_raw": "A",  # Overridden by linked key
        },
        {
            "id": q2_id,
            "number_norm": "2",
            "section": "Physics",
            "options": [{"label": "A"}, {"label": "B"}],
            "inline_answer_raw": "B",  # Uses same-doc key
        },
        {
            "id": q3_id,
            "number_norm": "3",
            "section": "Physics",
            "options": [{"label": "A"}, {"label": "B"}],
            "inline_answer_raw": "A",  # Fallback to inline
        },
    ]

    same_doc_entries = [
        {
            "id": uuid.uuid4(),
            "document_id": doc_id,
            "page_no": 1,
            "section": "Physics",
            "number_norm": "1",
            "answer_raw": "C",
            "answer_value": ["C"],
            "parse_confidence": 1.0,
        },
        {
            "id": uuid.uuid4(),
            "document_id": doc_id,
            "page_no": 1,
            "section": "Physics",
            "number_norm": "2",
            "answer_raw": "A",
            "answer_value": ["A"],
            "parse_confidence": 1.0,
        },
    ]

    linked_doc_entries = [
        {
            "id": uuid.uuid4(),
            "document_id": linked_doc_id,
            "page_no": 5,
            "section": "Physics",
            "number_norm": "1",
            "answer_raw": "B",
            "answer_value": ["B"],
            "parse_confidence": 1.0,
        }
    ]

    results, entry_statuses = match_question_answers(
        questions=questions,
        document_id=doc_id,
        same_doc_entries=same_doc_entries,
        linked_doc_entries=linked_doc_entries,
    )

    res_map = {r.question_id: r for r in results}

    # Q1: Linked doc takes precedence over same doc and inline -> Answer B
    assert res_map[q1_id].answer_status == "matched"
    assert res_map[q1_id].answer_value == ["B"]
    assert res_map[q1_id].answer_source["kind"] == "linked_document"

    # Q2: Same doc key takes precedence over inline -> Answer A
    assert res_map[q2_id].answer_status == "matched"
    assert res_map[q2_id].answer_value == ["A"]
    assert res_map[q2_id].answer_source["kind"] == "answer_key"

    # Q3: No key entries -> fallback to inline -> Answer A
    assert res_map[q3_id].answer_status == "matched"
    assert res_map[q3_id].answer_value == ["A"]
    assert res_map[q3_id].answer_source["kind"] == "inline"


def test_matching_edge_cases() -> None:
    doc_id = uuid.uuid4()
    q_ambig1 = uuid.uuid4()
    q_ambig2 = uuid.uuid4()
    q_out_of_range = uuid.uuid4()
    q_conflict = uuid.uuid4()

    questions = [
        # Duplicate number 1 across sections
        {"id": q_ambig1, "number_norm": "1", "section": "Physics", "options": [{"label": "A"}]},
        {"id": q_ambig2, "number_norm": "1", "section": "Chemistry", "options": [{"label": "A"}]},
        # Out of range option
        {
            "id": q_out_of_range,
            "number_norm": "2",
            "section": None,
            "options": [{"label": "A"}, {"label": "B"}],
        },
        # Conflict candidate
        {
            "id": q_conflict,
            "number_norm": "3",
            "section": None,
            "options": [{"label": "A"}, {"label": "B"}],
        },
    ]

    same_doc_entries = [
        # Key without section for duplicate number -> ambiguous
        {
            "id": uuid.uuid4(),
            "document_id": doc_id,
            "page_no": 1,
            "section": None,
            "number_norm": "1",
            "answer_raw": "A",
            "answer_value": ["A"],
        },
        # Key with option D for question with only A and B -> out of range
        {
            "id": uuid.uuid4(),
            "document_id": doc_id,
            "page_no": 1,
            "section": None,
            "number_norm": "2",
            "answer_raw": "D",
            "answer_value": ["D"],
        },
        # Contradictory keys for question 3
        {
            "id": uuid.uuid4(),
            "document_id": doc_id,
            "page_no": 1,
            "section": None,
            "number_norm": "3",
            "answer_raw": "A",
            "answer_value": ["A"],
        },
        {
            "id": uuid.uuid4(),
            "document_id": doc_id,
            "page_no": 1,
            "section": None,
            "number_norm": "3",
            "answer_raw": "B",
            "answer_value": ["B"],
        },
    ]

    results, _ = match_question_answers(
        questions=questions,
        document_id=doc_id,
        same_doc_entries=same_doc_entries,
    )

    res_map = {r.question_id: r for r in results}

    assert res_map[q_ambig1].answer_status == "ambiguous"
    assert "ANSWER_AMBIGUOUS" in res_map[q_ambig1].flags_to_add

    assert res_map[q_out_of_range].answer_status == "invalid"
    assert "ANSWER_OUT_OF_RANGE" in res_map[q_out_of_range].flags_to_add

    assert res_map[q_conflict].answer_status == "conflict"
    assert "ANSWER_CONFLICT" in res_map[q_conflict].flags_to_add
