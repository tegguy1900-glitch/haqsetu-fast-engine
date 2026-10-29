"""
Haq Setu - Scheme catalog (DATA, not code). Declarative eligibility so every rule is
auditable and serializable. Each scheme carries source + verify: the THRESHOLDS below
are a STARTING POINT to check against the official scheme guidelines before production.
Your legacy 50 YAML drops in as MORE rows here - no engine change.
requires clauses: {fact, op, value}. op in {>=,<=,>,<,==,!=,in,not_in,truthy,falsy}.
A required fact that is MISSING (not merely false) => scheme is UNCERTAIN => engine
abstains rather than guessing. The engine never asserts a scheme absent from this list.
"""
SCHEMES = [
  {"id":"nsap_old_age","name":"Old Age Pension (NSAP/IGMSY)","source":"MoRD NSAP guidelines",
   "verify":"age slab & amount per state notification","docs":["age proof","residence","bank"],
   "benefit":"monthly old-age pension","requires":[{"fact":"age","op":">=","value":60}]},
  {"id":"nsap_widow","name":"Widow Pension (NSAP)","source":"MoRD NSAP guidelines",
   "verify":"widowhood + age slab per state","docs":["death cert of spouse","age","residence"],
   "benefit":"monthly widow pension","requires":[{"fact":"is_widow","op":"==","value":True}]},
  {"id":"nsap_disability","name":"Disability Pension (NSAP)","source":"MoRD NSAP guidelines",
   "verify":"disability % certificate","docs":["disability cert","age","residence"],
   "benefit":"monthly disability pension","requires":[{"fact":"is_disabled","op":"==","value":True}]},
  {"id":"pmay_gramin","name":"PM Awas Yojana - Gramin","source":"MoRD PMAY-G",
   "verify":"houselessness/kutcha + priority list","docs":["house status","land","Aadhaar"],
   "benefit":"housing assistance","requires":[{"fact":"has_pucca_house","op":"==","value":False}]},
  {"id":"ayushman_bharat","name":"Ayushman Bharat (PM-JAY)","source":"NIHM PM-JAY",
   "verify":"income/DEPR + SECC proxy","docs":["Aadhaar","ration/income"],
   "benefit":"Rs 5 lakh/yr health cover",
   "requires":[{"fact":"annual_income","op":"<","value":180000}],
   "alt":[{"fact":"is_sc_st","op":"==","value":True},{"fact":"is_bpl","op":"==","value":True}]},
  {"id":"pm_kisan","name":"PM-KISAN Samman Nidhi","source":"DoAF PM-KISAN",
   "verify":"landholding + exclusion list","docs":["land records","Aadhaar","bank"],
   "benefit":"Rs 6000/yr income support","requires":[{"fact":"is_farmer","op":"==","value":True}]},
  {"id":"ujjwala","name":"Ujjwala Yojana (LPG)","source":"MoP Ujjwala",
   "verify":"woman-headed/BPL + no connection","docs":["ration","Aadhaar"],
   "benefit":"LPG connection subsidy",
   "requires":[{"fact":"is_woman","op":"==","value":True},{"fact":"has_lpg","op":"==","value":False}]},
  {"id":"ration_pds","name":"NFSA Ration Card (PDS)","source":"MoF NFSA",
   "verify":"PHH/antyodaya criteria","docs":["family members","income","residence"],
   "benefit":"subsidised food grains",
   "requires":[{"fact":"is_bpl","op":"==","value":True}],
   "alt":[{"fact":"annual_income","op":"<","value":100000}]},
  {"id":"matric_scholarship","name":"Pre/Post-Matric Scholarship","source":"MoSE / state",
   "verify":"minority/SC-ST + income","docs":["child school proof","income","caste"],
   "benefit":"education scholarship",
   "requires":[{"fact":"has_school_child","op":"==","value":True}],
   "alt":[{"fact":"is_sc_st","op":"==","value":True},{"fact":"is_bpl","op":"==","value":True}]},
  {"id":"mgnrega","name":"MGNREGA job card","source":"MoRD MGNREGA",
   "verify":"adult + rural household","docs":["age","residence","Aadhaar"],
   "benefit":"100 days wage work/yr",
   "requires":[{"fact":"age","op":">=","value":18},{"fact":"age","op":"<=","value":60}]},
  {"id":"indira_awas","name":"Indira Awaas / PMAY-G widow priority","source":"MoRD",
   "verify":"widow + kutcha house","docs":["widowhood","house status"],
   "benefit":"priority housing",
   "requires":[{"fact":"is_widow","op":"==","value":True},{"fact":"has_pucca_house","op":"==","value":False}]},
  {"id":"sarva_shiksha_child","name":"Sarva Shiksha / RTE child entitlement","source":"MoE RTE",
   "verify":"school-age child","docs":["child age proof"],
   "benefit":"free elementary education",
   "requires":[{"fact":"has_school_child","op":"==","value":True}]},
]
