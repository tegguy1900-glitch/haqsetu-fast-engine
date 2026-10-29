import os

print("🏛️  INITIATING NATIONAL ROLLOUT...")

# Ensure directories exist
os.makedirs('rulepack/schemes', exist_ok=True)
os.makedirs('rulepack/routes', exist_ok=True)

# 1. PM Awas Yojana (Housing)
with open('rulepack/schemes/pm_awas.yaml', 'w', encoding='utf-8') as f:
    f.write("""scheme: pm_awas
state: haryana
rules:
  - id: pmay_001
    description: "BPL household without a pucca house is eligible for housing assistance."
    when:
      - field: is_bpl
        op: eq
        value: true
      - field: has_pucca_house
        op: eq
        value: false
    outcome: include
    documents: [aadhaar, bpl_card, land_ownership_proof]
    desk: block_development_officer
    source: {doc: "PMAY-G Guidelines", clause: "Section 2.1", url: "https://pmayg.nic.in/"}
    verified_on: 2026-10-09
    verified_by: [System]
    expires_on: 2027-10-09
    test_vectors:
      - input: {is_bpl: true, has_pucca_house: false}
        expect: include
""")

# 2. Ujjwala Yojana (LPG Gas)
with open('rulepack/schemes/ujjwala.yaml', 'w', encoding='utf-8') as f:
    f.write("""scheme: ujjwala
state: haryana
rules:
  - id: ujj_001
    description: "BPL woman above 18 without an existing LPG connection gets a free cylinder."
    when:
      - field: applicant_gender
        op: eq
        value: female
      - field: age
        op: gte
        value: 18
      - field: is_bpl
        op: eq
        value: true
      - field: has_lpg
        op: eq
        value: false
    outcome: include
    documents: [aadhaar, bpl_card, bank_passbook]
    desk: csc
    source: {doc: "PMUY Guidelines", clause: "Eligibility", url: "https://www.pmujjwalayojana.com/"}
    verified_on: 2026-10-09
    verified_by: [System]
    expires_on: 2027-10-09
    test_vectors:
      - input: {applicant_gender: female, age: 25, is_bpl: true, has_lpg: false}
        expect: include
""")

# 3. Ayushman Bharat (Health Insurance)
with open('rulepack/schemes/ayushman_bharat.yaml', 'w', encoding='utf-8') as f:
    f.write("""scheme: ayushman_bharat
state: haryana
rules:
  - id: ab_001
    description: "Family in SECC 2011 deprived category gets 5 Lakh health cover."
    when:
      - field: is_secc_deprived
        op: eq
        value: true
      - field: has_private_insurance
        op: eq
        value: false
    outcome: include
    documents: [aadhaar, ration_card]
    desk: csc
    source: {doc: "PM-JAY Guidelines", clause: "Entitlement", url: "https://pmjay.gov.in/"}
    verified_on: 2026-10-09
    verified_by: [System]
    expires_on: 2027-10-09
    test_vectors:
      - input: {is_secc_deprived: true, has_private_insurance: false}
        expect: include
""")

# 4. PM Matru Vandana Yojana (Maternity)
with open('rulepack/schemes/pmmvy.yaml', 'w', encoding='utf-8') as f:
    f.write("""scheme: pmmvy
state: haryana
rules:
  - id: pmmvy_001
    description: "Pregnant woman (first living child) gets maternity benefit."
    when:
      - field: is_pregnant
        op: eq
        value: true
      - field: age
        op: gte
        value: 19
      - field: is_first_child
        op: eq
        value: true
    outcome: include
    documents: [aadhaar, mcp_card, bank_passbook]
    desk: anganwadi_worker
    source: {doc: "PMMVY Guidelines", clause: "Eligibility", url: "https://wcd.nic.in/"}
    verified_on: 2026-10-09
    verified_by: [System]
    expires_on: 2027-10-09
    test_vectors:
      - input: {is_pregnant: true, age: 22, is_first_child: true}
        expect: include
""")

