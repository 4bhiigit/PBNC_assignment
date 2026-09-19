import pytest

from app.pipeline.options import (
    match_stacked_option,
    normalize_option_label,
    parse_inline_options,
)


@pytest.mark.parametrize(
    ("raw_input", "expected_normalized"),
    [
        ("(A)", "A"),
        ("A.", "A"),
        ("A)", "A"),
        ("(a)", "A"),
        ("a)", "A"),
        ("[A]", "A"),
        ("(1)", "A"),
        ("(2)", "B"),
        ("(3)", "C"),
        ("(4)", "D"),
        ("1)", "A"),
        ("4)", "D"),
        ("(i)", "A"),
        ("(ii)", "B"),
        ("(iii)", "C"),
        ("(iv)", "D"),
        ("(I)", "A"),
        ("(IV)", "D"),
    ],
)
def test_normalize_option_label(raw_input: str, expected_normalized: str) -> None:
    assert normalize_option_label(raw_input) == expected_normalized


@pytest.mark.parametrize(
    ("line", "expected_label", "expected_raw", "expected_text"),
    [
        ("(A) Speed of sound", "A", "(A)", "Speed of sound"),
        ("(a) Velocity vector", "A", "(a)", "Velocity vector"),
        ("A. Kinetic energy", "A", "A.", "Kinetic energy"),
        ("A) Potential energy", "A", "A)", "Potential energy"),
        ("a) Friction coefficient", "A", "a)", "Friction coefficient"),
        ("[B] Angular velocity", "B", "[B]", "Angular velocity"),
        ("(1) Acceleration", "A", "(1)", "Acceleration"),
        ("(2) Displacement", "B", "(2)", "Displacement"),
        ("(3) Force", "C", "(3)", "Force"),
        ("(4) Work done", "D", "(4)", "Work done"),
        ("1) Inertia", "A", "1)", "Inertia"),
        ("2) Torque", "B", "2)", "Torque"),
        ("(i) Monatomic gas", "A", "(i)", "Monatomic gas"),
        ("(ii) Diatomic gas", "B", "(ii)", "Diatomic gas"),
        ("(iii) Triatomic gas", "C", "(iii)", "Triatomic gas"),
        ("(iv) Polyatomic gas", "D", "(iv)", "Polyatomic gas"),
    ],
)
def test_match_stacked_options(
    line: str, expected_label: str, expected_raw: str, expected_text: str
) -> None:
    match = match_stacked_option(line)
    assert match is not None, f"Failed to match line: {line}"
    assert match.label == expected_label
    assert match.raw_label == expected_raw
    assert match.text == expected_text


def test_parse_inline_options() -> None:
    line = "(A) 10 m/s  (B) 20 m/s  (C) 30 m/s  (D) 40 m/s"
    opts = parse_inline_options(line)
    assert len(opts) == 4
    assert [o.label for o in opts] == ["A", "B", "C", "D"]
    assert [o.text for o in opts] == ["10 m/s", "20 m/s", "30 m/s", "40 m/s"]

    line_letters = "(a) Red  (b) Green  (c) Blue"
    opts_letters = parse_inline_options(line_letters)
    assert len(opts_letters) == 3
    assert [o.label for o in opts_letters] == ["A", "B", "C"]
    assert [o.text for o in opts_letters] == ["Red", "Green", "Blue"]

    line_digits = "(1) True  (2) False"
    opts_digits = parse_inline_options(line_digits)
    assert len(opts_digits) == 2
    assert [o.label for o in opts_digits] == ["A", "B"]
    assert [o.text for o in opts_digits] == ["True", "False"]

    single_opt = "(A) Single option without others"
    assert parse_inline_options(single_opt) == []
