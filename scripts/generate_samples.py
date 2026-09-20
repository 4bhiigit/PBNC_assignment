"""Deterministic synthetic sample document generator for Document Intelligence Service.

Generates standard test documents in samples/input/ and matching ground-truth JSON in samples/expected/.
"""

import json
import random
from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Set deterministic random seed
SEED = 42
random.seed(SEED)
np.random.seed(SEED)

INPUT_DIR = Path("samples/input")
EXPECTED_DIR = Path("samples/expected")
INVALID_DIR = INPUT_DIR / "invalid"


def ensure_directories() -> None:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)
    INVALID_DIR.mkdir(parents=True, exist_ok=True)
    Path("docs/demo_evidence").mkdir(parents=True, exist_ok=True)


def draw_table_on_canvas(c: canvas.Canvas, x: float, y: float) -> None:
    """Draws a simple table box on canvas."""
    c.rect(x, y - 60, 300, 60)
    c.line(x, y - 20, x + 300, y - 20)
    c.line(x + 100, y - 60, x + 100, y)
    c.line(x + 200, y - 60, x + 200, y)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x + 10, y - 15, "Parameter")
    c.drawString(x + 110, y - 15, "Value A")
    c.drawString(x + 210, y - 15, "Value B")
    c.setFont("Helvetica", 9)
    c.drawString(x + 10, y - 35, "Voltage")
    c.drawString(x + 110, y - 35, "220 V")
    c.drawString(x + 210, y - 35, "110 V")
    c.drawString(x + 10, y - 55, "Current")
    c.drawString(x + 110, y - 55, "5 A")
    c.drawString(x + 210, y - 55, "10 A")


def draw_figure_on_canvas(c: canvas.Canvas, x: float, y: float) -> None:
    """Draws a simple geometric figure (circuit / triangle) on canvas."""
    c.rect(x, y - 80, 160, 80)
    c.circle(x + 40, y - 40, 20)
    c.line(x + 60, y - 40, x + 120, y - 40)
    c.rect(x + 120, y - 50, 25, 20)
    c.setFont("Helvetica", 8)
    c.drawString(x + 35, y - 43, "V")
    c.drawString(x + 125, y - 43, "R")


