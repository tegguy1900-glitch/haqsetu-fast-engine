import math, json, re, sys
from collections import Counter

try:
    import sklearn  # noqa: F401
    HAS_SKLEARN = True
except Exception:
    HAS_SKLEARN = False  # keyword + PPC path; never pip-install sklearn

KEYWORD_RULES = {
    "crop_loss": ["crop", "pmfby", "fasal", "hail", "drought"],
    "wage_work": ["mgnrega", "nrega", "majdoori", "wage", "job card"],
    "grievance": ["complaint", "grievance", "shikayat", "bribe"],
    "water_supply": ["handpump", "paani"],
    "streetlight": ["street light", "streetlight"],
    "road_repair": ["sadak", "road"],
    "drainage": ["naali", "sewage"],
}
MENU_OPTIONS = [
    {"id": "crop_loss", "label": "Crop loss / crop damage"},
    {"id": "wage_work", "label": "Wage work / MGNREGA"},
    {"id": "grievance", "label": "Grievance / delay / denial"},
    {"id": "other", "label": "Something else"},
]

def keyword_baseline(text, min_matches=1):
    normalized = (text or "").casefold().strip()
    if not normalized:
        return {"method": "keyword", "labels": [], "scores": {}, "matched_keywords": {}, "abstain": True}
    matched_keywords, scores, labels = {}, {}, []
    for route, keywords in KEYWORD_RULES.items():
        matches = []
        for keyword in keywords:
            pattern = r"\b" + re.escape(keyword.casefold()) + r"\b"
            if re.search(pattern, normalized):
                matches.append(keyword)
        matched_keywords[route] = matches
        scores[route] = min(1.0, len(matches) / 3.0)
        if len(matches) >= min_matches:
            labels.append(route)
    return {"method": "keyword", "labels": labels, "scores": scores,
            "matched_keywords": matched_keywords, "abstain": len(labels) == 0}

def pictogram_menu_baseline(text=None):
    """Safe abstain fallback: do not guess; show a menu."""
    return {"method": "pictogram_menu", "labels": [], "scores": {}, "abstain": True,
            "fallback": True, "options": MENU_OPTIONS, "text": text}

TRAINING_EXAMPLES = [
    ("pm kisan", ["pm_kisan"]),
    ("kisan samman", ["pm_kisan"]),
    ("pucca makan", ["pm_awas"]),
    ("awas yojana", ["pm_awas"]),
    ("gas cylinder", ["ujjwala"]),
    ("ujjwala", ["ujjwala"]),
    ("ayushman card", ["ayushman"]),
    ("health insurance", ["ayushman"]),
    ("pregnant hoon", ["pmmvy"]),
    ("maternity", ["pmmvy"]),
    ("fasal bima", ["pmfby"]),
    ("crop insurance", ["pmfby"]),
    ("nrega kaam", ["mgnrega"]),
    ("majdoori", ["mgnrega"]),
    ("shouchalay", ["sbm_toilet"]),
    ("toilet chahiye", ["sbm_toilet"]),
    ("budhapa pension", ["old_age_pension"]),
    ("old age", ["old_age_pension"]),
    ("vidhwa pension", ["widow_pension"]),
    ("viklang pension", ["disability_pension"]),
    ("beti account", ["sukanya"]),
    ("sukanya", ["sukanya"]),
    ("shram card", ["eshram"]),
    ("e-shram", ["eshram"]),
    ("kisan credit card", ["kcc"]),
    ("kheti loan", ["kcc"]),
    ("mudra loan", ["mudra"]),
    ("business loan", ["mudra"]),
    ("handpump kharab", ["water_supply"]),
    ("paani nahi", ["water_supply"]),
    ("street light", ["streetlight"]),
    ("gali bulb", ["streetlight"]),
    ("sadak toot", ["road_repair"]),
    ("gali kichad", ["road_repair"]),
    ("naali overflow", ["drainage"]),
    ("sewage", ["drainage"]),
    ("awara janwar", ["stray_animals"]),
    ("stray dog", ["stray_animals"]),
    ("hello kaise ho", []),
    ("aaj mausam kaisa hai", []),
]

def tokenize(t): return re.findall(r'\w+', t.lower())
class PPC:
    def __init__(s): s.idf={}; s.cv={}; s.cl=set()
    def fit(s, ex):
        docs=[tokenize(t) for t,_ in ex]; labels=[l for _,l in ex]; s.cl={l for lbls in labels for l in lbls}
        df=Counter(); N=len(docs)
        for d in docs:
            for t in set(d): df[t]+=1
        s.idf={t: math.log((N+1)/(df[t]+1))+1 for t in df}; s.cv={c:Counter() for c in s.cl}; cc=Counter()
        for d, lbls in zip(docs, labels):
            tf=Counter(d); vec={t:tf[t]*s.idf[t] for t in tf}; n=math.sqrt(sum(v**2 for v in vec.values())) or 1.0; vec={t:v/n for t,v in vec.items()}
            for l in lbls:
                cc[l]+=1
                for t,v in vec.items(): s.cv[l][t]+=v
        for c in s.cl:
            cnt=cc[c] or 1; s.cv[c]={t:v/cnt for t,v in s.cv[c].items()}; n=math.sqrt(sum(v**2 for v in s.cv[c].values())) or 1.0; s.cv[c]={t:v/n for t,v in s.cv[c].items()}
    def predict(s, text):
        tokens=tokenize(text); tf=Counter(tokens); vec={t:tf[t]*s.idf.get(t,1.0) for t in tf}; n=math.sqrt(sum(v**2 for v in vec.values())) or 1.0; vec={t:v/n for t,v in vec.items()}
        scores={c: max(0.0, sum(vec.get(t,0)*cv.get(t,0) for t in set(vec)|set(cv))) for c,cv in s.cv.items()}; tot=sum(scores.values()) or 1.0; probs={c:sc/tot for c,sc in scores.items()}
        preds=[c for c,p in probs.items() if p>0.35] or ([max(scores, key=scores.get)] if scores else [])
        return {"labels": preds, "scores": {k:round(v,3) for k,v in probs.items()}}
_m=None
def get_m(): global _m; _m=_m or PPC(); _m.fit(TRAINING_EXAMPLES); return _m
def predict(t): return get_m().predict(t)
if __name__=='__main__': print(json.dumps(predict(sys.argv[1] if len(sys.argv)>1 else 'mudra loan chahiye'), indent=2))
