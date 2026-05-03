from app.prompt_parser import get_answer


def _answer(answers, *labels):
    return get_answer(answers, *labels)


def _packet_offset(answers):
    """
    If the uploaded PDF is the larger Dr. Dan packet, the actual medical intake
    starts after the cover/waiver/privacy pages. Default to the observed packet
    offset so intake overlays do not land on cover pages.
    """
    packet = _answer(answers, "packet offset", "intake page offset")
    try:
        return int(packet)
    except (TypeError, ValueError):
        return 4


def build_dr_dan_template(answers):
    """
    Dr. Dan packet overlay template.

    Supports waiver/privacy pages and shifts the 6-page intake overlays to the
    intake section instead of writing them on the packet cover pages.
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
    city = _answer(answers, "city")
    state = _answer(answers, "state")
    zip_code = _answer(answers, "zip", "zip code")
    signature = _answer(answers, "signature", "print her name", "name")
    intake = _packet_offset(answers)

    return [
        # Waiver / consent page near bottom
        {"page": 2, "rect": [145, 540, 372, 558], "value": name},
        {"page": 2, "rect": [120, 568, 322, 586], "value": city},
        {"page": 2, "rect": [62, 596, 126, 614], "value": state},
        {"page": 2, "rect": [166, 596, 236, 614], "value": zip_code},
        {"page": 2, "rect": [292, 596, 430, 614], "value": phone},
        {"page": 2, "rect": [128, 624, 390, 642], "value": email},
        {"page": 2, "rect": [65, 650, 340, 670], "value": signature},

        # HIPAA acknowledgement page
        {"page": 3, "rect": [190, 595, 585, 615], "value": name},
        {"page": 3, "rect": [170, 627, 420, 647], "value": signature},
        {"page": 3, "rect": [478, 627, 598, 647], "value": date},

        # Intake page 1 - patient information and presenting concerns
        {"page": intake + 0, "rect": [78, 126, 168, 142], "value": date},
        {"page": intake + 0, "rect": [238, 126, 548, 142], "value": name},
        {"page": intake + 0, "rect": [100, 154, 188, 170], "value": dob},
        {"page": intake + 0, "rect": [222, 154, 286, 170], "value": height},
        {"page": intake + 0, "rect": [324, 154, 388, 170], "value": weight},
        {"page": intake + 0, "rect": [424, 154, 468, 170], "value": age},
        {"page": intake + 0, "rect": [520, 154, 586, 170], "value": gender},
        {"page": intake + 0, "rect": [145, 182, 365, 198], "value": email},
        {"page": intake + 0, "rect": [438, 182, 586, 198], "value": phone},
        {"page": intake + 0, "rect": [164, 208, 368, 224], "value": pcp},
        {"page": intake + 0, "rect": [438, 208, 586, 224], "value": _answer(answers, "referred by")},
        {"page": intake + 0, "rect": [50, 262, 565, 305], "value": _answer(answers, "history of present illness what do you hope to achieve", "what do you hope to achieve", "why i am coming in")},
        {"page": intake + 0, "rect": [50, 320, 565, 378], "value": _answer(answers, "are you experiencing a health problem now", "current diagnoses active problems", "current diagnoses / active problems")},
        {"page": intake + 0, "rect": [200, 386, 565, 410], "value": _answer(answers, "when did problems begin", "when did problem s begin")},

        # Intake page 2 - symptoms and past history
        {"page": intake + 1, "rect": [88, 38, 360, 56], "value": name},
        {"page": intake + 1, "rect": [238, 86, 565, 104], "value": _answer(answers, "symptom frequency", "how frequently do you experience symptoms")},
        {"page": intake + 1, "rect": [214, 112, 565, 130], "value": _answer(answers, "how long symptoms last", "how long do your symptoms last")},
        {"page": intake + 1, "rect": [374, 139, 565, 158], "value": _answer(answers, "pain description", "how would you describe the pain")},
        {"page": intake + 1, "rect": [208, 184, 565, 204], "value": _answer(answers, "what makes it better", "what if anything makes it better")},
        {"page": intake + 1, "rect": [208, 212, 565, 232], "value": _answer(answers, "what makes it worse", "what if anything makes it worse")},
        {"page": intake + 1, "rect": [50, 268, 565, 294], "value": _answer(answers, "current discomfort pain", "current level of discomfort pain", "symptoms i am currently dealing with")},
        {"page": intake + 1, "rect": [50, 700, 565, 750], "value": _answer(answers, "past medical history mark current or past", "past medical history")},

        # Intake page 3 - medication, allergies, treatment history, family history
        {"page": intake + 2, "rect": [88, 38, 360, 56], "value": name},
        {"page": intake + 2, "rect": [50, 88, 565, 128], "value": _answer(answers, "medications vitamins supplements herbals", "medications vitamins supplements herbal products", "current recent medications and supplements", "current / recent medications and supplements")},
        {"page": intake + 2, "rect": [184, 130, 365, 150], "value": _answer(answers, "allergies to medications", "allergies")},
        {"page": intake + 2, "rect": [444, 130, 565, 150], "value": _answer(answers, "latex allergy")},
        {"page": intake + 2, "rect": [224, 156, 565, 176], "value": _answer(answers, "food or environmental sensitivities")},
        {"page": intake + 2, "rect": [230, 184, 308, 204], "value": _answer(answers, "left or right handed")},
        {"page": intake + 2, "rect": [438, 184, 565, 204], "value": _answer(answers, "last tetanus shot", "date of last tetanus shot")},
        {"page": intake + 2, "rect": [170, 212, 282, 232], "value": _answer(answers, "last flu vaccine", "date of last flu vaccine")},
        {"page": intake + 2, "rect": [400, 212, 565, 232], "value": _answer(answers, "last covid vaccine", "date of last covid vaccine")},
        {"page": intake + 2, "rect": [190, 239, 306, 259], "value": _answer(answers, "pneumonia vaccine", "date of pneumonia vaccine")},
        {"page": intake + 2, "rect": [398, 239, 565, 259], "value": _answer(answers, "other vaccines")},
        {"page": intake + 2, "rect": [50, 286, 565, 344], "value": _answer(answers, "previous traumas surgeries illnesses hospitalizations", "surgeries procedures hospitalizations", "surgeries / procedures / hospitalizations")},
        {"page": intake + 2, "rect": [144, 378, 565, 398], "value": _answer(answers, "physical therapy")},
        {"page": intake + 2, "rect": [144, 403, 565, 423], "value": _answer(answers, "massage therapy")},
        {"page": intake + 2, "rect": [144, 428, 565, 448], "value": _answer(answers, "acupuncture")},
        {"page": intake + 2, "rect": [144, 453, 565, 473], "value": _answer(answers, "chiropractic")},
        {"page": intake + 2, "rect": [184, 478, 565, 498], "value": _answer(answers, "nutritional counseling")},
        {"page": intake + 2, "rect": [184, 503, 565, 523], "value": _answer(answers, "mental health counseling")},
        {"page": intake + 2, "rect": [50, 552, 565, 630], "value": _answer(answers, "women only reproductive history", "reproductive history")},
        {"page": intake + 2, "rect": [50, 682, 565, 758], "value": _answer(answers, "family history")},

        # Intake page 4 - social history, function, occupation, signature
        {"page": intake + 3, "rect": [88, 38, 360, 56], "value": name},
        {"page": intake + 3, "rect": [50, 82, 565, 130], "value": _answer(answers, "primary language", "highest education", "exercise")},
        {"page": intake + 3, "rect": [144, 136, 565, 156], "value": _answer(answers, "how do you relax")},
        {"page": intake + 3, "rect": [144, 162, 565, 182], "value": _answer(answers, "what brings you joy")},
        {"page": intake + 3, "rect": [254, 189, 565, 209], "value": _answer(answers, "meditation relaxation techniques")},
        {"page": intake + 3, "rect": [234, 216, 565, 236], "value": _answer(answers, "current emotional or life stress")},
        {"page": intake + 3, "rect": [114, 244, 565, 264], "value": _answer(answers, "hobbies")},
        {"page": intake + 3, "rect": [280, 272, 565, 292], "value": _answer(answers, "cultural or spiritual needs")},
        {"page": intake + 3, "rect": [170, 326, 565, 346], "value": _answer(answers, "assistive device")},
        {"page": intake + 3, "rect": [238, 354, 565, 374], "value": _answer(answers, "assistance with activities of daily living")},
        {"page": intake + 3, "rect": [230, 382, 565, 402], "value": _answer(answers, "live alone")},
        {"page": intake + 3, "rect": [50, 468, 565, 548], "value": _answer(answers, "describe", "presently have", "symptoms i am currently dealing with")},
        {"page": intake + 3, "rect": [50, 578, 565, 678], "value": _answer(answers, "occupational history", "social history")},
        {"page": intake + 3, "rect": [228, 700, 565, 720], "value": _answer(answers, "advanced directives")},
        {"page": intake + 3, "rect": [234, 728, 405, 748], "value": _answer(answers, "this patient history was completed by")},
        {"page": intake + 3, "rect": [88, 752, 318, 772], "value": signature},
        {"page": intake + 3, "rect": [458, 752, 565, 772], "value": date},

        # Intake page 5 - dental history
        {"page": intake + 4, "rect": [88, 38, 360, 56], "value": name},
        {"page": intake + 4, "rect": [50, 86, 565, 746], "value": _answer(answers, "page 5 dental history", "dental history", "other dental history")},

        # Intake page 6 - scars / marks
        {"page": intake + 5, "rect": [88, 38, 360, 56], "value": name},
        {"page": intake + 5, "rect": [70, 150, 565, 172], "value": _answer(answers, "scar 1", "1")},
        {"page": intake + 5, "rect": [70, 185, 565, 207], "value": _answer(answers, "scar 2", "2")},
        {"page": intake + 5, "rect": [70, 220, 565, 242], "value": _answer(answers, "scar 3", "3")},
        {"page": intake + 5, "rect": [70, 255, 565, 277], "value": _answer(answers, "scar 4", "4")},
        {"page": intake + 5, "rect": [70, 290, 565, 312], "value": _answer(answers, "scar 5", "5")},
        {"page": intake + 5, "rect": [70, 325, 565, 347], "value": _answer(answers, "scar 6", "6")},
        {"page": intake + 5, "rect": [70, 360, 565, 382], "value": _answer(answers, "scar 7", "7")},
        {"page": intake + 5, "rect": [70, 395, 565, 417], "value": _answer(answers, "scar 8", "8")},
        {"page": intake + 5, "rect": [70, 430, 565, 452], "value": _answer(answers, "scar 9", "9")},
        {"page": intake + 5, "rect": [70, 465, 565, 487], "value": _answer(answers, "scar 10", "10")},
    ]
