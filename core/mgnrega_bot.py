import time
import os
from playwright.sync_api import sync_playwright

class MGNREGABot:
    def __init__(self):
        pass 

    def register_citizen(self, user_data):
        print(f"🚀 Starting Registration for: {user_data.get('name')}")
        
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            mock_url = f"file://{base_dir}/web_demo/mock_nrega_portal.html"
            
            print(f"🌐 Navigating to: {mock_url}")
            
            with sync_playwright() as p:
                # Launch Chromium in headless mode
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                # Navigate
                page.goto(mock_url)
                
                # Wait for form
                page.wait_for_selector("#regForm")
                
                # Fill Fields
                if user_data.get("name"):
                    page.fill("#name", str(user_data["name"]))
                    print(f"   ✍️  Filled [name]")
                    
                if user_data.get("father_name"):
                    page.fill("#father_name", str(user_data["father_name"]))
                    print(f"   ✍️  Filled [father_name]")
                    
                if user_data.get("mobile"):
                    page.fill("#mobile", str(user_data["mobile"]))
                    print(f"   ✍️  Filled [mobile]")
                    
                if user_data.get("aadhaar_last4"):
                    page.fill("#aadhaar_last4", str(user_data["aadhaar_last4"]))
                    print(f"   ✍️  Filled [aadhaar_last4]")
                
                # Select Village
                village_val = str(user_data.get("village", "")).lower()
                sel_val = "ward7"
                if "ward 1" in village_val or "rampur" in village_val:
                    sel_val = "ward1"
                elif "ward 4" in village_val or "sonpur" in village_val:
                    sel_val = "ward4"
                
                page.select_option("#village", sel_val)
                print(f"   🏘️ Selected Village Option: {sel_val}")

                # Submit
                print("   👆 Clicking Submit Button...")
                page.click("button[type='submit']")
                
                # CRITICAL FIX: Wait for element to be ATTACHED (exists in DOM), not necessarily VISIBLE
                # This prevents timeout errors when CSS hides the element initially
                page.wait_for_selector("#result", state="attached", timeout=5000)
                
                # Extract ID directly from inner_text regardless of visibility
                final_reg_id = page.inner_text("#app-id")
                print(f"✅ SUCCESS! Generated Reg ID: {final_reg_id}")
                
                # Screenshot (Force wait slightly to ensure render completes)
                time.sleep(0.5) 
                shot_path = os.path.join(base_dir, "receipt_proof.png")
                page.screenshot(path=shot_path, full_page=True)
                print(f"📸 Receipt saved to: {shot_path}")
                
                browser.close()
                
                return {
                    "status": "success",
                    "registration_id": final_reg_id,
                    "screenshot_path": shot_path,
                    "message": "Application submitted successfully via automated bot."
                }

        except Exception as e:
            print(f"❌ REGISTRATION FAILED: {str(e)}")
            return {"status": "failed", "error": str(e)}

def get_bot():
    return MGNREGABot()
