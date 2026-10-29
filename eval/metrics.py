import math
import json

def wilson_interval(successes, total, z=1.96):
    """
    Calculates the 95% Wilson score interval.
    This is the honest way to report accuracy on small datasets.
    """
    if total <= 0:
        return {"lower": 0.0, "upper": 0.0, "center": 0.0}

    p_hat = successes / total
    z2 = z * z

    denominator = 1 + z2 / total
    centre = (p_hat + z2 / (2 * total)) / denominator
    margin = (z / denominator) * math.sqrt(
        (p_hat * (1 - p_hat) / total) + (z2 / (4 * total * total))
    )

    lower = max(0.0, centre - margin)
    upper = min(1.0, centre + margin)

    return {
        "lower": round(lower, 3),
        "upper": round(upper, 3),
        "center": round(centre, 3),
        "successes": successes,
        "total": total
    }

if __name__ == "__main__":
    # Simulate a small pilot test: 8 out of 10 cases routed correctly
    correct = 8
    total = 10
    
    interval = wilson_interval(correct, total)
    
    report = {
        "metric": "Triage Accuracy (Small Pilot)",
        "raw_accuracy": f"{correct}/{total} ({correct/total*100}%)",
        "honest_95_percent_interval": f"{interval['lower']*100}% to {interval['upper']*100}%",
        "wilson_data": interval,
        "note": "We report intervals, not absolute bounds, because our pilot dataset is small."
    }
    
    print(json.dumps(report, indent=2))