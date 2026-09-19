from app.pipeline.extractors.schemas import ExtractedItem, ExtractedOption, PageExtraction
from app.pipeline.stitcher import (
    PageExtractionInput,
    join_stitched_text,
    merge_extracted_options,
    stitch_document_extractions,
)


def test_join_stitched_text_dehyphenation() -> None:
    text_a = "The central pro-"
    text_b = "cessing unit controls execution."
    joined = join_stitched_text(text_a, text_b)
    assert joined == "The central processing unit controls execution."


def test_join_stitched_text_standard() -> None:
    text_a = "Which of the following is correct?"
    text_b = "Consider standard conditions."
    joined = join_stitched_text(text_a, text_b)
    assert joined == "Which of the following is correct? Consider standard conditions."


def test_merge_extracted_options() -> None:
    opts_a = [
        ExtractedOption(label="A", raw_label="(a)", text="Option A"),
        ExtractedOption(label="B", raw_label="(b)", text="Option B"),
    ]
    opts_b = [
        ExtractedOption(label="C", raw_label="(c)", text="Option C"),
        ExtractedOption(label="D", raw_label="(d)", text="Option D"),
    ]
    merged = merge_extracted_options(opts_a, opts_b)
    assert len(merged) == 4
    assert [o.label for o in merged] == ["A", "B", "C", "D"]


def test_two_page_explicit_stitch() -> None:
    p1 = PageExtractionInput(
        page_no=1,
        extraction=PageExtraction(
            page_type="questions",
            items=[
                ExtractedItem(
                    number_raw="1.",
                    number_norm="1",
                    text="What is the speed of light in a vacuum under standard",
                    options=[
                        ExtractedOption(label="A", raw_label="(a)", text="3 x 10^8 m/s"),
                        ExtractedOption(label="B", raw_label="(b)", text="2 x 10^8 m/s"),
                    ],
                    question_type="mcq_single",
                    continues_on_next_page=True,
                )
            ],
        ),
    )
    p2 = PageExtractionInput(
        page_no=2,
        extraction=PageExtraction(
            page_type="questions",
            items=[
                ExtractedItem(
                    text="conditions?",
                    options=[
                        ExtractedOption(label="C", raw_label="(c)", text="1 x 10^8 m/s"),
                        ExtractedOption(label="D", raw_label="(d)", text="None of these"),
                    ],
                    question_type="mcq_single",
                    starts_on_previous_page=True,
                )
            ],
        ),
    )

    questions = stitch_document_extractions([p1, p2])
    assert len(questions) == 1
    q = questions[0]
    assert q.sequence == 1
    assert q.number_norm == "1"
    assert "conditions?" in q.text
    assert len(q.options) == 4
    assert q.source_pages == [1, 2]
    assert "CROSS_PAGE_STITCHED" in q.flags


def test_three_page_span_stitch() -> None:
    p1 = PageExtractionInput(
        page_no=1,
        extraction=PageExtraction(
            items=[
                ExtractedItem(
                    number_raw="1.",
                    number_norm="1",
                    text="Part 1 of long question",
                    continues_on_next_page=True,
                )
            ]
        ),
    )
    p2 = PageExtractionInput(
        page_no=2,
        extraction=PageExtraction(
            items=[
                ExtractedItem(
                    text="Part 2 continuing across page",
                    starts_on_previous_page=True,
                    continues_on_next_page=True,
                )
            ]
        ),
    )
    p3 = PageExtractionInput(
        page_no=3,
        extraction=PageExtraction(
            items=[
                ExtractedItem(
                    text="Part 3 concluding question.",
                    starts_on_previous_page=True,
                    continues_on_next_page=False,
                )
            ]
        ),
    )

    questions = stitch_document_extractions([p1, p2, p3])
    assert len(questions) == 1
    q = questions[0]
    assert q.source_pages == [1, 2, 3]
    assert "CROSS_PAGE_STITCHED" in q.flags
    assert "Part 1" in q.text and "Part 2" in q.text and "Part 3" in q.text


def test_heuristic_uncertain_stitch() -> None:
    p1 = PageExtractionInput(
        page_no=1,
        extraction=PageExtraction(
            items=[
                ExtractedItem(
                    number_raw="1.",
                    number_norm="1",
                    text="The chemical formula for water is",
                    options=[ExtractedOption(label="A", raw_label="(a)", text="H2O")],
                    question_type="mcq_single",
                )
            ]
        ),
    )
    p2 = PageExtractionInput(
        page_no=2,
        extraction=PageExtraction(
            items=[
                ExtractedItem(
                    text="(b) CO2 (c) NaCl (d) CH4",
                    options=[
                        ExtractedOption(label="B", raw_label="(b)", text="CO2"),
                        ExtractedOption(label="C", raw_label="(c)", text="NaCl"),
                        ExtractedOption(label="D", raw_label="(d)", text="CH4"),
                    ],
                )
            ]
        ),
    )

    questions = stitch_document_extractions([p1, p2])
    assert len(questions) == 1
    q = questions[0]
    assert "STITCH_UNCERTAIN" in q.flags
    assert len(q.options) == 4


def test_orphan_fragment_retained() -> None:
    # Page 1 has no questions
    p1 = PageExtractionInput(
        page_no=1,
        extraction=PageExtraction(page_type="instructions", items=[]),
    )
    # Page 2 has an orphaned continuation fragment
    p2 = PageExtractionInput(
        page_no=2,
        extraction=PageExtraction(
            items=[
                ExtractedItem(
                    text="and therefore the equilibrium shifts to the left.",
                    starts_on_previous_page=True,
                )
            ]
        ),
    )

    questions = stitch_document_extractions([p1, p2])
    assert len(questions) == 1
    q = questions[0]
    assert "ORPHAN_FRAGMENT" in q.flags
    assert q.status == "needs_review"


def test_number_inference_gap_and_duplicates() -> None:
    # Q1, missing Q, Q3 -> Q2 inferred
    # Q3 duplicate, Q6 -> gap
    p = PageExtractionInput(
        page_no=1,
        extraction=PageExtraction(
            items=[
                ExtractedItem(number_raw="1.", number_norm="1", text="Question 1 text here"),
                ExtractedItem(text="Question missing number text here"),
                ExtractedItem(number_raw="3.", number_norm="3", text="Question 3 text here"),
                ExtractedItem(number_raw="3.", number_norm="3", text="Duplicate Question 3"),
                ExtractedItem(number_raw="6.", number_norm="6", text="Question 6 text after gap"),
            ]
        ),
    )

    questions = stitch_document_extractions([p])
    assert len(questions) == 5

    # Check inferred
    assert questions[1].number_norm == "2"
    assert questions[1].number_inferred is True
    assert "NUMBER_INFERRED" in questions[1].flags

    # Check duplicate
    assert "DUPLICATE_NUMBER" in questions[3].flags

    # Check gap
    assert "NUMBER_GAP" in questions[4].flags