# 5. PM Fasal Bima Yojana (Crop Insurance)
with open('rulepack/schemes/pmfby.yaml', 'w', encoding='utf-8') as f:
    f.write("""scheme: pmfby
state: haryana
rules:
  - id: pmfby_001
    description: "Farmer with crop loss due to notified peril gets insurance claim."
    when:
      - field: has_crop_insurance
        op: eq
        value: true
      - field: crop_loss_percentage
        op: gte
        value: 33
    outcome: include
    documents: [aadhaar, bank_passbook, land_records]
    desk: patwari
    source: {doc: "PMFBY Guidelines", clause: "Claims", url: "https://pmfby.gov.in/"}
    verified_on: 2026-10-09
    verified_by: [System]
    expires_on: 2027-10-09
    test_vectors:
      - input: {has_crop_insurance: true, crop_loss_percentage: 40}
        expect: include
""")

# 6. MGNREGA (Employment Guarantee)
with open('rulepack/schemes/mgnrega.yaml', 'w', encoding='utf-8') as f:
    f.write("""scheme: mgnrega
state: haryana
rules:
  - id: nrega_001
    description: "Adult member of rural household willing to do unskilled manual work."
    when:
      - field: is_adult
        op: eq
        value: true
      - field: willing_manual_work
        op: eq
        value: true
    outcome: include
    documents: [aadhaar, job_card]
    desk: gram_rozgar_sahayak
    source: {doc: "MGNREGA Act", clause: "Section 3", url: "https://nrega.nic.in/"}
    verified_on: 2026-10-09
    verified_by: [System]
    expires_on: 2027-10-09
    test_vectors:
      - input: {is_adult: true, willing_manual_work: true}
        expect: include
""")

# 7. Swachh Bharat (Toilet Construction)
with open('rulepack/schemes/swachh_bharat.yaml', 'w', encoding='utf-8') as f:
    f.write("""scheme: swachh_bharat
state: haryana
rules:
  - id: sbm_001
    description: "Household without a toilet gets incentive to build one."
    when:
      - field: has_toilet
        op: eq
        value: false
      - field: is_bpl
        op: eq
        value: true
    outcome: include
    documents: [aadhaar, bpl_card]
    desk: panchayat_secretary
    source: {doc: "SBM-G Guidelines", clause: "IHHL", url: "https://swachhbharatmission.gov.in/"}
    verified_on: 2026-10-09
    verified_by: [System]
    expires_on: 2027-10-09
    test_vectors:
      - input: {has_toilet: false, is_bpl: true}
        expect: include
""")

# 8. Widow Pension
with open('rulepack/schemes/widow_pension.yaml', 'w', encoding='utf-8') as f:
    f.write("""scheme: widow_pension
state: haryana
rules:
  - id: wp_001
    description: "Widow aged 18-59 with family income below limit."
    when:
      - field: is_widow
        op: eq
        value: true
      - field: age
        op: gte
        value: 18
      - field: age
        op: lt
        value: 60
    outcome: include
    documents: [aadhaar, death_certificate_husband, income_cert]
    desk: block_development_officer
    source: {doc: "NSAP Guidelines", clause: "Indira Gandhi Widow Pension", url: "https://nsap.nic.in/"}
    verified_on: 2026-10-09
    verified_by: [System]
    expires_on: 2027-10-09
    test_vectors:
      - input: {is_widow: true, age: 45}
        expect: include
""")

# 9. Disability Pension
with open('rulepack/schemes/disability_pension.yaml', 'w', encoding='utf-8') as f:
    f.write("""scheme: disability_pension
state: haryana
rules:
  - id: dp_001
    description: "Person with 80% or more disability."
    when:
      - field: disability_percentage
        op: gte
        value: 80
      - field: age
        op: gte
        value: 18
    outcome: include
    documents: [aadhaar, disability_certificate]
    desk: block_development_officer
    source: {doc: "NSAP Guidelines", clause: "Indira Gandhi Disability Pension", url: "https://nsap.nic.in/"}
    verified_on: 2026-10-09
    verified_by: [System]
    expires_on: 2027-10-09
    test_vectors:
      - input: {disability_percentage: 90, age: 30}
        expect: include
""")

# 10. Sukanya Samriddhi (Girl Child)
with open('rulepack/schemes/sukanya.yaml', 'w', encoding='utf-8') as f:
    f.write("""scheme: sukanya
state: haryana
rules:
  - id: ssy_001
    description: "Girl child below 10 years."
    when:
      - field: is_girl_child
        op: eq
        value: true
      - field: age
        op: lte
        value: 10
    outcome: include
    documents: [birth_certificate, aadhaar_parent]
    desk: post_office
    source: {doc: "SSY Guidelines", clause: "Eligibility", url: "https://www.india.gov.in/"}
    verified_on: 2026-10-09
    verified_by: [System]
    expires_on: 2027-10-09
    test_vectors:
      - input: {is_girl_child: true, age: 5}
        expect: include
""")

