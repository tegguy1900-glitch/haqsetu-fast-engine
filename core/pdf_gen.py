from fpdf import FPDF
import sqlite3
import os
from datetime import datetime

DB_PATH = "data/haqsetu.db"
OUTPUT_DIR = "reports"

def generate_sdm_report():
    """
    Fetches live stats from DB and generates a professional PDF report.
    Returns the absolute path to the generated PDF.
    """
    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # --- FETCH DATA FROM SQLITE ---
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Get Ticket Stats
    c.execute("SELECT COUNT(*) FROM tickets_infra WHERE status != 'closed'")
    open_tickets = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM tickets_infra WHERE status = 'closed'")
    resolved_tickets = c.fetchone()[0]
    
    # Get Application Stats
    c.execute("SELECT COUNT(*) FROM applications_scheme")
    total_apps = c.fetchone()[0]
    
    # Get Recent Critical Items (Top 5 Open Tickets)
    c.execute("SELECT id, description, timestamp_created FROM tickets_infra WHERE status != 'closed' ORDER BY timestamp_created DESC LIMIT 5")
    recent_issues = c.fetchall()
    
    conn.close()

    # --- BUILD PDF ---
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Header
    pdf.set_fill_color(30, 64, 175) # Govt Blue
    pdf.rect(0, 0, 210, 40, 'F')
    pdf.set_y(10)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 24)
    pdf.cell(0, 10, "HAQSETU - GRAM SABHA REPORT", ln=1, align='C')
    
    pdf.set_font("Arial", '', 12)
    pdf.cell(0, 8, f"Date: {datetime.now().strftime('%d %b %Y, %I:%M %p')}", ln=1, align='C')
    
    # Reset Colors for Body
    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)
    
    # Executive Summary Section
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "1. Executive Summary", ln=1)
    pdf.set_font("Arial", '', 12)
    
    summary_text = (
        f"This report summarizes the operational status of Village Governance under HaqSetu v2.0.\n\n"
        f"- Total Open Grievances: {open_tickets}\n"
        f"- Issues Resolved Today: {resolved_tickets}\n"
        f"- Scheme Applications Processed: {total_apps}\n\n"
        f"The system utilizes AI-driven intake, automated RPA submission, and geo-cryptographic verification."
    )
    pdf.multi_cell(0, 8, summary_text)
    pdf.ln(5)
    
    # Detailed Issues Table
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "2. Pending Infrastructure Issues", ln=1)
    
    if not recent_issues:
        pdf.set_font("Arial", 'I', 12)
        pdf.cell(0, 8, "No pending critical issues found.", ln=1)
    else:
        # Table Headers
        pdf.set_font("Arial", 'B', 10)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(20, 8, "ID", border=1, fill=True)
        pdf.cell(120, 8, "Description", border=1, fill=True)
        pdf.cell(50, 8, "Reported On", border=1, fill=True, ln=1)
        
        # Rows
        pdf.set_font("Arial", '', 9)
        for row in recent_issues:
            tid, desc, ts = row
            # Truncate long descriptions
            short_desc = desc[:40] + "..." if len(desc) > 40 else desc
            
            pdf.cell(20, 7, str(tid), border=1)
            pdf.cell(120, 7, short_desc, border=1)
            pdf.cell(50, 7, ts.split('.')[0], border=1, ln=1) # Remove microseconds

    # Footer / Sign-off
    pdf.ln(20)
    pdf.set_draw_color(0, 0, 0)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 5, "Generated Automatically by F.A.S.T. Engine", ln=1)
    pdf.cell(0, 5, "Sub-Divisional Magistrate (SDM) Office Copy", ln=1)

    # Save File
    filename = f"sdm_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    filepath = os.path.join(OUTPUT_DIR, filename)
    pdf.output(filepath)
    
    return filepath

if __name__ == "__main__":
    print(generate_sdm_report())
