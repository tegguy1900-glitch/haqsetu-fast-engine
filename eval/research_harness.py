"""
HaqSetu SELECTIVE-PREDICTION EVALUATION HARNESS (research layer)
Staged v0 data -> conformal-style quantile calibration on a held-out split ->
risk-coverage curve, macro-F1, confusion matrix, Wilson 95% CIs, AURC, baselines.
If eval/test_set.csv exists (lines: text,label) it is used instead of the generator.
Outputs: eval/results.json, eval/risk_coverage.svg, eval/confusion_matrix.csv
"""
import json, math, os, random, sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "triage"))
import baselines

CLASSES = ["crop_loss","wage_work","grievance","pm_awas","ujjwala","water_supply","streetlight","mudra"]
TEMPLATES = {
 "crop_loss": ["{crop} ki fasal {cause} {dhi} ho gayi","my {crop} crop was {den} by {causee}","khet mein {crop} {dhi} ho gaya"],
 "wage_work": ["majdoori ka kaam {days} din se nahi mila","job card hai par kaam {days} din se band hai","nrega payment {days} din se pending hai"],
 "grievance": ["pension {months} mahine se nahi aayi","ration shop mein {months} mahine se quota nahi mila","patwari {months} mahine se certificate nahi de raha"],
 "pm_awas": ["{months} mahine se awas yojana ka intezar","pucca makan ke liye {months} mahine se apply kiya","awas yojana form {months} mahine se pending hai"],
 "ujjwala": ["gas cylinder {months} mahine se nahi mila","ujjwala connection {months} mahine se pending","chulhe ka dhuaan {months} mahine se jhel raha hoon"],
 "water_supply": ["handpump {days} din se kharab hai","pipe se paani {days} din se nahi aaya","borewell {days} din se band pada hai"],
 "streetlight": ["gali ka bulb {days} din se fuse hai","street light {days} din se nahi jali","lamp post {days} din se kharab hai"],
 "mudra": ["dukaan ke liye mudra loan {months} mahine se ruka","mudra loan application {months} mahine se pending","business loan {months} mahine se nahi mila"],
}
OTHER = ["gaon mein cinema hall banwao","aaj mausam kaisa rahega","cricket match ka score batao","movie ticket chahiye","dukaan ka bill print karo"]
FILLER = ["sahab,","bhaiya,","please,","sunijiye,"]

def make_set(seed, per=30):
    rng = random.Random(seed); out = []
    for c in CLASSES:
        for _ in range(per):
            t = rng.choice(TEMPLATES[c])
            t = t.format(crop=rng.choice(["gehu","wheat","rice","bajra"]),
                         cause=rng.choice(["ola se","baadh se","heavy rain se","storm se"]),
                         causee=rng.choice(["hail","flood","heavy rain","storm"]),
                         dhi=rng.choice(["kharab","barbad","khtam"]),
                         den=rng.choice(["destroyed","ruined","wiped out"]),
                         days=rng.choice([3,5,7,10,15,20,25,40]),
                         months=rng.choice([2,3,4,6,8,12]))
            if rng.random() < 0.3: t = rng.choice(FILLER) + " " + t
            out.append((t, c))
    for _ in range(per):
        out.append((rng.choice(OTHER), "other"))
    rng.shuffle(out); return out

def load_or_generate():
    csv = os.path.join(ROOT, "eval", "test_set.csv")
    if os.path.exists(csv):
        rows = [l.strip().split(",") for l in open(csv, encoding="utf-8") if l.strip()]
        data = [(t, l) for t, l in rows]
        rng = random.Random(0); rng.shuffle(data)
        k = len(data) // 3
        return data[:k], data[k:], "REAL VOLUNTEER CSV"
    return make_set(101, 25), make_set(202, 35), "STAGED v0 (synthetic paraphrases)"

def conf_of(text):
    r = baselines.predict(text)
    s = r.get("scores") or {}
    if not s: return 0.0, "none"
    lab = max(s, key=s.get); return s[lab], lab

def wilson(success, total, z=1.96):
    if total <= 0: return (0.0, 0.0)
    p = success / total; z2 = z * z; den = 1 + z2 / total
    c = (p + z2 / (2 * total)) / den
    m = (z / den) * math.sqrt(p * (1 - p) / total + z2 / (4 * total * total))
    return (max(0.0, c - m), min(1.0, c + m))

def evaluate(test, threshold=None):
    cov_n = err_n = 0; cm = Counter(); preds_by_class = {c: [0, 0] for c in CLASSES}
    for text, true in test:
        cf, lab = conf_of(text)
        if threshold is not None and cf < threshold:
            cm[(true, "ABSTAIN")] += 1; continue
        cov_n += 1
        if lab != true: err_n += 1
        cm[(true, lab)] += 1
        if true in preds_by_class: preds_by_class[true][0] += (lab == true); preds_by_class[true][1] += 1
        if lab in preds_by_class: preds_by_class[lab][0] += (lab == true); preds_by_class[lab][1] += 1
    risk = err_n / cov_n if cov_n else 0.0
    lo, hi = wilson(cov_n - err_n, cov_n)
    f1s = []
    for c in CLASSES:
        tp = cm[(c, c)]; fp = sum(v for (t, p), v in cm.items() if p == c and t != c)
        fn = sum(v for (t, p), v in cm.items() if t == c and p != c)
        pr = tp / (tp + fp) if tp + fp else 0.0; rc = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * pr * rc / (pr + rc) if pr + rc else 0.0)
    return {"coverage": cov_n / len(test), "risk": risk, "risk_ci": (1 - hi, 1 - lo),
            "macro_f1": sum(f1s) / len(f1s), "cm": cm, "n_covered": cov_n}

