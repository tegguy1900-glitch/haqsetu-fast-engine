import re

with open('village/server.py', 'r') as f:
    code = f.read()

# 1. Ensure Imports are present at top
if 'from core.sms_service import send_otp' not in code:
    # Add import inside the try-except block if it exists, or just before class definition
    pass 

# 2. Replace handle_infra_fix function entirely
old_func_pattern = r'(    def handle_infra_fix\(self, data\):.*?return)'
new_func_code = '''    def handle_infra_fix(self, data):
        ticket_id = data.get("ticket_id")
        new_lat = float(data.get("new_lat", 0))
        new_lon = float(data.get("new_lon", 0))
        photo_base64 = data.get("photo")
        citizen_mobile = data.get("citizen_mobile", "+919876543210") 
        
        conn = get_db_conn()
        c = conn.cursor()
        
        # Get Original Coords
        c.execute("SELECT geo_lat, geo_lon FROM tickets_infra WHERE id=?", (ticket_id,))
        row = c.fetchone()
        
        if not row:
            self._send_json(404, {"error": "Ticket not found"})
            return
            
        orig_lat, orig_lon = row["geo_lat"], row["geo_lon"]
        
        # Geo Verification
        is_valid, distance = is_within_radius(orig_lat, orig_lon, new_lat, new_lon, radius_meters=50)
        
        if not is_valid:
            self._send_json(400, {"error": f"GEO_MISMATCH. Distance: {distance:.2f}m."})
            return
            
        # Save Fix Photo (Simplified for demo)
        fix_filepath = None
        
        # Generate OTP
        otp = generate_otp()
        
        # Update Ticket Status
        c.execute("""UPDATE tickets_infra 
                     SET status='fixed_pending_otp', fix_geo_lat=?, fix_geo_lon=?, otp_code=?
                     WHERE id=?""",
                  (new_lat, new_lon, otp, ticket_id))
                  
        conn.commit()
        conn.close()
        
        # ==========================================
        # ENHANCEMENT: SEND REAL SMS VIA TWILIO
        # ==========================================
        sms_status = "SIMULATED"
        try:
            from core.sms_service import send_otp
            success = send_otp(citizen_mobile, otp)
            if success:
                sms_status = "SENT_REAL_SMS"
        except ImportError:
            sms_status = "TWILIO_LIB_MISSING"
        except Exception as e:
            sms_status = f"ERROR: {str(e)}"
            
        response_msg = f"Fix verified. SMS Status: {sms_status}"
        if sms_status == "SENT_REAL_SMS":
             response_msg += f". OTP sent to {citizen_mobile[-4:]}"
             
        self._send_json(200, {"message": response_msg, "otp_preview": otp})'''

if re.search(old_func_pattern, code, re.DOTALL):
    code = re.sub(old_func_pattern, new_func_code, code, flags=re.DOTALL)
    with open('village/server.py', 'w') as f:
        f.write(code)
    print("✅ Server Patched with Safe SMS Logic.")
else:
    print("⚠️ Could not find exact function pattern. Manual check needed.")
