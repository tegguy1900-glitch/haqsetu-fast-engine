import core.scheme_application as scheme_app

def test_voice_extraction():
    text = "My Aadhaar number is 123456789012"
    result = scheme_app.process_voice_step("MGNREGA", "Provide Aadhaar number", text)
    assert result == "123456789012", f"Expected '123456789012', got {result}"

def test_document_verification():
    result = scheme_app.verify_document("MGNREGA", "Aadhaar", "aadhaar.pdf")
    assert result == "Verified", f"Expected 'Verified', got {result}"

    result = scheme_app.verify_document("MGNREGA", "Aadhaar", "aadhaar.jpg")
    assert result == "Wrong Document Type", f"Expected 'Wrong Document Type', got {result}"

    result = scheme_app.verify_document("MGNREGA", "Driving License", "license.pdf")
    assert result == "Missing", f"Expected 'Missing', got {result}"

if __name__ == '__main__':
    test_voice_extraction()
    test_document_verification()
    print("application_engine PASSED")
