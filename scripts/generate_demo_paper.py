"""Generates a professional multi-page examination paper PDF for video demonstration.

Includes:
- Official Header & Student Instructions
- Section A - Physics (with Diagram reference and cross-page split question)
- Section B - Chemistry (with Chemical formulas and reactions)
- Section C - Mathematics (with Equations and Calculus)
- Final Page: Official Answer Key & Solutions Grid
"""

from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import reportlab.lib.colors as colors

OUTPUT_PATHS = [
    Path("demo_question_paper.pdf"),
    Path("National_Entrance_Exam_2026.pdf"),
    Path("samples/input/demo_question_paper.pdf"),
]


def draw_header_footer(c: canvas.Canvas, page_num: int, total_pages: int, width: float, height: float):
    # Top Exam Header
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 35, "NATIONAL ENTRANCE & TALENT EXAMINATION (NETE - 2026)")
    c.setFont("Helvetica", 9)
    c.drawRightString(width - 50, height - 35, "CODE: PH-CH-MA-2026")
    
    c.setStrokeColor(colors.HexColor("#334155"))
    c.setLineWidth(1)
    c.line(50, height - 42, width - 50, height - 42)
    
    # Bottom Footer
    c.line(50, 35, width - 50, 35)
    c.setFont("Helvetica", 8)
    c.drawString(50, 24, "DocIntel Examination Processing Engine • Confidential Assessment")
    c.drawRightString(width - 50, 24, f"Page {page_num} of {total_pages}")


