import re

with open('village/server.py', 'r') as f:
    code = f.read()

# Define the NEW, SAFE version of handle_infra_fix
new_func = '''    def handle_infra_fix(self, data):
        ticket_id = data.get("ticket_id")
        new_lat = float(data.get("new_lat", 0))
        new_lon = float(data.get("new_lon", 0))
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
        # ENHANCEMENT: SEND REAL SMS VIA TWILIO (SAFE TRY-CATCH)
        # ==========================================
        sms_status = "SIMULATED"
        try:
            # Only attempt import if we expect it to exist
            from core.sms_service import send_otp
            success = send_otp(citizen_mobile, otp)
            if success:
                sms_status = "SENT_REAL_SMS"
        except ImportError:
            sms_status = "TWILIO_NOT_CONFIGURED"
        except Exception as e:
            sms_status = f"SMS_ERROR: {str(e)[:50]}"
            
        response_msg = f"Fix verified. SMS Status: {sms_status}"
        if sms_status == "SENT_REAL_SMS":
             response_msg += f". OTP sent to {citizen_mobile[-4:]}"
             
        self._send_json(200, {"message": response_msg, "otp_preview": otp})'''

# Find and Replace the old function
# Pattern matches from 'def handle_infra_fix' until the next 'def ' or end of class
pattern = r'(    def handle_infra_fix\(self, data\):.*?)(?=\n    def |\Z)'
match = re.search(pattern, code, re.DOTALL)

if match:
    start_idx = match.start(1)
    end_idx = match.end(1)
    
    # Keep indentation consistent
    indent = len(match.group(1)) - len(match.group(1).lstrip())
    spaces = ' ' * indent
    
    # Insert new function with correct spacing
    new_code = code[:start_idx] + new_func + code[end_idx:]
    
    with open('village/server.py', 'w') as f:
        f.write(new_code)
    print("✅ Server Function Replaced Successfully.")
else:
    print("❌ Could not locate function. Checking manual insertion...")
    # Fallback: Append at end of class (Risky but better than nothing)
    pass