def generate_digital_paper_mcq() -> None:
    """Generates digital_paper_mcq.pdf (20 MCQs across 4 pages with table and figure)."""
    pdf_path = INPUT_DIR / "digital_paper_mcq.pdf"
    expected_path = EXPECTED_DIR / "digital_paper_mcq.json"

    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    width, height = letter

    expected_questions = []

    # Page 1: Physics (Q1 - Q5)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, "Section A - Physics")

    questions_p1 = [
        (
            1,
            "1.",
            "What is the SI unit of electric current?",
            ["Ampere", "Volt", "Ohm", "Watt"],
            "A",
        ),
        (
            2,
            "2.",
            "A body of mass 2 kg moves with acceleration 3 m/s^2. Find the net force.",
            ["3 N", "5 N", "6 N", "1.5 N"],
            "C",
        ),
        (
            3,
            "3.",
            "Light year is a unit of which physical quantity?",
            ["Time", "Distance", "Speed", "Intensity"],
            "B",
        ),
        (
            4,
            "4.",
            "Refer to the circuit figure below. Identify the component labeled R.",
            ["Inductor", "Capacitor", "Resistor", "Diode"],
            "C",
        ),
        (
            5,
            "5.",
            "Sound waves cannot travel through which of the following media?",
            ["Water", "Steel", "Air", "Vacuum"],
            "D",
        ),
    ]

    y = height - 80
    for q_num, q_raw, text, opts, ans in questions_p1:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, f"{q_raw} {text}")
        y -= 15
        if q_num == 4:
            draw_figure_on_canvas(c, 70, y)
            y -= 90

        c.setFont("Helvetica", 9)
        labels = ["A", "B", "C", "D"]
        for idx, opt in enumerate(opts):
            lbl = labels[idx]
            c.drawString(70, y, f"({lbl}) {opt}")
            y -= 14
        y -= 10

        expected_questions.append(
            {
                "sequence": q_num,
                "number_raw": q_raw,
                "number_norm": str(q_num),
                "section": "Section A - Physics",
                "type": "mcq_single",
                "text": text,
                "options": [
                    {"label": labels[i], "raw_label": f"({labels[i]})", "text": opts[i]}
                    for i in range(4)
                ],
                "answer_status": "matched",
                "answer_value": [ans],
            }
        )

    c.showPage()

    # Page 2: Chemistry (Q6 - Q10)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, "Section B - Chemistry")

    questions_p2 = [
        (6, "Q.6", "What is the chemical formula of water?", ["H2O", "CO2", "NaCl", "CH4"], "A"),
        (
            7,
            "Q.7",
            "Which gas is released during photosynthesis?",
            ["Nitrogen", "Oxygen", "Carbon dioxide", "Hydrogen"],
            "B",
        ),
        (
            8,
            "Q.8",
            "What is the pH value of pure water at 25 degrees Celsius?",
            ["0", "14", "7", "1"],
            "C",
        ),
        (
            9,
            "Q.9",
            "Refer to the table below comparing parameters across conditions.",
            ["Condition A", "Condition B", "Both equal", "None"],
            "A",
        ),
        (
            10,
            "Q.10",
            "Which element is known as the King of Chemicals?",
            ["Sulphuric Acid", "Hydrochloric Acid", "Nitric Acid", "Acetic Acid"],
            "A",
        ),
    ]

    y = height - 80
    for q_num, q_raw, text, opts, ans in questions_p2:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, f"{q_raw} {text}")
        y -= 15
        if q_num == 9:
            draw_table_on_canvas(c, 70, y)
            y -= 70

        c.setFont("Helvetica", 9)
        labels = ["A", "B", "C", "D"]
        for idx, opt in enumerate(opts):
            lbl = labels[idx]
            c.drawString(70, y, f"({lbl}) {opt}")
            y -= 14
        y -= 10

        expected_questions.append(
            {
                "sequence": q_num,
                "number_raw": q_raw,
                "number_norm": str(q_num),
                "section": "Section B - Chemistry",
                "type": "mcq_single",
                "text": text,
                "options": [
                    {"label": labels[i], "raw_label": f"({labels[i]})", "text": opts[i]}
                    for i in range(4)
                ],
                "answer_status": "matched",
                "answer_value": [ans],
            }
        )

    c.showPage()

    # Page 3: Mathematics Part 1 (Q11 - Q15)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, "Section C - Mathematics")

    questions_p3 = [
        (11, "11)", "Find the value of x if 2x + 6 = 14.", ["2", "3", "4", "5"], "C"),
        (
            12,
            "12)",
            "What is the derivative of sin(x) with respect to x?",
            ["cos(x)", "-cos(x)", "tan(x)", "-sin(x)"],
            "A",
        ),
        (
            13,
            "13)",
            "What is the area of a circle with radius 7 cm? (Use pi = 22/7)",
            ["154 cm^2", "44 cm^2", "77 cm^2", "308 cm^2"],
            "A",
        ),
        (
            14,
            "14)",
            "If matrix A is 2x3 and matrix B is 3x2, what is the order of matrix AB?",
            ["3x3", "2x2", "2x3", "3x2"],
            "B",
        ),
        (
            15,
            "15)",
            "What is the probability of getting a prime number when throwing a fair 6-sided die?",
            ["1/6", "1/3", "1/2", "2/3"],
            "C",
        ),
    ]

    y = height - 80
    for q_num, q_raw, text, opts, ans in questions_p3:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, f"{q_raw} {text}")
        y -= 15
        c.setFont("Helvetica", 9)
        labels = ["A", "B", "C", "D"]
        for idx, opt in enumerate(opts):
            lbl = labels[idx]
            c.drawString(70, y, f"({lbl}) {opt}")
            y -= 14
        y -= 12

        expected_questions.append(
            {
                "sequence": q_num,
                "number_raw": q_raw,
                "number_norm": str(q_num),
                "section": "Section C - Mathematics",
                "type": "mcq_single",
                "text": text,
                "options": [
                    {"label": labels[i], "raw_label": f"({labels[i]})", "text": opts[i]}
                    for i in range(4)
                ],
                "answer_status": "matched",
                "answer_value": [ans],
            }
        )

    c.showPage()

    # Page 4: Mathematics Part 2 (Q16 - Q20)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, "Section C - Mathematics (Contd.)")

    questions_p4 = [
        (
            16,
            "(16)",
            "Find the roots of the quadratic equation x^2 - 5x + 6 = 0.",
            ["2 and 3", "1 and 6", "-2 and -3", "-1 and -6"],
            "A",
        ),
        (
            17,
            "(17)",
            "What is the sum of interior angles of a pentagon?",
            ["180 deg", "360 deg", "540 deg", "720 deg"],
            "C",
        ),
        (
            18,
            "(18)",
            "Evaluate the limit of sin(x)/x as x approaches 0.",
            ["0", "1", "Infinity", "Undefined"],
            "B",
        ),
        (
            19,
            "(19)",
            "What is the distance between points (0,0) and (3,4)?",
            ["3", "4", "5", "7"],
            "C",
        ),
        (20, "(20)", "If log10(x) = 2, what is the value of x?", ["20", "100", "200", "1000"], "B"),
    ]

    y = height - 80
    for q_num, q_raw, text, opts, ans in questions_p4:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, f"{q_raw} {text}")
        y -= 15
        c.setFont("Helvetica", 9)
        labels = ["A", "B", "C", "D"]
        for idx, opt in enumerate(opts):
            lbl = labels[idx]
            c.drawString(70, y, f"({lbl}) {opt}")
            y -= 14
        y -= 12

        expected_questions.append(
            {
                "sequence": q_num,
                "number_raw": q_raw,
                "number_norm": str(q_num),
                "section": "Section C - Mathematics",
                "type": "mcq_single",
                "text": text,
                "options": [
                    {"label": labels[i], "raw_label": f"({labels[i]})", "text": opts[i]}
                    for i in range(4)
                ],
                "answer_status": "matched",
                "answer_value": [ans],
            }
        )

    c.save()

    expected_payload = {
        "filename": "digital_paper_mcq.pdf",
        "page_count": 4,
        "role": "question_paper",
        "questions_count": 20,
        "questions": expected_questions,
    }
    expected_path.write_text(json.dumps(expected_payload, indent=2), encoding="utf-8")