def generate_demo_pdf():
    for p in OUTPUT_PATHS:
        p.parent.mkdir(parents=True, exist_ok=True)
        
    main_path = OUTPUT_PATHS[0]
    c = canvas.Canvas(str(main_path), pagesize=letter)
    width, height = letter
    total_pages = 4

    # =========================================================================
    # PAGE 1: Instructions & Physics (Q1 to Q4 start)
    # =========================================================================
    draw_header_footer(c, 1, total_pages, width, height)
    
    # Instructions Box
    c.setFillColor(colors.HexColor("#f8fafc"))
    c.setStrokeColor(colors.HexColor("#cbd5e1"))
    c.rect(50, height - 95, width - 100, 42, fill=1, stroke=1)
    
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(60, height - 65, "GENERAL INSTRUCTIONS:")
    c.setFont("Helvetica", 8)
    c.drawString(60, height - 77, "1. This paper contains 15 Multiple Choice Questions divided into 3 Sections: Physics, Chemistry & Mathematics.")
    c.drawString(60, height - 88, "2. Each question has four options (A, B, C, D) with exactly one correct option. Darken the corresponding circle.")

    # Section A Heading
    y = height - 120
    c.setFillColor(colors.HexColor("#1e293b"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Section A — Physics")
    y -= 25

    # Q1
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "1. What is the SI unit of electrical capacitance in terms of base units?")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(70, y, "(A) Farad (C / V)")
    c.drawString(220, y, "(B) Henry (Wb / A)")
    y -= 14
    c.drawString(70, y, "(C) Siemens (A / V)")
    c.drawString(220, y, "(D) Weber (J / A)")
    y -= 22

    # Q2
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "2. A particle moves along a circular path of radius R with constant speed v. What is the magnitude")
    y -= 13
    c.drawString(50, y, "   of average acceleration over half a revolution?")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(70, y, "(A) 2v^2 / (pi * R)")
    c.drawString(220, y, "(B) v^2 / R")
    y -= 14
    c.drawString(70, y, "(C) pi * v^2 / (2 * R)")
    c.drawString(220, y, "(D) Zero")
    y -= 22

    # Q3
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "3. Light of wavelength 600 nm is incident normally on a diffraction grating with 5000 lines per cm.")
    y -= 13
    c.drawString(50, y, "   What is the maximum number of diffraction orders observed?")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(70, y, "(A) 2")
    c.drawString(160, y, "(B) 3")
    c.drawString(250, y, "(C) 5")
    c.drawString(340, y, "(D) 7")
    y -= 26

    # Q4 (Spanning Question: Part 1 on Page 1, Part 2 on Page 2)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "4. Consider an idealized thermodynamic Carnot engine operating between temperatures T1 = 800 K")
    y -= 13
    c.drawString(50, y, "   and T2 = 400 K. In each cycle, the working substance absorbs 1000 Joules of thermal energy")
    y -= 13
    c.drawString(50, y, "   from the high-temperature reservoir. Calculate the theoretical thermal efficiency and the net")
    y -= 13
    c.drawString(50, y, "   mechanical work output delivered per cycle:")
    y -= 15
    c.setFont("Helvetica", 9)
    c.drawString(70, y, "(A) Efficiency = 50%, Work Output = 500 Joules")
    y -= 14
    c.drawString(70, y, "(B) Efficiency = 40%, Work Output = 400 Joules")
    y -= 10
    # Page break after (B)
    c.showPage()

    # =========================================================================
    # PAGE 2: Q4 Continuation + Q5 + Section B: Chemistry (Q6 to Q8)
    # =========================================================================
    draw_header_footer(c, 2, total_pages, width, height)
    
    y = height - 60
    # Q4 Continuation Options
    c.setFont("Helvetica", 9)
    c.drawString(70, y, "(C) Efficiency = 60%, Work Output = 600 Joules")
    y -= 14
    c.drawString(70, y, "(D) Efficiency = 75%, Work Output = 750 Joules")
    y -= 25

    # Q5
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "5. Which fundamental law of physics establishes that magnetic monopoles do not exist in isolation?")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(70, y, "(A) Gauss's Law for Magnetism (div B = 0)")
    y -= 14
    c.drawString(70, y, "(B) Ampere's Circuital Law")
    y -= 14
    c.drawString(70, y, "(C) Faraday's Law of Electromagnetic Induction")
    y -= 14
    c.drawString(70, y, "(D) Coulomb's Law of Electrostatics")
    y -= 30

    # Section B Heading
    c.setFillColor(colors.HexColor("#1e293b"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Section B — Chemistry")
    y -= 25

    # Q6
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "6. What is the IUPAC systematic name for the compound CH3-CH(CH3)-CH2-CHO?")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(70, y, "(A) 2-Methylbutanal")
    c.drawString(240, y, "(B) 3-Methylbutanal")
    y -= 14
    c.drawString(70, y, "(C) 3-Methylbutanoic acid")
    c.drawString(240, y, "(D) 2-Methylbutan-1-one")
    y -= 22

    # Q7
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "7. Which of the following elements possesses the highest first ionization enthalpy?")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(70, y, "(A) Helium (He)")
    c.drawString(200, y, "(B) Fluorine (F)")
    c.drawString(330, y, "(C) Neon (Ne)")
    y -= 14
    c.drawString(70, y, "(D) Nitrogen (N)")
    c.drawString(200, y, "(E) Oxygen (O)")
    y -= 22

    # Q8
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "8. What is the oxidation state of Chromium (Cr) in the dichromate ion [Cr2O7]^(2-)?")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(70, y, "(A) +3")
    c.drawString(160, y, "(B) +4")
    c.drawString(250, y, "(C) +6")
    c.drawString(340, y, "(D) +7")
    y -= 10

    c.showPage()

    # =========================================================================
    # PAGE 3: Chemistry (Q9, Q10) + Section C: Mathematics (Q11 to Q15)
    # =========================================================================
    draw_header_footer(c, 3, total_pages, width, height)
    
    y = height - 60

    # Q9
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "9. For a first-order chemical reaction with rate constant k = 0.0693 min^-1, what is the half-life?")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(70, y, "(A) 5.0 minutes")
    c.drawString(220, y, "(B) 10.0 minutes")
    y -= 14
    c.drawString(70, y, "(C) 15.0 minutes")
    c.drawString(220, y, "(D) 20.0 minutes")
    y -= 22

    # Q10
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "10. Which coordination geometry is typically associated with d8 transition metal complexes with strong field ligands?")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(70, y, "(A) Tetrahedral")
    c.drawString(220, y, "(B) Square Planar")
    y -= 14
    c.drawString(70, y, "(C) Octahedral")
    c.drawString(220, y, "(D) Trigonal Bipyramidal")
    y -= 30

    # Section C Heading
    c.setFillColor(colors.HexColor("#1e293b"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Section C — Mathematics")
    y -= 25

    # Q11
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "11. If alpha and beta are the roots of quadratic equation x^2 - 7x + 12 = 0, find the value of (alpha^2 + beta^2):")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(70, y, "(A) 25")
    c.drawString(160, y, "(B) 37")
    c.drawString(250, y, "(C) 49")
    c.drawString(340, y, "(D) 13")
    y -= 22

    # Q12
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "12. Evaluate the definite integral: Integral from 0 to pi/2 of [sin(x) / (sin(x) + cos(x))] dx")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(70, y, "(A) pi / 4")
    c.drawString(160, y, "(B) pi / 2")
    c.drawString(250, y, "(C) 1")
    c.drawString(340, y, "(D) 0")
    y -= 22

    # Q13
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "13. What is the value of limit as x approaches 0 for: (e^(3x) - 1) / (sin(2x))?")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(70, y, "(A) 1.0")
    c.drawString(160, y, "(B) 1.5 (3/2)")
    c.drawString(250, y, "(C) 2.0")
    c.drawString(340, y, "(D) 0.67 (2/3)")
    y -= 22

    # Q14
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "14. If a matrix A of order 3x3 has determinant det(A) = 4, what is the determinant of 2 * adj(A)?")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(70, y, "(A) 64")
    c.drawString(160, y, "(B) 128")
    c.drawString(250, y, "(C) 256")
    c.drawString(340, y, "(D) 512")
    y -= 22

    # Q15
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "15. Two fair 6-sided dice are thrown simultaneously. What is the probability that the sum is at least 10?")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(70, y, "(A) 1 / 12")
    c.drawString(160, y, "(B) 1 / 6")
    c.drawString(250, y, "(C) 1 / 4")
    c.drawString(340, y, "(D) 5 / 36")
    y -= 10

    c.showPage()

    # =========================================================================
    # PAGE 4: Official Answer Key & Solutions Grid
    # =========================================================================
    draw_header_footer(c, 4, total_pages, width, height)
    
    y = height - 70
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Official Solutions & Answer Key")
    y -= 15
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawString(50, y, "Master evaluation grid for automated reconciliation.")
    y -= 30

    # Answer key grid box
    c.setFillColor(colors.HexColor("#f8fafc"))
    c.setStrokeColor(colors.HexColor("#cbd5e1"))
    c.rect(50, y - 240, width - 100, 250, fill=1, stroke=1)

    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(70, y - 20, "QUESTION NUMBER")
    c.drawString(220, y - 20, "SUBJECT / SECTION")
    c.drawString(380, y - 20, "CORRECT OPTION")
    
    c.setStrokeColor(colors.HexColor("#94a3b8"))
    c.line(65, y - 26, width - 65, y - 26)

    keys = [
        ("1", "Section A - Physics", "A"),
        ("2", "Section A - Physics", "A"),
        ("3", "Section A - Physics", "B"),
        ("4", "Section A - Physics", "A"),
        ("5", "Section A - Physics", "A"),
        ("6", "Section B - Chemistry", "B"),
        ("7", "Section B - Chemistry", "A"),
        ("8", "Section B - Chemistry", "C"),
        ("9", "Section B - Chemistry", "B"),
        ("10", "Section B - Chemistry", "B"),
        ("11", "Section C - Mathematics", "A"),
        ("12", "Section C - Mathematics", "A"),
        ("13", "Section C - Mathematics", "B"),
        ("14", "Section C - Mathematics", "B"),
        ("15", "Section C - Mathematics", "B"),
    ]

    c.setFont("Helvetica", 9)
    row_y = y - 40
    for q_no, sec, ans in keys:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(75, row_y, f"Question {q_no}")
        c.setFont("Helvetica", 9)
        c.drawString(220, row_y, sec)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(390, row_y, f"({ans})")
        row_y -= 13

    c.save()

    # Also copy bytes to other paths
    pdf_bytes = main_path.read_bytes()
    for p in OUTPUT_PATHS[1:]:
        p.write_bytes(pdf_bytes)

    print(f"Generated Demo Exam Paper PDF successfully at:")
    for p in OUTPUT_PATHS:
        print(f"  -> {p.resolve()}")


if __name__ == "__main__":
    generate_demo_pdf()
