import re
from typing import Dict

UNKNOWN_VALUE = "Not documented in source records"


def clean_answer(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"\s+", " ", value)
    value = value.replace("VERIFY", UNKNOWN_VALUE)
    return value or UNKNOWN_VALUE


def normalize_key(label: str) -> str:
    label = (label or "").lower().strip()
    label = re.sub(r"[^a-z0-9]+", "_", label)
    label = re.sub(r"_+", "_", label).strip("_")
    return label


def parse_label_answer_prompt(prompt_text: str) -> Dict[str, str]:
    """
    Deterministic parser for AI/source answer prompts.

    Supports:
      FIELD LABEL:
      answer text

      FIELD LABEL: answer text

      1. answer text
      Scar 1: answer text

    It does not infer missing facts; missing fields fall back to UNKNOWN_VALUE.
    """
    answers: Dict[str, str] = {}
    lines = (prompt_text or "").splitlines()
    current_label = None
    buffer = []

    def flush():
        nonlocal current_label, buffer
        if current_label:
            answers[normalize_key(current_label)] = clean_answer(" ".join(buffer))
        current_label = None
        buffer = []

    numbered_re = re.compile(r"^(?:scar\s*)?(\d{1,2})[\.)]\s*(.+)$", re.IGNORECASE)
    inline_label_re = re.compile(r"^([A-Za-z0-9][A-Za-z0-9 /&().,'\-]{0,90}?):\s*(.*)$")

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        numbered = numbered_re.match(line)
        if numbered:
            flush()
            answers[normalize_key(numbered.group(1))] = clean_answer(numbered.group(2))
            answers[normalize_key(f"scar {numbered.group(1)}")] = clean_answer(numbered.group(2))
            continue

        inline = inline_label_re.match(line)
        if inline:
            flush()
            label = inline.group(1).strip()
            value = inline.group(2).strip()
            if value:
                answers[normalize_key(label)] = clean_answer(value)
            else:
                current_label = label
                buffer = []
            continue

        if line.endswith(":") and len(line) <= 90:
            flush()
            current_label = line[:-1].strip()
            buffer = []
        elif current_label:
            buffer.append(line)

    flush()
    return answers


def get_answer(answers: Dict[str, str], *candidate_labels: str) -> str:
    for label in candidate_labels:
        key = normalize_key(label)
        if key in answers and answers[key]:
            return clean_answer(answers[key])
    return UNKNOWN_VALUE