def generate_digital_paper_spanning() -> None:
    """Generates digital_paper_spanning.pdf with 2-page and 3-page spanning questions."""
    pdf_path = INPUT_DIR / "digital_paper_spanning.pdf"
    expected_path = EXPECTED_DIR / "digital_paper_spanning.json"

    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    width, height = letter

    # Page 1: Q1 (normal) + Q2 (starts on page 1, continues on page 2)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, "Spanning Question Test Paper")

    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, height - 90, "1. What is the acceleration due to gravity on Earth?")
    c.setFont("Helvetica", 9)
    c.drawString(70, height - 110, "(A) 9.8 m/s^2")
    c.drawString(70, height - 125, "(B) 8.9 m/s^2")
    c.drawString(70, height - 140, "(C) 10.8 m/s^2")
    c.drawString(70, height - 155, "(D) 7.8 m/s^2")

    # Q2 starts near page bottom
    c.setFont("Helvetica-Bold", 10)
    c.drawString(
        50,
        100,
        "2. A block of mass 10 kg slides down a frictionless inclined plane of angle 30 degrees.",
    )
    c.setFont("Helvetica", 9)
    c.drawString(
        50,
        85,
        "If the plane has a total length of 20 meters, determine the time taken by the block",
    )
    c.drawString(
        50, 70, "to reach the bottom starting from rest, and choose the correct answer below:"
    )
    c.drawString(70, 50, "(A) 2.02 seconds")
    c.drawString(70, 35, "(B) 2.86 seconds")
    c.showPage()

    # Page 2: Q2 continuation + Q3 normal + Q4 start (spans 3 pages)
    c.setFont("Helvetica", 9)
    c.drawString(70, height - 50, "(C) 3.50 seconds")
    c.drawString(70, height - 65, "(D) 4.10 seconds")

    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, height - 110, "3. What is the unit of magnetic flux density?")
    c.setFont("Helvetica", 9)
    c.drawString(70, height - 130, "(A) Tesla")
    c.drawString(70, height - 145, "(B) Weber")
    c.drawString(70, height - 160, "(C) Henry")
    c.drawString(70, height - 175, "(D) Gauss")

    # Q4 starts near bottom of page 2
    c.setFont("Helvetica-Bold", 10)
    c.drawString(
        50,
        100,
        "4. Consider a thermodynamic heat engine operating between two thermal reservoirs at",
    )
    c.setFont("Helvetica", 9)
    c.drawString(
        50,
        85,
        "temperatures T_hot = 600 K and T_cold = 300 K. The working substance undergoes a Carnot",
    )
    c.drawString(
        50,
        70,
        "cycle consisting of two reversible isothermal processes and two reversible adiabatic processes.",
    )
    c.showPage()

    # Page 3: Q4 middle fragment
    c.setFont("Helvetica", 9)
    c.drawString(
        50,
        height - 50,
        "During the isothermal expansion at 600 K, the engine absorbs 1200 Joules of heat from the hot reservoir.",
    )
    c.drawString(
        50,
        height - 65,
        "Calculate the theoretical maximum efficiency and the net mechanical work output performed per cycle:",
    )
    c.drawString(70, height - 90, "(A) Efficiency = 50%, Work = 600 J")
    c.drawString(70, height - 105, "(B) Efficiency = 40%, Work = 480 J")
    c.showPage()

    # Page 4: Q4 end fragment + Q5 normal
    c.setFont("Helvetica", 9)
    c.drawString(70, height - 50, "(C) Efficiency = 60%, Work = 720 J")
    c.drawString(70, height - 65, "(D) Efficiency = 75%, Work = 900 J")

    c.setFont("Helvetica-Bold", 10)
    c.drawString(
        50, height - 110, "5. Which law of thermodynamics establishes the concept of entropy?"
    )
    c.setFont("Helvetica", 9)
    c.drawString(70, height - 130, "(A) Zeroth Law")
    c.drawString(70, height - 145, "(B) First Law")
    c.drawString(70, height - 160, "(C) Second Law")
    c.drawString(70, height - 175, "(D) Third Law")

    c.save()

    expected_payload = {
        "filename": "digital_paper_spanning.pdf",
        "page_count": 4,
        "role": "question_paper",
        "questions_count": 5,
        "questions": [
            {"sequence": 1, "number_raw": "1.", "number_norm": "1", "source_pages": [1]},
            {
                "sequence": 2,
                "number_raw": "2.",
                "number_norm": "2",
                "source_pages": [1, 2],
                "flags": ["CROSS_PAGE_STITCHED"],
            },
            {"sequence": 3, "number_raw": "3.", "number_norm": "3", "source_pages": [2]},
            {
                "sequence": 4,
                "number_raw": "4.",
                "number_norm": "4",
                "source_pages": [2, 3, 4],
                "flags": ["CROSS_PAGE_STITCHED"],
            },
            {"sequence": 5, "number_raw": "5.", "number_norm": "5", "source_pages": [4]},
        ],
    }
    expected_path.write_text(json.dumps(expected_payload, indent=2), encoding="utf-8")


