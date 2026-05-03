from app.prompt_parser import get_answer


def _answer(answers, *labels):
    return get_answer(answers, *labels)


def build_dr_dan_template(answers):
    """
    Dr. Dan intake form overlay template.

    This template is intentionally limited to the fillable intake packet pages.
    It leaves unknown fields blank through prompt_parser.get_answer behavior
    and avoids spraying fallback text across the form.
    """
    name = _answer(answers, "name", "full name", "patient name", "name last first mi")
    date = _answer(answers, "date", "today's date", "today date")
    dob = _answer(answers, "date of birth", "dob")
    height = _answer(answers, "height")
    weight = _answer(answers, "weight")
    age = _answer(answers, "age")
    gender = _answer(answers, "gender", "sex")
    phone = _answer(answers, "cell phone", "phone", "phone in records")
    email = _answer(answers, "email", "email address")
    pcp = _answer(answers, "primary care physician", "primary care doctor", "pcp")

    return [
        # Page 1 - patient information and presenting concerns
        {"page": 0, "rect": [78, 126, 168, 142], "value": date},
        {"page": 0, "rect": [238, 126, 548, 142], "value": name},
        {"page": 0, "rect": [100, 154, 188, 170], "value": dob},
        {"page": 0, "rect": [222, 154, 286, 170], "value": height},
        {"page": 0, "rect": [324, 154, 388, 170], "value": weight},
        {"page": 0, "rect": [424, 154, 468, 170], "value": age},
        {"page": 0, "rect": [520, 154, 586, 170], "value": gender},
        {"page": 0, "rect": [145, 182, 365, 198], "value": email},
        {"page": 0, "rect": [438, 182, 586, 198], "value": phone},
        {"page": 0, "rect": [164, 208, 368, 224], "value": pcp},
        {"page": 0, "rect": [438, 208, 586, 224], "value": _answer(answers, "referred by")},
        {"page": 0, "rect": [50, 262, 565, 305], "value": _answer(answers, "history of present illness what do you hope to achieve", "what do you hope to achieve", "why i am coming in")},
        {"page": 0, "rect": [50, 320, 565, 378], "value": _answer(answers, "are you experiencing a health problem now", "current diagnoses active problems", "current diagnoses / active problems")},
        {"page": 0, "rect": [200, 386, 565, 410], "value": _answer(answers, "when did problems begin", "when did problem s begin")},

        # Page 2 - symptoms and past history
        {"page": 1, "rect": [88, 38, 360, 56], "value": name},
        {"page": 1, "rect": [238, 86, 565, 104], "value": _answer(answers, "symptom frequency", "how frequently do you experience symptoms")},
        {"page": 1, "rect": [214, 112, 565, 130], "value": _answer(answers, "how long symptoms last", "how long do your symptoms last")},
        {"page": 1, "rect": [374, 139, 565, 158], "value": _answer(answers, "pain description", "how would you describe the pain")},
        {"page": 1, "rect": [208, 184, 565, 204], "value": _answer(answers, "what makes it better", "what if anything makes it better")},
        {"page": 1, "rect": [208, 212, 565, 232], "value": _answer(answers, "what makes it worse", "what if anything makes it worse")},
        {"page": 1, "rect": [50, 268, 565, 294], "value": _answer(answers, "current discomfort pain", "current level of discomfort pain", "symptoms i am currently dealing with")},
        {"page": 1, "rect": [50, 700, 565, 750], "value": _answer(answers, "past medical history mark current or past", "past medical history")},

        # Page 3 - medication, allergies, treatment history, family history
        {"page": 2, "rect": [88, 38, 360, 56], "value": name},
        {"page": 2, "rect": [50, 88, 565, 128], "value": _answer(answers, "medications vitamins supplements herbals", "medications vitamins supplements herbal products", "current recent medications and supplements", "current / recent medications and supplements")},
        {"page": 2, "rect": [184, 130, 365, 150], "value": _answer(answers, "allergies to medications", "allergies")},
        {"page": 2, "rect": [444, 130, 565, 150], "value": _answer(answers, "latex allergy")},
        {"page": 2, "rect": [224, 156, 565, 176], "value": _answer(answers, "food or environmental sensitivities")},
        {"page": 2, "rect": [230, 184, 308, 204], "value": _answer(answers, "left or right handed")},
        {"page": 2, "rect": [438, 184, 565, 204], "value": _answer(answers, "last tetanus shot", "date of last tetanus shot")},
        {"page": 2, "rect": [170, 212, 282, 232], "value": _answer(answers, "last flu vaccine", "date of last flu vaccine")},
        {"page": 2, "rect": [400, 212, 565, 232], "value": _answer(answers, "last covid vaccine", "date of last covid vaccine")},
        {"page": 2, "rect": [190, 239, 306, 259], "value": _answer(answers, "pneumonia vaccine", "date of pneumonia vaccine")},
        {"page": 2, "rect": [398, 239, 565, 259], "value": _answer(answers, "other vaccines")},
        {"page": 2, "rect": [50, 286, 565, 344], "value": _answer(answers, "previous traumas surgeries illnesses hospitalizations", "surgeries procedures hospitalizations", "surgeries / procedures / hospitalizations")},
        {"page": 2, "rect": [144, 378, 565, 398], "value": _answer(answers, "physical therapy")},
        {"page": 2, "rect": [144, 403, 565, 423], "value": _answer(answers, "massage therapy")},
        {"page": 2, "rect": [144, 428, 565, 448], "value": _answer(answers, "acupuncture")},
        {"page": 2, "rect": [144, 453, 565, 473], "value": _answer(answers, "chiropractic")},
        {"page": 2, "rect": [184, 478, 565, 498], "value": _answer(answers, "nutritional counseling")},
        {"page": 2, "rect": [184, 503, 565, 523], "value": _answer(answers, "mental health counseling")},
        {"page": 2, "rect": [50, 552, 565, 630], "value": _answer(answers, "women only reproductive history", "reproductive history")},
        {"page": 2, "rect": [50, 682, 565, 758], "value": _answer(answers, "family history")},

        # Page 4 - social history, function, occupation, signature
        {"page": 3, "rect": [88, 38, 360, 56], "value": name},
        {"page": 3, "rect": [50, 82, 565, 130], "value": _answer(answers, "primary language", "highest education", "exercise")},
        {"page": 3, "rect": [144, 136, 565, 156], "value": _answer(answers, "how do you relax")},
        {"page": 3, "rect": [144, 162, 565, 182], "value": _answer(answers, "what brings you joy")},
        {"page": 3, "rect": [254, 189, 565, 209], "value": _answer(answers, "meditation relaxation techniques")},
        {"page": 3, "rect": [234, 216, 565, 236], "value": _answer(answers, "current emotional or life stress")},
        {"page": 3, "rect": [114, 244, 565, 264], "value": _answer(answers, "hobbies")},
        {"page": 3, "rect": [280, 272, 565, 292], "value": _answer(answers, "cultural or spiritual needs")},
        {"page": 3, "rect": [170, 326, 565, 346], "value": _answer(answers, "assistive device")},
        {"page": 3, "rect": [238, 354, 565, 374], "value": _answer(answers, "assistance with activities of daily living")},
        {"page": 3, "rect": [230, 382, 565, 402], "value": _answer(answers, "live alone")},
        {"page": 3, "rect": [50, 468, 565, 548], "value": _answer(answers, "describe", "presently have", "symptoms i am currently dealing with")},
        {"page": 3, "rect": [50, 578, 565, 678], "value": _answer(answers, "occupational history", "social history")},
        {"page": 3, "rect": [228, 700, 565, 720], "value": _answer(answers, "advanced directives")},
        {"page": 3, "rect": [234, 728, 405, 748], "value": _answer(answers, "this patient history was completed by")},
        {"page": 3, "rect": [88, 752, 318, 772], "value": _answer(answers, "signature", "print her name", "name")},
        {"page": 3, "rect": [458, 752, 565, 772], "value": date},

        # Page 5 - dental history
        {"page": 4, "rect": [88, 38, 360, 56], "value": name},
        {"page": 4, "rect": [50, 86, 565, 746], "value": _answer(answers, "page 5 dental history", "dental history", "other dental history")},

        # Page 6 - scars / marks
        {"page": 5, "rect": [88, 38, 360, 56], "value": name},
        {"page": 5, "rect": [70, 150, 565, 172], "value": _answer(answers, "scar 1", "1")},
        {"page": 5, "rect": [70, 185, 565, 207], "value": _answer(answers, "scar 2", "2")},
        {"page": 5, "rect": [70, 220, 565, 242], "value": _answer(answers, "scar 3", "3")},
        {"page": 5, "rect": [70, 255, 565, 277], "value": _answer(answers, "scar 4", "4")},
        {"page": 5, "rect": [70, 290, 565, 312], "value": _answer(answers, "scar 5", "5")},
        {"page": 5, "rect": [70, 325, 565, 347], "value": _answer(answers, "scar 6", "6")},
        {"page": 5, "rect": [70, 360, 565, 382], "value": _answer(answers, "scar 7", "7")},
        {"page": 5, "rect": [70, 395, 565, 417], "value": _answer(answers, "scar 8", "8")},
        {"page": 5, "rect": [70, 430, 565, 452], "value": _answer(answers, "scar 9", "9")},
        {"page": 5, "rect": [70, 465, 565, 487], "value": _answer(answers, "scar 10", "10")},
    ]
