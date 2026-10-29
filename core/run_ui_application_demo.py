import os

def test_ui_application():
    with open('web_demo/index.html', 'r') as file:
        content = file.read()
        assert "Scheme Application" in content, "Scheme Application section not found"
        assert "/apply_step" in content, "/apply_step endpoint not found"
        assert "/upload_doc" in content, "/upload_doc endpoint not found"

if __name__ == '__main__':
    test_ui_application()
    print("ui_application PASSED")
