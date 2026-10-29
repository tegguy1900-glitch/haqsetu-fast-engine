import re

def parse_user_input(raw_text):
    """
    Extracts structured data from natural language input.
    Supports MGNREGA, Old Age Pension, Widow Pension contexts.
    """
    text = raw_text.lower().strip()
    
    data = {
        "name": None,
        "father_name": None,
        "mobile": None,
        "aadhaar_last4": None,
        "village": None,
        "doc_hint": None # 'death_cert', 'age_proof', or None
    }

    # 1. Mobile Number
    mobile_match = re.search(r'\b\d{10}\b', text)
    if mobile_match:
        data["mobile"] = mobile_match.group()

    # 2. Aadhaar Last 4
    aadhaar_match = re.search(r'(?:last\s*4|antim\s*4)\s*:?\s*(\d{4})', text)
    if not aadhaar_match:
        aadhaar_match = re.search(r'aadhaar.*?(\d{4})', text)
    if aadhaar_match:
        data["aadhaar_last4"] = aadhaar_match.group(1)

    # 3. Name Extraction
    def clean_val(val):
        if not val: return None
        val = re.sub(r'[.,!?]+$', '', val).strip()
        return val.title() if val else None

    # Applicant Name
    name_pattern = r'(?:my name is|mera naam|i am|main hoon)\s+([a-zA-Z\s]+?)(?=\s+(?:and|aur|father|pitaji|pita|husband|pati|mobile|number)|[,.]|$)'
    name_match = re.search(name_pattern, text)
    if name_match:
        data["name"] = clean_val(name_match.group(1))

    # Father/Husband Name
    father_pattern = r'(?:father|pitaji|pita ji|husband|pati)\s+(?:is|hai|hoon)?\s+([a-zA-Z\s]+?)(?=\s+(?:and|aur|mobile|number|ward|gaon)|[,.]|$)'
    father_match = re.search(father_pattern, text)
    if father_match:
        data["father_name"] = clean_val(father_match.group(1))

    # 4. Document Hint Detection (For Pension Wizards)
    if any(kw in text for kw in ["vidhwa", "widow", "patni mar gayi", "husband died"]):
        data["doc_hint"] = "death_cert"
    elif any(kw in text for kw in ["budhape", "old age", "60 saal", "retirement"]):
        data["doc_hint"] = "age_proof"
        
    return data

# Test Block
if __name__ == "__main__":
    tests = [
        "My name is Ramesh Kumar, father Suresh, mobile 9876543210.",
        "Main vidhwa hoon, naam Sunita Devi, pati ka death certificate upload karungi."
    ]
    for t in tests:
        print(f"Input: {t}")
        print(f"Output: {parse_user_input(t)}\n{'-'*40}")

# --- NEW ENHANCEMENT: IMAGE PARSING (OCR) ---
try:
    import pytesseract
    from PIL import Image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False
    print("⚠️ Warning: pytesseract/PIL not found. OCR disabled.")

def parse_image_input(image_path):
    """
    Extracts text from an image using OCR and then parses it.
    Returns dict with extracted fields or None if failed.
    """
    if not HAS_OCR:
        return None
        
    try:
        # Open image
        img = Image.open(image_path)
        
        # Convert to grayscale for better contrast/accuracy
        img_gray = img.convert('L')
        
        # Perform OCR (English + Hindi support if installed)
        # Note: For pure English IDs, lang='eng' is fastest. 
        # If you have Hindi data, use lang='hin+eng' (requires tesseract-ocr-hin package)
        raw_text = pytesseract.image_to_string(img_gray, lang='eng') 
        
        print(f"   👁️ [OCR] Raw Text Extracted ({len(raw_text)} chars)")
        
        # Pass extracted text through our existing regex parser
        parsed_data = parse_user_input(raw_text)
        
        # Clean up common OCR errors (e.g., confusing '0' with 'O', '1' with 'l')
        if parsed_data.get("name"):
            parsed_data["name"] = parsed_data["name"].replace("0", "O").replace("1", "I")
            
        return parsed_data
    
    except Exception as e:
        print(f"❌ [OCR] Failed: {e}")
        return None
