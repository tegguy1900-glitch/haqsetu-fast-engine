import re

SCHEME_REQUIREMENTS = {
    "MGNREGA": {
        "steps": [
            "Provide Aadhaar number",
            "Upload Photo",
            "Upload Bank Passbook"
        ],
        "required_docs": {
            "Aadhaar": "pdf",
            "Photo": "jpg",
            "Bank Passbook": "pdf"
        }
    }
}

def process_voice_step(scheme, step, text):
    if scheme == "MGNREGA":
        if step == "Provide Aadhaar number":
            match = re.search(r'\d{12}', text)
            if match:
                return match.group()
        elif step == "Upload Photo":
            return text.strip()
        elif step == "Upload Bank Passbook":
            return text.strip()
    return None

def verify_document(scheme, doc_type, filename):
    if scheme == "MGNREGA":
        required_extension = SCHEME_REQUIREMENTS[scheme]["required_docs"].get(doc_type)
        if required_extension:
            if filename.endswith(f".{required_extension}"):
                return "Verified"
            else:
                return "Wrong Document Type"
        else:
            return "Missing"
    return "Invalid Scheme"
