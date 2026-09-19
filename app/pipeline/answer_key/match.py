import re
import uuid
from typing import Any

from pydantic import BaseModel

from app.pipeline.answer_key.normalize import map_digits_to_letters_if_applicable


def sections_match(s1: str, s2: str) -> bool:
    """Checks if two section strings match exactly or through common prefixes."""
    clean1 = s1.strip().lower()
    clean2 = s2.strip().lower()
    if clean1 == clean2:
        return True
    c1 = re.sub(
        r"^(?:section|part|खंड|खण्ड|भाग)\s*[a-z0-9\s\-:]+\s*[-:]\s*", "", clean1
    ).strip()
    c2 = re.sub(
        r"^(?:section|part|खंड|खण्ड|भाग)\s*[a-z0-9\s\-:]+\s*[-:]\s*", "", clean2
    ).strip()
    if c1 and c2 and (c1 == c2 or c1 in c2 or c2 in c1):
        return True
    return False


class MatchCandidate(BaseModel):
    source_kind: str  # "linked_document" | "answer_key" | "inline"
    document_id: uuid.UUID
    page_no: int
    section: str | None = None
    number_norm: str
    raw_answer: str
    normalized_values: list[str]
    confidence: float
    key_entry_id: uuid.UUID | None = None


class QuestionMatchResult(BaseModel):
    question_id: uuid.UUID
    answer_status: str  # "matched" | "not_found" | "ambiguous" | "conflict" | "invalid"
    answer_value: list[str] = []
    answer_raw: str | None = None
    answer_source: dict[str, Any] = {}
    answer_confidence: float | None = None
    flags_to_add: list[str] = []
    matched_entry_id: uuid.UUID | None = None