def generate_paper_with_key_at_end() -> None:
    """Generates paper_with_key_at_end.pdf with MCQs followed by Answer Key at end."""
    pdf_path = INPUT_DIR / "paper_with_key_at_end.pdf"
    expected_path = EXPECTED_DIR / "paper_with_key_at_end.json"

    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    width, height = letter

    # Page 1: 5 MCQs
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, "Science Assessment Paper")

    questions = [
        (
            1,
            "1.",
            "Which gas is essential for human respiration?",
            ["Oxygen", "Carbon Dioxide", "Nitrogen", "Methane"],
            "A",
        ),
        (
            2,
            "2.",
            "What is the chemical formula of common salt?",
            ["NaCl", "KCl", "CaCl2", "MgCl2"],
            "A",
        ),
        (
            3,
            "3.",
            "How many bones are in the adult human skeleton?",
            ["206", "214", "198", "250"],
            "A",
        ),
        (
            4,
            "4.",
            "Which organ pumps blood throughout the human body?",
            ["Lungs", "Brain", "Heart", "Kidney"],
            "C",
        ),
        (
            5,
            "5.",
            "What is the boiling point of pure water at 1 atm?",
            ["50 C", "100 C", "150 C", "200 C"],
            "B",
        ),
    ]

    y = height - 90
    for _q_num, q_raw, text, opts, _ans in questions:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, f"{q_raw} {text}")
        y -= 15
        c.setFont("Helvetica", 9)
        labels = ["A", "B", "C", "D"]
        for idx, opt in enumerate(opts):
            c.drawString(70, y, f"({labels[idx]}) {opt}")
            y -= 14
        y -= 10

    c.showPage()

    # Page 2: Answer Key grid/table
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, "Answer Key")

    c.setFont("Helvetica", 11)
    c.drawString(50, height - 90, "1 - A")
    c.drawString(50, height - 110, "2 - A")
    c.drawString(50, height - 130, "3 - A")
    c.drawString(50, height - 150, "4 - C")
    c.drawString(50, height - 170, "5 - B")

    c.save()

    expected_payload = {
        "filename": "paper_with_key_at_end.pdf",
        "page_count": 2,
        "role": "combined",
        "questions_count": 5,
        "answer_keys_count": 5,
        "answers": {"1": "A", "2": "A", "3": "A", "4": "C", "5": "B"},
    }
    expected_path.write_text(json.dumps(expected_payload, indent=2), encoding="utf-8")


