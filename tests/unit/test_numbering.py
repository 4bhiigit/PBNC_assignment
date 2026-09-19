import pytest

from app.pipeline.numbering import match_question_number, match_section_heading


@pytest.mark.parametrize(
    ("line", "expected_raw", "expected_norm", "expected_rest"),
    [
        # Standard digits
        ("1. What is the speed of light?", "1.", "1", "What is the speed of light?"),
        ("1) What is Newton's second law?", "1)", "1", "What is Newton's second law?"),
        ("(1) Explain thermodynamics.", "(1)", "1", "Explain thermodynamics."),
        ("[1] Calculate the momentum.", "[1]", "1", "Calculate the momentum."),
        ("12. Solve for x.", "12.", "12", "Solve for x."),
        ("1 - State Ohm's law.", "1 -", "1", "State Ohm's law."),
        ("1: Define entropy.", "1:", "1", "Define entropy."),
        # Question prefixes
        ("Q1. What is the capital of France?", "Q1.", "1", "What is the capital of France?"),
        ("Q.1 Find the derivative.", "Q.1", "1", "Find the derivative."),
        ("Q 1: Find the integral.", "Q 1:", "1", "Find the integral."),
        ("Q1: Name the planet.", "Q1:", "1", "Name the planet."),
        ("Question 1. Describe photosynthesis.", "Question 1.", "1", "Describe photosynthesis."),
        ("Question 1: What is gravity?", "Question 1:", "1", "What is gravity?"),
        ("Que. 4 Compute the area.", "Que. 4", "4", "Compute the area."),
        # Hindi numbering
        ("प्र.1 प्रकाश संश्लेषण क्या है?", "प्र.1", "1", "प्रकाश संश्लेषण क्या है?"),
        ("प्र. 5 न्यूटन का नियम लिखिए।", "प्र. 5", "5", "न्यूटन का नियम लिखिए।"),
        ("प्रश्न 2: ऊर्जा क्या है?", "प्रश्न 2:", "2", "ऊर्जा क्या है?"),
    ],
)
def test_match_question_number_formats(
    line: str, expected_raw: str, expected_norm: str, expected_rest: str
) -> None:
    match = match_question_number(line)
    assert match is not None, f"Failed to match line: {line}"
    assert match.normalized == expected_norm
    assert match.raw == expected_raw
    assert match.rest_of_line == expected_rest


@pytest.mark.parametrize(
    "line",
    [
        "This is just normal text without numbers.",
        "Section A - Physics",
        "(a) Option text only",
        "A. Another option",
        "In 1999, Einstein's theory was celebrated.",
    ],
)
def test_non_question_number_lines_return_none(line: str) -> None:
    assert match_question_number(line) is None


@pytest.mark.parametrize(
    ("line", "expected_heading"),
    [
        ("Section A - Physics", "Section A - Physics"),
        ("Section-1: Chemistry", "Section-1: Chemistry"),
        ("Part B: Mathematics", "Part B: Mathematics"),
        ("खण्ड अ", "खण्ड अ"),
        ("भाग 1", "भाग 1"),
        ("Physics - Mechanics", "Physics - Mechanics"),
        ("Mathematics", "Mathematics"),
    ],
)
def test_match_section_headings(line: str, expected_heading: str) -> None:
    heading = match_section_heading(line)
    assert heading is not None
    assert expected_heading.lower() in heading.lower()
