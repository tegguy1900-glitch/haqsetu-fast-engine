import sqlite3
import os

DB_PATH = "data/haqsetu.db"

def init_database():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Table 1: Users (Citizens, JEs, Sarpanchs)
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mobile_hash TEXT UNIQUE,
        pin_hash TEXT,
        name TEXT,
        role TEXT CHECK(role IN ('citizen', 'je', 'sarpanch')),
        ward_id TEXT
    )''')
    
    # Table 2: Infrastructure Tickets (Handpumps, Roads, etc.)
    c.execute('''CREATE TABLE IF NOT EXISTS tickets_infra (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        citizen_mobile_hash TEXT,
        description TEXT,
        photo_path TEXT,
        geo_lat REAL,
        geo_lon REAL,
        timestamp_created DATETIME DEFAULT CURRENT_TIMESTAMP,
        status TEXT CHECK(status IN ('open', 'assigned', 'fixed_pending_otp', 'closed')) DEFAULT 'open',
        je_assigned_id INTEGER,
        fix_photo_path TEXT,
        fix_geo_lat REAL,
        fix_geo_lon REAL,
        otp_code TEXT,
        FOREIGN KEY(je_assigned_id) REFERENCES users(id)
    )''')
    
    # Table 3: Scheme Applications (MGNREGA, Pensions, etc.)
    c.execute('''CREATE TABLE IF NOT EXISTS applications_scheme (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        citizen_mobile_hash TEXT,
        scheme_name TEXT,
        parsed_data_json TEXT,
        doc_type_uploaded TEXT, -- e.g., 'death_cert', 'age_proof'
        bot_status TEXT CHECK(bot_status IN ('pending', 'processing', 'success', 'failed')),
        reg_id_generated TEXT,
        screenshot_path TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Table 4: Meeting Logs (Transcripts & Reports)
    c.execute('''CREATE TABLE IF NOT EXISTS meetings_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_started DATETIME,
        transcript_json TEXT,
        pdf_report_path TEXT,
        summary_stats TEXT
    )''')
    
    conn.commit()
    conn.close()
    print("✅ Database Initialized at data/haqsetu.db")

if __name__ == "__main__":
    init_database()
