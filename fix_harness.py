import io
p = "eval/research_harness.py"
src = io.open(p, encoding="utf-8").read().replace("\r\n", "\n")
old = r'''    print(f"{'keyword_rules':<20}{1.0:>10.1%}{kw['risk']:>8.1%}{f\"{kw['risk_ci'][0]:.1%}-{kw['risk_ci'][1]:.1%}\":>18}{'-':>9}")
    print(f"{'tfidf_no_abstain':<20}{noab['coverage']:>10.1%}{noab['risk']:>8.1%}{f\"{noab['risk_ci'][0]:.1%}-{noab['risk_ci'][1]:.1%}\":>18}{noab['macro_f1']:>9.3f}")
    print(f"{'tfidf_conformal':<20}{op['coverage']:>10.1%}{op['risk']:>8.1%}{f\"{op['risk_ci'][0]:.1%}-{op['risk_ci'][1]:.1%}\":>18}{op['macro_f1']:>9.3f}")'''
new = '''    def ci_str(ci):
        return f"{ci[0]:.1%}-{ci[1]:.1%}"
    kw_ci, noab_ci, op_ci = ci_str(kw["risk_ci"]), ci_str(noab["risk_ci"]), ci_str(op["risk_ci"])
    print(f"{'keyword_rules':<20}{1.0:>10.1%}{kw['risk']:>8.1%}{kw_ci:>18}{'-':>9}")
    print(f"{'tfidf_no_abstain':<20}{noab['coverage']:>10.1%}{noab['risk']:>8.1%}{noab_ci:>18}{noab['macro_f1']:>9.3f}")
    print(f"{'tfidf_conformal':<20}{op['coverage']:>10.1%}{op['risk']:>8.1%}{op_ci:>18}{op['macro_f1']:>9.3f}")'''
if old in src:
    io.open(p, "w", encoding="utf-8").write(src.replace(old, new))
    print("PATCHED OK")
else:
    print("OLD BLOCK NOT FOUND - tell me and I will give manual lines")