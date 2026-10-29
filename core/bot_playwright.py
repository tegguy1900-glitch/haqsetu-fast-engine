import os
import time
from playwright.sync_api import sync_playwright

class HaqSetuBot:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
    def execute_registration(self, scheme_id, user_data, doc_path=None):
        """
        Automates registration for MGNREGA or Pensions.
        Returns dict with status, reg_id, screenshot_path.
        """
        print(f"🤖 [Bot] Starting execution for Scheme: {scheme_id}")
        
        # Determine Target Portal based on Scheme
        if scheme_id == "MGNREGA":
            target_file = "mock_mgnrega.html"
        elif scheme_id in ["OLD_AGE_PENSION", "VIDHWA_PENSION"]:
            target_file = "mock_pension.html"
        else:
            return {"status": "error", "message": f"Unknown scheme: {scheme_id}"}
            
        target_url = f"file://{self.base_dir}/web_demo/{target_file}"
        umang_success_url = f"file://{self.base_dir}/web_demo/mock_umang_success.html"
        
        try:
            with sync_playwright() as p:
                # Launch Headless Chromium
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                print(f"   🌐 Navigating to: {target_url}")
                page.goto(target_url)
                page.wait_for_selector("#regForm")
                
                # --- FILL COMMON FIELDS ---
                if user_data.get("name"):
                    page.fill("#name", str(user_data["name"]))
                    print(f"   ✍️  Filled Name: {user_data['name']}")
                    
                if user_data.get("father_name"):
                    page.fill("#father_name", str(user_data["father_name"]))
                    print(f"   ✍️  Filled Father/Husband: {user_data['father_name']}")
                    
                if user_data.get("mobile"):
                    page.fill("#mobile", str(user_data["mobile"]))
                    print(f"   ✍️  Filled Mobile: {user_data['mobile']}")
                    
                if user_data.get("aadhaar_last4"):
                    page.fill("#aadhaar_last4", str(user_data["aadhaar_last4"]))
                    print(f"   ✍️  Filled Aadhaar Last 4: {user_data['aadhaar_last4']}")

                # --- SCHEME SPECIFIC LOGIC ---
                
                # Village Selection (Common for both mocks)
                village_val = str(user_data.get("village", "")).lower()
                sel_val = "ward7" # Default
                if "ward 1" in village_val or "rampur" in village_val: sel_val = "ward1"
                elif "ward 4" in village_val or "sonpur" in village_val: sel_val = "ward4"
                
                try:
                    page.select_option("#village", sel_val)
                    print(f"   🏘️ Selected Village: {sel_val}")
                except: pass

                # Document Upload (For Pensions)
                if scheme_id in ["OLD_AGE_PENSION", "VIDHWA_PENSION"] and doc_path:
                    if os.path.exists(doc_path):
                        page.set_input_files("#doc_upload", doc_path)
                        print(f"   📎 Uploaded Doc: {os.path.basename(doc_path)}")
                    else:
                        print(f"   ⚠️ Warning: Doc file not found at {doc_path}")

                # --- SUBMIT ---
                print("   👆 Clicking Submit...")
                page.click("button[type='submit']")
                
                # Wait for result div (state=attached handles hidden elements better)
                page.wait_for_selector("#result", state="attached", timeout=5000)
                
                # Extract Reg ID
                reg_id = page.inner_text("#app-id").strip()
                print(f"   ✅ Got Reg ID: {reg_id}")
                
                # --- REDIRECT TO UMANG SUCCESS PAGE ---
                print("   🔄 Redirecting to Umang Success View...")
                page.goto(umang_success_url)
                
                # Fill Umang Page Data via JS injection (simulating API response)
                page.evaluate("""(data) => {
                    document.getElementById('umang-ref-no').innerText = data.reg_id;
                    document.getElementById('umang-scheme-name').innerText = data.scheme_name;
                    document.getElementById('umang-date').innerText = new Date().toLocaleDateString();
                }""", {"reg_id": reg_id, "scheme_name": scheme_id})
                
                # Take Screenshot of the Final Umang Screen
                shot_filename = f"proof_{scheme_id}_{int(time.time())}.png"
                shot_path = os.path.join(self.base_dir, "uploads", shot_filename)
                
                # Ensure uploads dir exists
                os.makedirs(os.path.join(self.base_dir, "uploads"), exist_ok=True)
                
                page.screenshot(path=shot_path, full_page=True)
                print(f"   📸 Saved Proof: {shot_path}")
                
                browser.close()
                
                return {
                    "status": "success",
                    "registration_id": reg_id,
                    "screenshot_path": shot_path,
                    "message": f"Registered for {scheme_id} successfully."
                }

        except Exception as e:
            print(f"❌ [Bot] Error: {str(e)}")
            return {"status": "failed", "error": str(e)}

# Singleton Helper
_bot_instance = None
def get_bot():
    global _bot_instance
    if not _bot_instance:
        _bot_instance = HaqSetuBot()
    return _bot_instance