def generate_paper_with_key_at_start() -> None:
    """Generates paper_with_key_at_start.pdf with Answer Key on page 1."""
    pdf_path = INPUT_DIR / "paper_with_key_at_start.pdf"
    expected_path = EXPECTED_DIR / "paper_with_key_at_start.json"

    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    width, height = letter

    # Page 1: Answer Key table
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, "Official Solutions and Answer Key")

    c.setFont("Helvetica", 11)
    c.drawString(50, height - 90, "1. (b)")
    c.drawString(50, height - 110, "2. (c)")
    c.drawString(50, height - 130, "3. (a)")
    c.drawString(50, height - 150, "4. (d)")

    c.showPage()

    # Page 2: Questions
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, "Questions Section")

    questions = [
        (
            1,
            "1.",
            "What is the capital city of France?",
            ["Rome", "Paris", "Berlin", "Madrid"],
            "B",
        ),
        (
            2,
            "2.",
            "Which ocean is the largest on Earth?",
            ["Atlantic", "Indian", "Pacific", "Arctic"],
            "C",
        ),
        (
            3,
            "3.",
            "Who wrote the play Romeo and Juliet?",
            ["Shakespeare", "Milton", "Chaucer", "Keats"],
            "A",
        ),
        (4, "4.", "What is the currency of Japan?", ["Yuan", "Won", "Baht", "Yen"], "D"),
    ]

    y = height - 90
    for _q_num, q_raw, text, opts, _ans in questions:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, f"{q_raw} {text}")
        y -= 15
        c.setFont("Helvetica", 9)
        labels = ["A", "B", "C", "D"]
        for idx, opt in enumerate(opts):
            c.drawString(70, y, f"({labels[idx]}) {opt}")
            y -= 14
        y -= 10

    c.save()

    expected_payload = {
        "filename": "paper_with_key_at_start.pdf",
        "page_count": 2,
        "role": "combined",
        "questions_count": 4,
        "answer_keys_count": 4,
        "answers": {"1": "B", "2": "C", "3": "A", "4": "D"},
    }
    expected_path.write_text(json.dumps(expected_payload, indent=2), encoding="utf-8")