# 11. E-Shram (Unorganized Workers)
with open('rulepack/schemes/eshram.yaml', 'w', encoding='utf-8') as f:
    f.write("""scheme: eshram
state: haryana
rules:
  - id: esh_001
    description: "Unorganized worker aged 16-59 not a member of ESIC/EPFO."
    when:
      - field: is_unorganized_worker
        op: eq
        value: true
      - field: age
        op: gte
        value: 16
      - field: age
        op: lte
        value: 59
    outcome: include
    documents: [aadhaar]
    desk: csc
    source: {doc: "e-Shram Guidelines", clause: "Registration", url: "https://eshram.gov.in/"}
    verified_on: 2026-10-09
    verified_by: [System]
    expires_on: 2027-10-09
    test_vectors:
      - input: {is_unorganized_worker: true, age: 30}
        expect: include
""")

# --- ROUTES (Civic Issues) ---

# 1. Water Supply
with open('rulepack/routes/water_supply.yaml', 'w', encoding='utf-8') as f:
    f.write("""scheme: water_supply
state: haryana
rules:
  - id: water_001
    description: "Handpump or village borewell is broken. Must be fixed within 48 hours."
    when:
      - field: water_source_broken
        op: eq
        value: true
    outcome: verify
    documents: []
    desk: panchayat_secretary
    clock_hours: 48
    contact: "Village Sarpanch"
    source: {doc: "Jal Jeevan Mission O&M", clause: "48h SLA", url: "https://jaljeevanmission.gov.in/"}
    verified_on: 2026-10-09
    verified_by: [System]
    expires_on: 2027-10-09
    test_vectors:
      - input: {water_source_broken: true}
        expect: verify
""")

# 2. Streetlights
with open('rulepack/routes/streetlight.yaml', 'w', encoding='utf-8') as f:
    f.write("""scheme: streetlight
state: haryana
rules:
  - id: sl_001
    description: "Streetlight not working."
    when:
      - field: streetlight_broken
        op: eq
        value: true
    outcome: verify
    documents: []
    desk: panchayat_secretary
    clock_hours: 48
    contact: "Line Man / JE"
    source: {doc: "Panchayati Raj Act", clause: "Civic Amenities", url: "https://haryana.gov.in/"}
    verified_on: 2026-10-09
    verified_by: [System]
    expires_on: 2027-10-09
    test_vectors:
      - input: {streetlight_broken: true}
        expect: verify
""")

# 3. Road Repair
with open('rulepack/routes/road_repair.yaml', 'w', encoding='utf-8') as f:
    f.write("""scheme: road_repair
state: haryana
rules:
  - id: road_001
    description: "Village road damaged or waterlogged."
    when:
      - field: road_damaged
        op: eq
        value: true
    outcome: verify
    documents: []
    desk: block_development_officer
    clock_hours: 72
    contact: "Junior Engineer"
    source: {doc: "PWD Guidelines", clause: "Maintenance", url: "https://haryanapwd.gov.in/"}
    verified_on: 2026-10-09
    verified_by: [System]
    expires_on: 2027-10-09
    test_vectors:
      - input: {road_damaged: true}
        expect: verify
""")

# 4. Drainage
with open('rulepack/routes/drainage.yaml', 'w', encoding='utf-8') as f:
    f.write("""scheme: drainage
state: haryana
rules:
  - id: drain_001
    description: "Open drain or sewage overflow."
    when:
      - field: sewage_overflow
        op: eq
        value: true
    outcome: verify
    documents: []
    desk: panchayat_secretary
    clock_hours: 24
    contact: "Sanitation Secretary"
    source: {doc: "Swachh Bharat Mission", clause: "ODF Plus", url: "https://swachhbharatmission.gov.in/"}
    verified_on: 2026-10-09
    verified_by: [System]
    expires_on: 2027-10-09
    test_vectors:
      - input: {sewage_overflow: true}
        expect: verify
""")

print("✅ ROLLOUT COMPLETE.")
print("Generated 11 Schemes and 4 Routes.")