def match_question_answers(
    questions: list[dict[str, Any]],
    document_id: uuid.UUID,
    same_doc_entries: list[dict[str, Any]],
    linked_doc_entries: list[dict[str, Any]] | None = None,
) -> tuple[list[QuestionMatchResult], dict[uuid.UUID | str, str]]:
    """Matches questions with answer keys following SPEC §9 & §11 rules.

    Precedence:
    1. Linked answer key document (highest priority)
    2. Same-document answer key
    3. Inline question answer (lowest priority)

    Integrity rules:
    - Never assign answer when ambiguous or conflicting.
    - Out-of-range option -> invalid + ANSWER_OUT_OF_RANGE.
    - Missing section with duplicate numbers across sections -> ambiguous.
    """
    results: list[QuestionMatchResult] = []
    entry_match_statuses: dict[uuid.UUID | str, str] = {}

    # Count how many times each number_norm appears across the document
    question_number_counts: dict[str, int] = {}
    for q in questions:
        num = q.get("number_norm")
        if num:
            question_number_counts[num] = question_number_counts.get(num, 0) + 1

    # Map candidate answer keys:
    # 1. Linked doc entries
    linked_candidates: list[MatchCandidate] = []
    for entry in linked_doc_entries or []:
        norm_num = entry.get("number_norm")
        if norm_num:
            linked_candidates.append(
                MatchCandidate(
                    source_kind="linked_document",
                    document_id=entry.get("document_id", document_id),
                    page_no=entry.get("page_no", 1),
                    section=entry.get("section"),
                    number_norm=norm_num,
                    raw_answer=entry.get("answer_raw", ""),
                    normalized_values=entry.get("answer_value", []),
                    confidence=float(entry.get("parse_confidence", 1.0)),
                    key_entry_id=entry.get("id"),
                )
            )

    # 2. Same doc entries
    same_doc_candidates: list[MatchCandidate] = []
    for entry in same_doc_entries:
        norm_num = entry.get("number_norm")
        if norm_num:
            same_doc_candidates.append(
                MatchCandidate(
                    source_kind="answer_key",
                    document_id=document_id,
                    page_no=entry.get("page_no", 1),
                    section=entry.get("section"),
                    number_norm=norm_num,
                    raw_answer=entry.get("answer_raw", ""),
                    normalized_values=entry.get("answer_value", []),
                    confidence=float(entry.get("parse_confidence", 1.0)),
                    key_entry_id=entry.get("id"),
                )
            )

    # Track matched entry IDs so we can mark remaining ones as unmatched
    matched_entry_ids: set[uuid.UUID] = set()

    for q in questions:
        q_id = q["id"]
        q_num = q.get("number_norm")
        q_section = q.get("section")
        q_options = q.get("options", [])
        inline_raw = q.get("inline_answer_raw")

        if not q_num:
            # Question has no number -> cannot match to answer key
            results.append(
                QuestionMatchResult(
                    question_id=q_id,
                    answer_status="not_found",
                    flags_to_add=["ANSWER_NOT_FOUND"],
                )
            )
            continue

        # Find matching candidates in order of precedence:
        # Check linked doc candidates first, then same doc candidates
        def find_candidates(
            pool: list[MatchCandidate],
            target_num: str,
            target_section: str | None,
        ) -> list[MatchCandidate]:
            exact_matches: list[MatchCandidate] = []
            number_only_matches: list[MatchCandidate] = []
            for c in pool:
                if c.number_norm != target_num:
                    continue
                if c.section and target_section:
                    if sections_match(c.section, target_section):
                        exact_matches.append(c)
                    else:
                        number_only_matches.append(c)
                else:
                    number_only_matches.append(c)

            if exact_matches:
                return exact_matches
            return number_only_matches

        linked_matches = find_candidates(linked_candidates, q_num, q_section)
        same_doc_matches = find_candidates(same_doc_candidates, q_num, q_section)

        # Precedence resolution
        selected_candidates: list[MatchCandidate] = []
        is_inline = False

        if linked_matches:
            selected_candidates = linked_matches
        elif same_doc_matches:
            selected_candidates = same_doc_matches
        elif inline_raw:
            is_inline = True
        else:
            # No answer found from any source
            results.append(
                QuestionMatchResult(
                    question_id=q_id,
                    answer_status="not_found",
                    flags_to_add=["ANSWER_NOT_FOUND"],
                )
            )
            continue

        # Handle inline answer fallback
        if is_inline and inline_raw:
            inline_norm, was_mapped = map_digits_to_letters_if_applicable(
                [inline_raw.strip().upper()], q_options
            )
            inline_flags = ["ANSWER_DIGIT_MAPPED"] if was_mapped else []
            # Check MCQ options validity
            if q_options:
                valid_labels = {
                    opt.get("label", "").upper() for opt in q_options if opt.get("label")
                }
                if valid_labels and not set(inline_norm).issubset(valid_labels):
                    results.append(
                        QuestionMatchResult(
                            question_id=q_id,
                            answer_status="invalid",
                            answer_raw=inline_raw,
                            flags_to_add=["ANSWER_OUT_OF_RANGE"],
                        )
                    )
                    continue

            results.append(
                QuestionMatchResult(
                    question_id=q_id,
                    answer_status="matched",
                    answer_value=inline_norm,
                    answer_raw=inline_raw,
                    answer_source={
                        "kind": "inline",
                        "document_id": str(document_id),
                        "page": q.get("source_pages", [1])[0] if q.get("source_pages") else 1,
                    },
                    answer_confidence=0.75,
                    flags_to_add=inline_flags,
                )
            )
            continue

        # If duplicate numbers exist across sections without matching section info,
        # mark as ambiguous
        is_number_ambiguous = question_number_counts.get(q_num, 0) > 1 and any(
            c.section is None
            or not q_section
            or not sections_match(c.section, q_section)
            for c in selected_candidates
        )
        if is_number_ambiguous:
            results.append(
                QuestionMatchResult(
                    question_id=q_id,
                    answer_status="ambiguous",
                    flags_to_add=["ANSWER_AMBIGUOUS"],
                )
            )
            for c in selected_candidates:
                if c.key_entry_id:
                    entry_match_statuses[c.key_entry_id] = "ambiguous"
            continue

        # Check for conflicts within selected candidates
        unique_answers = {tuple(sorted(c.normalized_values)) for c in selected_candidates}
        if len(unique_answers) > 1:
            results.append(
                QuestionMatchResult(
                    question_id=q_id,
                    answer_status="conflict",
                    flags_to_add=["ANSWER_CONFLICT"],
                )
            )
            for c in selected_candidates:
                if c.key_entry_id:
                    entry_match_statuses[c.key_entry_id] = "conflict"
            continue

        best_candidate = selected_candidates[0]
        final_values, was_mapped = map_digits_to_letters_if_applicable(
            best_candidate.normalized_values, q_options
        )
        flags: list[str] = []
        conf = best_candidate.confidence
        if was_mapped:
            flags.append("ANSWER_DIGIT_MAPPED")
            conf = min(conf, 0.80)

        # Validate against MCQ options
        if q_options:
            valid_labels = {opt.get("label", "").upper() for opt in q_options if opt.get("label")}
            if valid_labels and not set(final_values).issubset(valid_labels):
                results.append(
                    QuestionMatchResult(
                        question_id=q_id,
                        answer_status="invalid",
                        answer_raw=best_candidate.raw_answer,
                        flags_to_add=["ANSWER_OUT_OF_RANGE"],
                        matched_entry_id=best_candidate.key_entry_id,
                    )
                )
                if best_candidate.key_entry_id:
                    entry_match_statuses[best_candidate.key_entry_id] = "invalid"
                    matched_entry_ids.add(best_candidate.key_entry_id)
                continue

        # Successfully matched
        answer_source_dict: dict[str, Any] = {
            "kind": best_candidate.source_kind,
            "document_id": str(best_candidate.document_id),
            "page": best_candidate.page_no,
        }
        if best_candidate.key_entry_id:
            answer_source_dict["entry_id"] = str(best_candidate.key_entry_id)

        results.append(
            QuestionMatchResult(
                question_id=q_id,
                answer_status="matched",
                answer_value=final_values,
                answer_raw=best_candidate.raw_answer,
                answer_source=answer_source_dict,
                answer_confidence=conf,
                flags_to_add=flags,
                matched_entry_id=best_candidate.key_entry_id,
            )
        )

        if best_candidate.key_entry_id:
            matched_entry_ids.add(best_candidate.key_entry_id)
            entry_match_statuses[best_candidate.key_entry_id] = "matched"

    # Mark remaining entries as unmatched if they weren't matched or flagged ambiguous/conflict
    for entry in same_doc_entries:
        e_id = entry.get("id")
        if e_id and e_id not in entry_match_statuses:
            entry_match_statuses[e_id] = "unmatched"

    for entry in linked_doc_entries or []:
        e_id = entry.get("id")
        if e_id and e_id not in entry_match_statuses:
            entry_match_statuses[e_id] = "unmatched"

    return results, entry_match_statuses
