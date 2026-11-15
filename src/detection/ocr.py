import os
import cv2
import re
from difflib import SequenceMatcher
from paddleocr import PaddleOCR

csv_path = os.path.join("output", "ocr_results", "plate_results.csv")

PROVINCE_DICTIONARY = {
    "Sindh": ["SINDH", "SIND"],
    "Punjab": ["PUNJAB", "PANJAB"],
    "Balochistan": ["BALOCHISTAN", "BALUCHISTAN", "BALOCH"],
    "KPK / Khyber Pakhtunkhwa": ["KPK", "KHYBER PAKHTUNKHWA", "KHYBER", "PAKHTUNKHWA", "NWFP"],
    "Islamabad": ["ISLAMABAD", "ICT", "ISB"],
}

EXCLUSIONS = {"YAMAHA", "HONDA", "PAKISTAN"}


def detect_province(raw_lines):
    if not raw_lines:
        return None

    exact_candidates = []
    fuzzy_tokens = []

    for line in raw_lines:
        if not line or not isinstance(line, str):
            continue

        norm = line.upper()
        norm = re.sub(r"[\-_\./\\,;:|]", " ", norm)
        norm = re.sub(r"\s+", " ", norm).strip()
        if not norm:
            continue

        if norm not in EXCLUSIONS:
            exact_candidates.append(norm)
            collapsed = re.sub(r"\s+", "", norm)
            if collapsed != norm and collapsed not in EXCLUSIONS:
                exact_candidates.append(collapsed)

        words = norm.split(" ")
        for w in words:
            w_clean = re.sub(r"[^A-Z0-9]", "", w)
            if not w_clean or w_clean in EXCLUSIONS:
                continue
            if w_clean not in exact_candidates:
                exact_candidates.append(w_clean)
            if len(w_clean) >= 4:
                fuzzy_tokens.append(w_clean)

    for cand in exact_candidates:
        for province, aliases in PROVINCE_DICTIONARY.items():
            for alias in aliases:
                if cand == alias:
                    return province

    province_best_scores = {}
    for token in fuzzy_tokens:
        for province, aliases in PROVINCE_DICTIONARY.items():
            for alias in aliases:
                if len(alias) < 4:
                    continue
                score = SequenceMatcher(None, token, alias).ratio()
                if score >= 0.85:
                    if province not in province_best_scores or score > province_best_scores[province]:
                        province_best_scores[province] = score

    if not province_best_scores:
        return None

    sorted_scores = sorted(province_best_scores.items(), key=lambda item: item[1], reverse=True)
    top_province, top_score = sorted_scores[0]

    if len(sorted_scores) > 1:
        _, second_score = sorted_scores[1]
        if (top_score - second_score) <= 0.03:
            return None

    return top_province

# -----------------------------------
# LOAD OCR MODEL
# -----------------------------------

print("Loading PaddleOCR...")

reader = PaddleOCR(lang="en")

print("PaddleOCR loaded successfully.\n")


# -----------------------------------
# CLEAN TEXT
# -----------------------------------

def clean_plate_text(text):

    text = text.upper()

    text = re.sub(
        r"[^A-Z0-9]",
        "",
        text
    )

    return text


def remove_province_from_plate(plate_number, province, raw_lines=None):
    if not plate_number or not province:
        return plate_number

    aliases = list(PROVINCE_DICTIONARY.get(province, []))
    province_words = re.findall(r"[A-Z0-9]+", province.upper())
    for pw in province_words:
        if pw not in EXCLUSIONS and pw not in aliases:
            aliases.append(pw)

    tokens_to_remove = set()
    for alias in aliases:
        clean_alias = re.sub(r"[^A-Z0-9]", "", alias.upper())
        if clean_alias and clean_alias not in EXCLUSIONS and len(clean_alias) >= 3:
            tokens_to_remove.add(clean_alias)

    if raw_lines:
        for line in raw_lines:
            if not line or not isinstance(line, str):
                continue
            norm = line.upper()
            norm = re.sub(r"[\-_\./\\,;:|]", " ", norm)
            words = norm.split(" ")
            for w in words:
                w_clean = re.sub(r"[^A-Z0-9]", "", w)
                if not w_clean or w_clean in EXCLUSIONS:
                    continue
                if w_clean in tokens_to_remove:
                    continue
                if len(w_clean) >= 4:
                    for alias in list(tokens_to_remove):
                        if len(alias) >= 4:
                            ratio = SequenceMatcher(None, w_clean, alias).ratio()
                            if ratio >= 0.85:
                                tokens_to_remove.add(w_clean)
                                break

    sorted_tokens = sorted(tokens_to_remove, key=len, reverse=True)

    cleaned_plate = plate_number

    changed = True
    while changed:
        changed = False
        for tok in sorted_tokens:
            if not tok:
                continue
            if cleaned_plate.startswith(tok):
                cleaned_plate = cleaned_plate[len(tok):]
                changed = True
                break
            if cleaned_plate.endswith(tok):
                cleaned_plate = cleaned_plate[:-len(tok)]
                changed = True
                break

    for tok in sorted_tokens:
        if len(tok) >= 4 and tok in cleaned_plate:
            cleaned_plate = cleaned_plate.replace(tok, "")

    changed = True
    while changed:
        changed = False
        for tok in sorted_tokens:
            if not tok:
                continue
            if cleaned_plate.startswith(tok):
                cleaned_plate = cleaned_plate[len(tok):]
                changed = True
                break
            if cleaned_plate.endswith(tok):
                cleaned_plate = cleaned_plate[:-len(tok)]
                changed = True
                break

    return cleaned_plate


# -----------------------------------
# OCR FUNCTION
# -----------------------------------

def read_plate(plate_image_paths):

    ocr_records = []

    for plate_path in plate_image_paths:

        filename = os.path.basename(
            plate_path
        )

        plate = cv2.imread(
            plate_path
        )

        if plate is None:
            continue

        print(f"Processing: {filename}")

        results = reader.predict(
            plate
        )

        detected_texts = []

        confidences = []

        all_raw_texts = []

        # ----------------------------
        # READ TEXT
        # ----------------------------

        for result in results:
           
            result_dict = result.json
            res = result_dict["res"]

            texts = res.get("rec_texts", [])
            scores = res.get("rec_scores", [])
            all_raw_texts.extend(texts)

            for text, confidence in zip(
                texts,
                scores
            ):

                cleaned_text = clean_plate_text(
                    text
                )

                if cleaned_text:

                    detected_texts.append(
                        cleaned_text
                    )

                    confidences.append(
                        float(confidence)
                    )

                    print(
                        f"Detected: {cleaned_text}"
                    )

        # ----------------------------
        # OCR RESULT
        # ----------------------------

        if detected_texts:

            plate_number = "".join(
                detected_texts
            )

            average_confidence = (
                sum(confidences)
                / len(confidences)
            )

            status = "Detected"


        else:

            plate_number = ""

            average_confidence = 0.0

            status = "No text detected"

        province = detect_province(all_raw_texts)
        if province:
            print(f"Detected Province: {province}")
            plate_number = remove_province_from_plate(plate_number, province, all_raw_texts)
            if not plate_number:
                status = "No text detected"
            else:
                print(f"Plate Number: {plate_number}")

        # ----------------------------
        # STORE OCR RECORD
        # ----------------------------

        
        ocr_records.append({

            "image": filename,

            "plate_number": plate_number,

            "province": province,

            "confidence": round(
                average_confidence,
                2
            ),

            "status": status

        })

        print("-" * 50)

    print("\nOCR completed.")
    return csv_path, ocr_records