def calibrate(cal, alpha=0.10):
    scores = sorted(conf_of(t)[0] for t, _ in cal)
    q = min(max(math.ceil((len(scores) + 1) * (1 - alpha)), 1), len(scores))
    return scores[q - 1]

def curve_points(test):
    confs = sorted({round(conf_of(t)[0], 4) for t, _ in test}, reverse=True)
    pts = []
    for t in confs:
        e = evaluate(test, threshold=t)
        pts.append((e["coverage"], e["risk"]))
    return pts

def aurc(pts):
    pts = sorted(pts); a = pts[0][0] * pts[0][1]
    for i in range(1, len(pts)):
        a += (pts[i][0] - pts[i-1][0]) * (pts[i][1] + pts[i-1][1]) / 2
    return a

KW = [("crop_loss", ["fasal","crop","khet"]), ("wage_work", ["majdoori","nrega","job card"]),
      ("grievance", ["pension","ration","patwari"]), ("pm_awas", ["awas","makan"]),
      ("ujjwala", ["gas","ujjwala","cylinder"]), ("water_supply", ["handpump","paani","pipe"]),
      ("streetlight", ["bulb","light","lamp"]), ("mudra", ["mudra","loan"])]
def kw_predict(text):
    t = text.lower()
    for c, kws in KW:
        if any(k in t for k in kws): return c
    return "other"

def svg_curve(pts, op, out):
    W, H, ML, MB = 720, 460, 60, 50
    X = lambda c: ML + c * (W - ML - 20); Y = lambda r: 20 + r * (H - MB - 20) / max(0.5, max(p[1] for p in pts))
    path = " ".join(f"{'M' if i==0 else 'L'}{X(c):.1f},{Y(r):.1f}" for i, (c, r) in enumerate(sorted(pts)))
    s = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}'><rect width='{W}' height='{H}' fill='#0f172a'/>",
         f"<text x='{ML}' y='20' fill='#38bdf8' font-family='monospace' font-size='15'>HaqSetu Risk-Coverage (selective prediction)</text>",
         f"<line x1='{ML}' y1='{Y(0)}' x2='{W-20}' y2='{Y(0)}' stroke='#334155'/><line x1='{ML}' y1='20' x2='{ML}' y2='{Y(0)}' stroke='#334155'/>",
         f"<path d='{path}' fill='none' stroke='#10b981' stroke-width='2.5'/>",
         f"<circle cx='{X(op['coverage'])}' cy='{Y(op['risk'])}' r='6' fill='#f59e0b'/>",
         f"<text x='{X(op['coverage'])+10}' y='{Y(op['risk'])-8}' fill='#f59e0b' font-family='monospace' font-size='12'>operating point a=0.10</text>",
         f"<text x='{ML}' y='{H-15}' fill='#94a3b8' font-family='monospace' font-size='12'>coverage -></text>",
         f"<text x='12' y='{H//2}' fill='#94a3b8' font-family='monospace' font-size='12' transform='rotate(-90 12 {H//2})'>risk (misroute) -></text></svg>"]
    open(out, "w", encoding="utf-8").write("".join(s))

if __name__ == "__main__":
    cal, test, source = load_or_generate()
    t_star = calibrate(cal, 0.10)
    op = evaluate(test, t_star)
    noab = evaluate(test, None)
    kw_err = sum(1 for x, y in test if kw_predict(x) != y)
    kw = {"coverage": 1.0, "risk": kw_err / len(test), "risk_ci": wilson(len(test) - kw_err, len(test))}
    pts = curve_points(test)
    outdir = os.path.join(ROOT, "eval")
    svg_curve(pts, op, os.path.join(outdir, "risk_coverage.svg"))
    with open(os.path.join(outdir, "confusion_matrix.csv"), "w", encoding="utf-8") as f:
        cols = CLASSES + ["other", "ABSTAIN"]
        f.write("true," + ",".join(cols) + "\n")
        for tr in CLASSES + ["other"]:
            f.write(tr + "," + ",".join(str(op["cm"].get((tr, p), 0)) for p in cols) + "\n")
    for e in (op, noab):
        e["cm"] = {f"{a}>>{b}": v for (a, b), v in e["cm"].items()}
    results = {"data_source": source, "n_cal": len(cal), "n_test": len(test),
               "threshold": t_star, "operating": op, "tfidf_no_abstain": noab,
               "keyword_rules": kw, "aurc": aurc(pts)}
    json.dump(results, open(os.path.join(outdir, "results.json"), "w"), indent=2, default=str)
    print(f"DATA: {source} | cal n={len(cal)} test n={len(test)}")
    print(f"conformal threshold (alpha=0.10): {t_star:.3f}")
    print(f"{'method':<20}{'coverage':>10}{'risk':>8}{'risk 95% CI':>18}{'macroF1':>9}")
    def ci_str(ci):
        return f"{ci[0]:.1%}-{ci[1]:.1%}"
    kw_ci, noab_ci, op_ci = ci_str(kw["risk_ci"]), ci_str(noab["risk_ci"]), ci_str(op["risk_ci"])
    print(f"{'keyword_rules':<20}{1.0:>10.1%}{kw['risk']:>8.1%}{kw_ci:>18}{'-':>9}")
    print(f"{'tfidf_no_abstain':<20}{noab['coverage']:>10.1%}{noab['risk']:>8.1%}{noab_ci:>18}{noab['macro_f1']:>9.3f}")
    print(f"{'tfidf_conformal':<20}{op['coverage']:>10.1%}{op['risk']:>8.1%}{op_ci:>18}{op['macro_f1']:>9.3f}")
    print(f"AURC {aurc(pts):.4f} | abstain rate {1-op['coverage']:.1%} (routed to human, NEVER denied)")
    print("wrote eval/risk_coverage.svg, eval/confusion_matrix.csv, eval/results.json")