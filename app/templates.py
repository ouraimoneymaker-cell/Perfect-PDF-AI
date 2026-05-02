from app.prompt_parser import get_answer


def build_dr_dan_template(answers):
    """
    First expanded Dr. Dan intake template.
    Coordinates are PDF points and intentionally conservative.
    This is template-assisted filling: exact coordinates can be refined from visual output.
    """
    return [
        # Page 1 - demographics and presenting concerns
        {"page": 0, "rect": [85, 132, 170, 146], "value": get_answer(answers, "date")},
        {"page": 0, "rect": [245, 132, 520, 146], "value": get_answer(answers, "name", "name last first mi")},
        {"page": 0, "rect": [105, 160, 185, 174], "value": get_answer(answers, "date of birth", "dob")},
        {"page": 0, "rect": [230, 160, 280, 174], "value": get_answer(answers, "height")},
        {"page": 0, "rect": [330, 160, 385, 174], "value": get_answer(answers, "weight")},
        {"page": 0, "rect": [430, 160, 465, 174], "value": get_answer(answers, "age")},
        {"page": 0, "rect": [525, 160, 585, 174], "value": get_answer(answers, "gender")},
        {"page": 0, "rect": [150, 188, 360, 202], "value": get_answer(answers, "email address", "email")},
        {"page": 0, "rect": [445, 188, 585, 202], "value": get_answer(answers, "cell phone", "phone")},
        {"page": 0, "rect": [170, 214, 360, 228], "value": get_answer(answers, "primary care physician")},
        {"page": 0, "rect": [445, 214, 585, 228], "value": get_answer(answers, "referred by")},
        {"page": 0, "rect": [55, 270, 560, 302], "value": get_answer(answers, "history of present illness what do you hope to achieve", "what do you hope to achieve")},
        {"page": 0, "rect": [55, 325, 560, 372], "value": get_answer(answers, "are you experiencing a health problem now")},
        {"page": 0, "rect": [205, 392, 560, 410], "value": get_answer(answers, "when did problems begin", "when did problem s begin")},

        # Page 2 - symptoms and past history narrative support
        {"page": 1, "rect": [95, 45, 360, 60], "value": get_answer(answers, "name")},
        {"page": 1, "rect": [245, 92, 560, 108], "value": get_answer(answers, "symptom frequency", "how frequently do you experience symptoms")},
        {"page": 1, "rect": [220, 118, 560, 134], "value": get_answer(answers, "how long symptoms last", "how long do your symptoms last")},
        {"page": 1, "rect": [380, 145, 560, 162], "value": get_answer(answers, "pain description", "how would you describe the pain")},
        {"page": 1, "rect": [215, 190, 560, 207], "value": get_answer(answers, "what makes it better", "what if anything makes it better")},
        {"page": 1, "rect": [215, 218, 560, 235], "value": get_answer(answers, "what makes it worse", "what if anything makes it worse")},
        {"page": 1, "rect": [55, 275, 560, 292], "value": get_answer(answers, "current discomfort pain", "current level of discomfort pain")},
        {"page": 1, "rect": [55, 710, 560, 742], "value": get_answer(answers, "past medical history mark current or past", "past medical history")},

        # Page 3 - meds, allergies, vaccines, therapies, family
        {"page": 2, "rect": [95, 45, 360, 60], "value": get_answer(answers, "name")},
        {"page": 2, "rect": [55, 95, 560, 125], "value": get_answer(answers, "medications vitamins supplements herbals", "medications vitamins supplements herbal products")},
        {"page": 2, "rect": [190, 135, 360, 151], "value": get_answer(answers, "allergies to medications")},
        {"page": 2, "rect": [450, 135, 560, 151], "value": get_answer(answers, "latex allergy")},
        {"page": 2, "rect": [230, 162, 560, 178], "value": get_answer(answers, "food or environmental sensitivities")},
        {"page": 2, "rect": [235, 190, 305, 206], "value": get_answer(answers, "left or right handed")},
        {"page": 2, "rect": [445, 190, 560, 206], "value": get_answer(answers, "last tetanus shot", "date of last tetanus shot")},
        {"page": 2, "rect": [175, 218, 280, 234], "value": get_answer(answers, "last flu vaccine", "date of last flu vaccine")},
        {"page": 2, "rect": [405, 218, 560, 234], "value": get_answer(answers, "last covid vaccine", "date of last covid vaccine")},
        {"page": 2, "rect": [195, 245, 300, 261], "value": get_answer(answers, "pneumonia vaccine", "date of pneumonia vaccine")},
        {"page": 2, "rect": [405, 245, 560, 261], "value": get_answer(answers, "other vaccines")},
        {"page": 2, "rect": [55, 292, 560, 338], "value": get_answer(answers, "previous traumas surgeries illnesses hospitalizations")},
        {"page": 2, "rect": [150, 385, 560, 400], "value": get_answer(answers, "physical therapy")},
        {"page": 2, "rect": [150, 410, 560, 425], "value": get_answer(answers, "massage therapy")},
        {"page": 2, "rect": [150, 435, 560, 450], "value": get_answer(answers, "acupuncture")},
        {"page": 2, "rect": [150, 460, 560, 475], "value": get_answer(answers, "chiropractic")},
        {"page": 2, "rect": [190, 485, 560, 500], "value": get_answer(answers, "nutritional counseling")},
        {"page": 2, "rect": [190, 510, 560, 525], "value": get_answer(answers, "mental health counseling")},
        {"page": 2, "rect": [55, 560, 560, 625], "value": get_answer(answers, "women only reproductive history", "reproductive history")},
        {"page": 2, "rect": [55, 690, 560, 760], "value": get_answer(answers, "family history")},

        # Page 4 - social, occupation, signature
        {"page": 3, "rect": [95, 45, 360, 60], "value": get_answer(answers, "name")},
        {"page": 3, "rect": [55, 88, 560, 128], "value": get_answer(answers, "primary language", "highest education", "exercise")},
        {"page": 3, "rect": [150, 142, 560, 157], "value": get_answer(answers, "how do you relax")},
        {"page": 3, "rect": [150, 168, 560, 183], "value": get_answer(answers, "what brings you joy")},
        {"page": 3, "rect": [260, 195, 560, 210], "value": get_answer(answers, "meditation relaxation techniques")},
        {"page": 3, "rect": [240, 222, 560, 238], "value": get_answer(answers, "current emotional or life stress")},
        {"page": 3, "rect": [120, 250, 560, 265], "value": get_answer(answers, "hobbies")},
        {"page": 3, "rect": [285, 278, 560, 294], "value": get_answer(answers, "cultural or spiritual needs")},
        {"page": 3, "rect": [175, 332, 560, 348], "value": get_answer(answers, "assistive device")},
        {"page": 3, "rect": [245, 360, 560, 376], "value": get_answer(answers, "assistance with activities of daily living")},
        {"page": 3, "rect": [235, 388, 560, 404], "value": get_answer(answers, "live alone")},
        {"page": 3, "rect": [55, 475, 560, 545], "value": get_answer(answers, "describe", "presently have")},
        {"page": 3, "rect": [55, 585, 560, 675], "value": get_answer(answers, "occupational history")},
        {"page": 3, "rect": [235, 705, 560, 720], "value": get_answer(answers, "advanced directives")},
        {"page": 3, "rect": [240, 735, 400, 750], "value": get_answer(answers, "this patient history was completed by")},
        {"page": 3, "rect": [95, 760, 300, 775], "value": get_answer(answers, "signature")},
        {"page": 3, "rect": [465, 760, 560, 775], "value": get_answer(answers, "date")},

        # Page 5 dental
        {"page": 4, "rect": [95, 45, 360, 60], "value": get_answer(answers, "name")},
        {"page": 4, "rect": [55, 92, 560, 742], "value": get_answer(answers, "page 5 dental history", "dental history", "other dental history")},

        # Page 6 scars
        {"page": 5, "rect": [95, 45, 360, 60], "value": get_answer(answers, "name")},
        {"page": 5, "rect": [75, 155, 560, 175], "value": get_answer(answers, "scar 1", "1")},
        {"page": 5, "rect": [75, 190, 560, 210], "value": get_answer(answers, "scar 2", "2")},
        {"page": 5, "rect": [75, 225, 560, 245], "value": get_answer(answers, "scar 3", "3")},
        {"page": 5, "rect": [75, 260, 560, 280], "value": get_answer(answers, "scar 4", "4")},
        {"page": 5, "rect": [75, 295, 560, 315], "value": get_answer(answers, "scar 5", "5")},
        {"page": 5, "rect": [75, 330, 560, 350], "value": get_answer(answers, "scar 6", "6")},
        {"page": 5, "rect": [75, 365, 560, 385], "value": get_answer(answers, "scar 7", "7")},
        {"page": 5, "rect": [75, 400, 560, 420], "value": get_answer(answers, "scar 8", "8")},
        {"page": 5, "rect": [75, 435, 560, 455], "value": get_answer(answers, "scar 9", "9")},
        {"page": 5, "rect": [75, 470, 560, 490], "value": get_answer(answers, "scar 10", "10")},
    ]
