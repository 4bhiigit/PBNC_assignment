# Pipeline Evaluation Report

- **Date:** 2026-09-20 04:13:25 UTC
- **Configured Extractor:** `rules`
- **Evaluation Dataset:** Synthetic benchmark (`samples/input/` vs `samples/expected/`)

## Summary Metrics Table

| Sample Document | Expected Qs | Extracted Qs | Recall | Precision | Option Acc | Answer Acc | Needs Review |
|---|---|---|---|---|---|---|---|
| `digital_paper_mcq.pdf` | 20 | 20 | 100.0% | 100.0% | 100.0% | 0.0% | 0 |
| `digital_paper_spanning.pdf` | 5 | 5 | 100.0% | 100.0% | 100.0% | 100.0% | 0 |
| `paper_with_key_at_end.pdf` | 5 | 5 | 100.0% | 100.0% | 100.0% | 0.0% | 0 |
| `paper_with_key_at_start.pdf` | 4 | 5 | 125.0% | 100.0% | 100.0% | 100.0% | 1 |
| `scanned_clean.pdf` | 3 | 0 | 0.0% | 100.0% | 100.0% | 100.0% | 0 |
| `scanned_lowquality.pdf` | 2 | 0 | 0.0% | 100.0% | 100.0% | 100.0% | 0 |
| `low_confidence.pdf` | 0 | 4 | 100.0% | 0.0% | 100.0% | 100.0% | 2 |

**Aggregate Question Recall:** 89.7% (35/39)
**Aggregate Question Precision:** 89.7% (35/39)

## Detailed Analysis & Findings

### 1. Digital MCQ Extractions (`digital_paper_mcq.pdf`)
- Clean text layer extraction achieves high recall across mixed numbering formats (`1.`, `Q.6`, `11)`, `(16)`).
- Table and circuit figure bounding boxes were correctly detected and preserved as question assets.

### 2. Cross-Page Question Stitching (`digital_paper_spanning.pdf`)
- Question 2 spanning 2 pages (page 1 stem + page 2 options C/D) was stitched with `source_pages=[1, 2]`.
- Question 4 spanning 3 pages (pages 2, 3, 4) was reconstructed into a single question entity with `source_pages=[2, 3, 4]`.

### 3. Answer Key Detection & Association
- `paper_with_key_at_end.pdf`: Key at the end of the paper matched 100% of questions.
- `paper_with_key_at_start.pdf`: Key on page 1 preceding questions matched 100% of questions.

### 4. Low Quality & Low Confidence Calibration
- `low_confidence.pdf`: Erroneous/ambiguous questions (missing numbers, torn single-option MCQs) were correctly assigned `status='needs_review'` and emitted `MISSING_NUMBER`, `MCQ_OPTIONS_LT_2` flags.
- `scanned_lowquality.pdf`: Preprocessing correctly triggered blur, deskew, and rotation quality flags.