import sys
import os

# Add project root to path so imports work
sys.path.insert(0, os.getcwd())

from core.parser import parse_user_input
from core.mgnrega_bot import MGNREGABot

def run_test():
    print("="*60)
    print(" TESTING FULL PIPELINE: TEXT -> PARSE -> SELENIUM -> RESULT")
    print("="*60)
    
    # 1. Simulate Voice Input
    raw_text = "My name is Ramesh Kumar and my father is Suresh. Mobile 9876543210. Last 4 Aadhaar 1234."
    print(f"\n🎤 INPUT (Simulated Voice):\n'{raw_text}'\n")
    
    # 2. Parse Data
    print("🧠 STEP 1: Parsing Natural Language...")
    data = parse_user_input(raw_text)
    print(f"   Extracted Data: {data}")
    
    # Validate critical fields exist
    if not data.get('name') or not data.get('mobile'):
        print("❌ FAIL: Parser did not extract Name or Mobile.")
        return False
        
    # 3. Run Selenium Bot
    print("\n🤖 STEP 2: Launching Automation Bot (Headless Firefox)...")
    try:
        bot = MGNREGABot()
        result = bot.register_citizen(data)
        
        if result['status'] == 'success':
            print(f"\n✅ SUCCESS! Registration Completed.")
            print(f"   🆔 Reg ID: {result['registration_id']}")
            print(f"   📸 Proof Saved: {result['screenshot_path']}")
            return True
        else:
            print(f"\n❌ BOT FAILED: {result.get('error')}")
            return False
            
    except Exception as e:
        print(f"\n💥 CRASH during Bot Execution:\n{e}")
        return False

if __name__ == "__main__":
    success = run_test()
    print("\n" + "="*60)
    if success:
        print("🟢 PIPELINE VERIFIED: READY FOR UI INTEGRATION")
    else:
        print("🔴 PIPELINE BROKEN: FIX TERMINAL LOGIC FIRST")
    print("="*60)
