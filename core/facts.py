"""
Haq Setu - Fact extractor. Parses Hinglish/Hindi/English into a normalized facts dict.
NEVER invents: a field appears only when a pattern matches; absent => missing => abstain.
Grounded additions from your visible extractor: crop loss %, days-since-work-demand, and
insurance TRI-STATE with the neg-first guard (your comment: "not insured" contains
"insured", so check negative before positive). Age requires a cue word; income parses
magnitude words and stops at the first non-magnitude token.
"""
import re
_AGE = re.compile(r"\b(\d{2,3})\b\s*(?:saal|sal|years?|year|umar|age|barsa|varsh|वर्ष|साल|उम्र)", re.I)
_INCOME = re.compile(r"(?:income|aamdani|aamdni|amdani|kamai|earning|आमदननी|आय|कमाई)\b[\s,:]*(.{0,40})", re.I)
_LOSS = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent|pratishat|प्रतिशत)", re.I)
_LOSS2 = re.compile(r"(?:loss|damage|kharab|nuksan|nuqsan|नुकसान)\s*(?:of|is|was|hai)?\s*(\d+(?:\.\d+)?)", re.I)
_DAYS = re.compile(r"(\d+)\s*(?:days?|din|दिन)", re.I)
_WEEKS = re.compile(r"(\d+)\s*(?:weeks?|hafte|सप्ताह|हफ्तो)", re.I)
_INS_POS = ["insured","beema","bima","pmfby","बीमा","भरसा"]
_INS_NEG = ["not insured","uninsured","nahi","nhi","not beema","no beema","नहीं","ना"]
_MULT = {"hazaar":1000,"hazar":1000,"thousand":1000,"k":1000,"हजार":1000,
         "lakh":100000,"lac":100000,"लाख":100000,"crore":10000000,"karod":10000000,"करोड़":10000000}
_VOCAB = {
 "is_widow":(r"widow|vidhwa|vidawa|parinemta|parinamita|विधवा",None),
 "is_woman":(r"\bwoman\b|\bfemale\b|mahila|aurat|stree|स्त्री|महिला",r"\bman\b|\bmale\b|purush|aadmi"),
 "is_disabled":(r"disab|viklang|diggaj|विकलांग|दिव्यांग",None),
 "has_pucca_house":(r"pucca|pakka|pakke|concrete|cement|पक्का",r"kacha|kachcha|kutcha|kutchi|mud|jhoppi|कच्चा|झोपड़ी"),
 "is_farmer":(r"farmer|kisan|krishak|khedut|किसान|खेती|farm",None),
 "has_lpg":(r"lpg|gas connection|गैस",None),
 "is_sc_st":(r"\bsc\b|\bst\b|scheduled caste|scheduled tribe|dalit|आदिवासी|अनुसूचित",None),
 "is_bpl":(r"bpl|below poverty|garib|गरीब|बीपीएल|yellow card",None),
 "has_school_child":(r"child|bachcha|baccha|beta|beti|student|school|पढ़ता|विद्यालय|स्कूल",None),
 "has_land":(r"land|zameen|jameen|khet|plot|भूमि|जमीन|खेत",None),
 "is_pregnant_or_lactating":(r"pregnant|garbhavati|feeding|sthan|दूध पिला|गर्भवती",None),
 "is_student":(r"student|padhta|padhti|chhatra|chatra|विद्यार्थी|पढ़ता",None),
 "is_girl_child":(r"girl child|beti|kanya|bachi|बेटी|कन्या",None),
 "is_single_woman":(r"single woman|akeli mahila|unmarried woman|अकेली",None),
}
def _collapse(s): return re.sub(r"(?<=\d)[, ](?=\d)", "", s)
def _parse_amount(chunk):
    c=_collapse(chunk or ""); toks=re.findall(r"\d+|[^\d\s]+", c); total=0; i=0; n=len(toks); started=False
    while i<n:
        t=toks[i]
        if t.isdigit():
            cur=int(t); started=True; i+=1
            if i<n and toks[i].lower() in _MULT: total+=cur*_MULT[toks[i].lower()]; i+=1; continue
            else: total+=cur; break
        else: break
    return total if (started and total>0) else None
def _insured(low):
    for kw in _INS_NEG:
        if kw in low: return False          # neg-first: "not insured" contains "insured"
    for kw in _INS_POS:
        if kw in low: return True
    return None
def extract(raw_text, lang=None):
    t=(raw_text or "").strip(); low=t.lower(); f={}
    if not t: return f
    m=_AGE.search(low)
    if m and 18<=int(m.group(1))<=120: f["age"]=int(m.group(1))
    im=_INCOME.search(low) or _INCOME.search(t)
    if im:
        amt=_parse_amount(im.group(1))
        if amt is not None: f["annual_income_inr"]=amt
    lm=_LOSS.search(low) or _LOSS2.search(low)
    if lm:
        try:
            v=float(lm.group(1))
            if 0<=v<=100: f["crop_loss_percentage"]=v
        except ValueError: pass
    dm=_DAYS.search(low)
    if dm: f["days_since_work_demand"]=int(dm.group(1))
    else:
        wm=_WEEKS.search(low)
        if wm: f["days_since_work_demand"]=int(wm.group(1))*7
    ins=_insured(low)
    if ins is not None: f["is_insured"]=ins
    for fact,(pos,neg) in _VOCAB.items():
        if re.search(pos,low) or re.search(pos,t):
            if neg and re.search(neg,low): continue
            f[fact]=True
    if "has_pucca_house" not in f and re.search(r"kacha|kachcha|kutcha|kutchi|mud|jhoppi|कच्चा|झोपड़ी",low):
        f["has_pucca_house"]=False
    if f.get("is_woman") and "has_lpg" not in f and not re.search(r"lpg|gas",low):
        f["has_lpg"]=False
    return f
