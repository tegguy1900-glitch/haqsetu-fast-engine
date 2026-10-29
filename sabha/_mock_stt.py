import sys, json
sys.stdin.buffer.read()  # consume the staged "audio" bytes (content irrelevant here)
segs = [
    {"speaker": None,        "text": "The handpump in Ward 9 has been broken, no water."},
    {"speaker": "Secretary",  "text": "I will repair the road near school by Monday."},
]
print(json.dumps(segs))
