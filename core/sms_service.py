import os
from twilio.rest import Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SID = os.getenv("TWILIO_ACCOUNT_SID")
TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
FROM_NUM = os.getenv("TWILIO_PHONE_NUMBER")

if not SID or not TOKEN:
    print("⚠️ Warning: Twilio credentials missing in .env. SMS disabled.")

client = None
if SID and TOKEN:
    try:
        client = Client(SID, TOKEN)
        print("📱 [SMS] Twilio Client Initialized.")
    except Exception as e:
        print(f"❌ [SMS] Init Error: {e}")

def send_otp(to_number, otp_code):
    """
    Sends an OTP via SMS using Twilio.
    Returns True if successful, False otherwise.
    """
    if not client:
        print("   ❌ Cannot send SMS: Client not initialized.")
        return False
        
    message_body = f"[HaqSetu] Your verification code is {otp_code}. Do not share this code with anyone."
    
    try:
        msg = client.messages.create(
            body=message_body,
            from_=FROM_NUM,
            to=to_number
        )
        print(f"   ✅ [SMS] Sent OTP {otp_code} to {to_number} (Sid: {msg.sid})")
        return True
    except Exception as e:
        print(f"   ❌ [SMS] Failed: {str(e)}")
        return False