def generate_answer_key_separate() -> None:
    """Generates standalone answer_key_separate.pdf with matched, unmatched, and out-of-range keys."""
    pdf_path = INPUT_DIR / "answer_key_separate.pdf"
    expected_path = EXPECTED_DIR / "answer_key_separate.json"

    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, "Answer Key for Digital Paper MCQ")

    c.setFont("Helvetica", 10)
    y = height - 90
    # 20 matching keys
    keys = [
        ("1", "A"),
        ("2", "C"),
        ("3", "B"),
        ("4", "C"),
        ("5", "D"),
        ("6", "A"),
        ("7", "B"),
        ("8", "C"),
        ("9", "A"),
        ("10", "A"),
        ("11", "C"),
        ("12", "A"),
        ("13", "A"),
        ("14", "B"),
        ("15", "C"),
        ("16", "A"),
        ("17", "C"),
        ("18", "B"),
        ("19", "C"),
        ("20", "Z"),  # Out of range! (Z not in options)
        ("99", "A"),  # Unmatched key entry!
    ]

    for q_num, ans in keys:
        c.drawString(50, y, f"Q{q_num}: {ans}")
        y -= 18

    c.save()

    expected_payload = {
        "filename": "answer_key_separate.pdf",
        "page_count": 1,
        "role": "answer_key",
        "total_entries": 21,
        "matched_count": 19,
        "out_of_range_entries": ["20"],
        "unmatched_entries": ["99"],
    }
    expected_path.write_text(json.dumps(expected_payload, indent=2), encoding="utf-8")


