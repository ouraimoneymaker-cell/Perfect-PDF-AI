import re
from typing import Dict

UNKNOWN_VALUE = "Not documented in source records"

_BLOCKED_HEADING_KEYS = {
    "mission",
    "absolute_source_truth_rules",
    "pixel_level_pdf_filling_rules",
    "current_patient_identity_and_demographics",
    "user_provided_current_update_that_must_be_reflected",
    "patient_style_narrative_answers_for_page_1_medical_form",
    "symptoms_and_pain_section",
    "past_medical_history_condition_list_mark_current_past_only_when_documented",
    "current_medications_vitamins_supplements_herbal_products",
}

_REAL_INLINE_PREFIXES = (
    "date",
    "name",
    "dob",
    "date of birth",
    "height",
    "weight",
    "age",
    "gender",
    "email",
    "cell phone",
    "phone",
    "primary care physician",
    "referred by",
    "history of present illness",
    "what do you hope",
    "are you experiencing",
    "when did",
    "symptom",
    "how frequently",
    "how long",
    "pain",
    "what makes",
    "current discomfort",
    "past medical history",
    "medications",
    "allergies",
    "latex",
    "food or environmental",
    "left or right",
    "tetanus",
    "flu",
    "covid",
    "pneumonia",
    "other vaccines",
    "previous traumas",
    "physical therapy",
    "massage therapy",
    "acupuncture",
    "chiropractic",
    "nutritional counseling",
    "mental health counseling",
    "women only",
    "reproductive",
    "family history",
    "mother",
    "father",
    "brother",
    "sister",
    "partner",
    "spouse",
    "children",
    "primary language",
    "highest education",
    "exercise",
    "how do you relax",
    "what brings",
    "meditation",
    "current emotional",
    "hobbies",
    "cultural",
    "learn best",
    "assistive",
    "assistance",
    "live alone",
    "smoke",
    "alcohol",
    "recreational",
    "healthy eating",
    "caffeine",
    "specific diet",
    "presently have",
    "describe",
    "occupational",
    "advanced directives",
    "signature",
    "dental",
    "scar",
)


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


def _is_blocked_heading(label: str, value: str = "") -> bool:
    key = normalize_key(label)
    if key in _BLOCKED_HEADING_KEYS:
        return True
    if key.isdigit() and value and not value[:1].isdigit():
        return True
    return False


def _is_real_label(label: str) -> bool:
    label_l = (label or "").strip().lower()
    key = normalize_key(label_l)
    if not label_l or key in _BLOCKED_HEADING_KEYS:
        return False
    if key.isdigit():
        return False
    return label_l.startswith(_REAL_INLINE_PREFIXES)


def parse_label_answer_prompt(prompt_text: str) -> Dict[str, str]:
    """
    Parse explicit form-answer prompts while ignoring instruction headings.
    """
    answers: Dict[str, str] = {}
    lines = (prompt_text or "").splitlines()
    current_label = None
    buffer = []

    def flush():
        nonlocal current_label, buffer
        if current_label and _is_real_label(current_label):
            value = clean_answer(" ".join(buffer))
            if value:
                answers[normalize_key(current_label)] = value
        current_label = None
        buffer = []

    numbered_re = re.compile(r"^scar\s*(\d{1,2})\s*[:\.)]\s*(.+)$", re.IGNORECASE)
    inline_label_re = re.compile(r"^([A-Za-z0-9][A-Za-z0-9 /&().,'\-]{0,90}?):\s*(.*)$")

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        numbered = numbered_re.match(line)
        if numbered:
            flush()
            value = clean_answer(numbered.group(2))
            answers[normalize_key(numbered.group(1))] = value
            answers[normalize_key(f"scar {numbered.group(1)}")] = value
            continue

        inline = inline_label_re.match(line)
        if inline:
            flush()
            label = inline.group(1).strip()
            value = inline.group(2).strip()
            if _is_blocked_heading(label, value) or not _is_real_label(label):
                current_label = None
                buffer = []
                continue
            if value:
                answers[normalize_key(label)] = clean_answer(value)
            else:
                current_label = label
                buffer = []
            continue

        if line.endswith(":") and len(line) <= 90:
            flush()
            label = line[:-1].strip()
            if _is_real_label(label):
                current_label = label
                buffer = []
            else:
                current_label = None
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
