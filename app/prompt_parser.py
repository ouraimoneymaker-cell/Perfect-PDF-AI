import re
from typing import Dict

UNKNOWN_VALUE = "Not documented in source records"


def clean_answer(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"\s+", " ", value)
    value = value.replace("VERIFY", UNKNOWN_VALUE)
    return value


def parse_label_answer_prompt(prompt_text: str) -> Dict[str, str]:
    """
    Deterministic parser for AI-generated answer prompts.

    Expected style:
        FIELD LABEL:
        answer text

    This intentionally avoids guessing. It only extracts explicit label/value pairs.
    Missing labels are not invented. If a label is not found, the caller receives a blank string.
    If the prompt explicitly says "Not documented in source records", that exact value is preserved.
    """
    answers: Dict[str, str] = {}
    lines = (prompt_text or "").splitlines()
    current_label = None
    buffer = []

    def flush():
        nonlocal current_label, buffer
        if current_label:
            value = clean_answer(" ".join(buffer))
            if value:
                answers[normalize_key(current_label)] = value
        current_label = None
        buffer = []

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        if line.endswith(":") and len(line) <= 90:
            flush()
            current_label = line[:-1].strip()
            buffer = []
        elif current_label:
            buffer.append(line)

    flush()
    return answers


def normalize_key(label: str) -> str:
    label = (label or "").lower().strip()
    label = re.sub(r"[^a-z0-9]+", "_", label)
    label = re.sub(r"_+", "_", label).strip("_")
    return label


def get_answer(answers: Dict[str, str], *candidate_labels: str) -> str:
    for label in candidate_labels:
        key = normalize_key(label)
        if key in answers and answers[key]:
            return clean_answer(answers[key])
    return ""