def generate_scanned_clean() -> None:
    """Generates scanned_clean.pdf by rasterizing text to clean image and saving as PDF."""
    pdf_path = INPUT_DIR / "scanned_clean.pdf"
    expected_path = EXPECTED_DIR / "scanned_clean.json"

    img = Image.new("RGB", (1200, 1600), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    text_lines = [
        "General Science Scanned Quiz",
        "",
        "1. What is the hardest natural mineral on Earth?",
        "(A) Diamond",
        "(B) Corundum",
        "(C) Quartz",
        "(D) Topaz",
        "",
        "2. Which gas gives soda water its fizz?",
        "(A) Oxygen",
        "(B) Carbon Dioxide",
        "(C) Nitrogen",
        "(D) Hydrogen",
        "",
        "3. What is the unit of frequency?",
        "(A) Hertz",
        "(B) Decibel",
        "(C) Joule",
        "(D) Tesla",
    ]

    y = 80
    for line in text_lines:
        if line.startswith("General"):
            draw.text((80, y), line, fill=(0, 0, 0))
            y += 60
        elif line and line[0].isdigit():
            draw.text((80, y), line, fill=(0, 0, 0))
            y += 40
        elif line:
            draw.text((120, y), line, fill=(0, 0, 0))
            y += 35
        else:
            y += 20

    img.save(str(pdf_path), "PDF", resolution=200.0)

    expected_payload = {
        "filename": "scanned_clean.pdf",
        "page_count": 1,
        "role": "question_paper",
        "questions_count": 3,
        "questions": [
            {"sequence": 1, "number_norm": "1", "answer_value": ["A"]},
            {"sequence": 2, "number_norm": "2", "answer_value": ["B"]},
            {"sequence": 3, "number_norm": "3", "answer_value": ["A"]},
        ],
    }
    expected_path.write_text(json.dumps(expected_payload, indent=2), encoding="utf-8")


def generate_scanned_lowquality() -> None:
    """Generates scanned_lowquality.pdf with skew, blur, noise, and one page rotated by 90 degrees."""
    pdf_path = INPUT_DIR / "scanned_lowquality.pdf"
    expected_path = EXPECTED_DIR / "scanned_lowquality.json"

    # Page 1: Skewed and noisy
    img1 = Image.new("RGB", (1000, 1400), color=(245, 245, 245))
    draw1 = ImageDraw.Draw(img1)

    draw1.text((70, 80), "Low Quality Scanned Exam - Page 1", fill=(30, 30, 30))
    draw1.text((70, 140), "1. What is the speed of light in vacuum?", fill=(30, 30, 30))
    draw1.text((100, 180), "(A) 3 x 10^8 m/s", fill=(30, 30, 30))
    draw1.text((100, 215), "(B) 3 x 10^6 m/s", fill=(30, 30, 30))
    draw1.text((100, 250), "(C) 3 x 10^5 m/s", fill=(30, 30, 30))
    draw1.text((100, 285), "(D) 3 x 10^7 m/s", fill=(30, 30, 30))

    # Apply 3-degree skew using OpenCV
    cv_img1 = np.array(img1)
    rows, cols, _ = cv_img1.shape
    M = cv2.getRotationMatrix2D((cols / 2, rows / 2), 3.0, 1.0)
    skewed1 = cv2.warpAffine(cv_img1, M, (cols, rows), borderValue=(245, 245, 245))
    # Add Gaussian blur and noise
    blurred1 = cv2.GaussianBlur(skewed1, (3, 3), 0.8)
    noise = np.random.normal(0, 10, blurred1.shape).astype(np.uint8)
    noisy1 = cv2.add(blurred1, noise)

    pil_p1 = Image.fromarray(noisy1)

    # Page 2: Rotated 90 degrees clockwise
    img2 = Image.new("RGB", (1000, 1400), color=(245, 245, 245))
    draw2 = ImageDraw.Draw(img2)
    draw2.text((70, 80), "Low Quality Scanned Exam - Page 2", fill=(30, 30, 30))
    draw2.text((70, 140), "2. Which organelle is the powerhouse of the cell?", fill=(30, 30, 30))
    draw2.text((100, 180), "(A) Ribosome", fill=(30, 30, 30))
    draw2.text((100, 215), "(B) Mitochondria", fill=(30, 30, 30))
    draw2.text((100, 250), "(C) Nucleus", fill=(30, 30, 30))
    draw2.text((100, 285), "(D) Golgi Body", fill=(30, 30, 30))

    pil_p2 = img2.rotate(-90, expand=True)

    pil_p1.save(str(pdf_path), "PDF", save_all=True, append_images=[pil_p2], resolution=120.0)

    expected_payload = {
        "filename": "scanned_lowquality.pdf",
        "page_count": 2,
        "role": "question_paper",
        "quality_issues": ["BLURRY", "ROTATED_CORRECTED", "LOW_RESOLUTION"],
        "questions_count": 2,
    }
    expected_path.write_text(json.dumps(expected_payload, indent=2), encoding="utf-8")


def generate_scan_images() -> None:
    """Generates scan_page.png and scan_page.jpg standalone images."""
    png_path = INPUT_DIR / "scan_page.png"
    jpg_path = INPUT_DIR / "scan_page.jpg"

    img = Image.new("RGB", (900, 1200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.text((60, 60), "Single Page Scanned Quiz", fill=(0, 0, 0))
    draw.text((60, 120), "1. Which element has the atomic number 1?", fill=(0, 0, 0))
    draw.text((90, 155), "(A) Helium", fill=(0, 0, 0))
    draw.text((90, 185), "(B) Hydrogen", fill=(0, 0, 0))
    draw.text((90, 215), "(C) Lithium", fill=(0, 0, 0))
    draw.text((90, 245), "(D) Carbon", fill=(0, 0, 0))

    draw.text((60, 310), "2. What is the value of gravitational constant G?", fill=(0, 0, 0))
    draw.text((90, 345), "(A) 6.67 x 10^-11 N m^2/kg^2", fill=(0, 0, 0))
    draw.text((90, 375), "(B) 9.8 m/s^2", fill=(0, 0, 0))
    draw.text((90, 405), "(C) 3.0 x 10^8 m/s", fill=(0, 0, 0))
    draw.text((90, 435), "(D) 1.6 x 10^-19 C", fill=(0, 0, 0))

    img.save(str(png_path), "PNG")
    img.save(str(jpg_path), "JPEG", quality=85)


def generate_low_confidence_paper() -> None:
    """Generates low_confidence.pdf with missing numbers, torn options, and duplicates."""
    pdf_path = INPUT_DIR / "low_confidence.pdf"
    expected_path = EXPECTED_DIR / "low_confidence.json"

    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, "Low Confidence Sample Document")

    # Question with missing number
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 90, "Which instrument is used to measure atmospheric pressure?")
    c.drawString(70, height - 110, "(A) Barometer")
    c.drawString(70, height - 125, "(B) Thermometer")

    # Duplicate numbered question 1
    c.drawString(50, height - 160, "1. What is the chemical symbol for Gold?")
    c.drawString(70, height - 180, "(A) Au")
    c.drawString(70, height - 195, "(B) Ag")

    # Second duplicate numbered question 1
    c.drawString(50, height - 230, "1. What is the chemical symbol for Silver?")
    c.drawString(70, height - 250, "(A) Ag")
    c.drawString(70, height - 265, "(B) Au")

    # MCQ with single option (torn options)
    c.drawString(50, height - 300, "2. Single option incomplete question.")
    c.drawString(70, height - 320, "(A) Only One Option Given")

    c.save()

    expected_payload = {
        "filename": "low_confidence.pdf",
        "page_count": 1,
        "expected_flags": ["MISSING_NUMBER", "DUPLICATE_NUMBER", "MCQ_OPTIONS_LT_2"],
        "expected_status": "needs_review",
    }
    expected_path.write_text(json.dumps(expected_payload, indent=2), encoding="utf-8")


def generate_invalid_files() -> None:
    """Generates invalid files set in samples/input/invalid/."""
    # 1. fake.pdf (text content pretending to be PDF)
    (INVALID_DIR / "fake.pdf").write_text(
        "This is an executable or raw text pretending to be PDF.", encoding="utf-8"
    )

    # 2. truncated.pdf (PDF header with truncated body)
    (INVALID_DIR / "truncated.pdf").write_bytes(b"%PDF-1.4\n% truncated bytes...")

    # 3. notes.txt (unsupported MIME text file)
    (INVALID_DIR / "notes.txt").write_text(
        "Plain text notes that should be rejected by upload MIME validation.", encoding="utf-8"
    )

    # 4. encrypted.pdf (password protected PDF)
    enc_doc = fitz.open()
    enc_page = enc_doc.new_page()
    enc_page.insert_text((50, 50), "Secret encrypted content")
    enc_doc.save(
        str(INVALID_DIR / "encrypted.pdf"),
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw="password123",
        owner_pw="admin123",
    )
    enc_doc.close()

    # 5. bomb.png (high dimension decompression bomb attempt)
    # Using Pillow with small file size but large dimensions
    bomb_img = Image.new("1", (10000, 10000), color=0)
    bomb_img.save(str(INVALID_DIR / "bomb.png"), "PNG", optimize=True)


def generate_all_samples() -> None:
    ensure_directories()
    print("Generating digital_paper_mcq.pdf...")
    generate_digital_paper_mcq()
    print("Generating digital_paper_spanning.pdf...")
    generate_digital_paper_spanning()
    print("Generating paper_with_key_at_end.pdf...")
    generate_paper_with_key_at_end()
    print("Generating paper_with_key_at_start.pdf...")
    generate_paper_with_key_at_start()
    print("Generating answer_key_separate.pdf...")
    generate_answer_key_separate()
    print("Generating scanned_clean.pdf...")
    generate_scanned_clean()
    print("Generating scanned_lowquality.pdf...")
    generate_scanned_lowquality()
    print("Generating scan_page images (png and jpg)...")
    generate_scan_images()
    print("Generating low_confidence.pdf...")
    generate_low_confidence_paper()
    print("Generating invalid test files...")
    generate_invalid_files()
    print("Sample generation completed successfully!")


if __name__ == "__main__":
    generate_all_samples()
