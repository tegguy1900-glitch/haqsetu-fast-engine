import csv
import random

# Define base templates and synonym pools
TEMPLATES = {
    "MGNREGA": [
        "Main {name} hoon kaam dhund raha hoon",
        "Mujhe job chahiye sarkari scheme se",
        "I want employment under MGNREGA act",
        "Gaon mein koi work nahi mil raha hai",
        "Need work under Mahatma Gandhi National Rural Employment Guarantee Act",
        "Job card banwana hai MGNREGA ke liye",
        "Rozgar mangta hoon gaon walo ke liye",
        "Unemployment relief scheme apply karna hai"
    ],
    "OLD_AGE_PENSION": [
        "Meri pension ruki hui hai",
        "Mujhe budhape ki pension deni hai",
        "Senior citizen allowance apply karna hai",
        "Old age support fund claim karna hai",
        "Retirement benefit scheme registration",
        "Vruddh avastha bhatta chahiye",
        "Age pension application submit karo",
        "Elderly care subsidy needed"
    ],
    "VIDHWA_PENSION": [
        "Pati ki death ho gayi ab vidhwa pension chahiye",
        "My husband died I need widow support",
        "Widow certificate ke liye kya karun",
        "Mera pati mar gaya hai ab mujhe kaise guzara karna hai",
        "Patni ki mrityu ke baad alimony chahiye", # Note: Usually widower/wife context varies but logic holds
        "Husband expired wife pension claim",
        "Vidhva bhatta prapt karna hai",
        "Spouse deceased financial assistance required",
        "Kanya vivah ke baad patni ka nirvahana", 
        "Dependent spouse welfare scheme"
    ],
    "INFRA_BROKEN": [
        "Handpump toot gaya paani nahi aa raha",
        "Sarak par bada gaddha hai accident hogaya",
        "Street light jalna band hai raat ko andhera",
        "Grievance register karna hai infrastructure issue",
        "Road damaged near school area",
        "Water pipeline burst in ward 4",
        "Public toilet broken cleaning needed",
        "Drainage overflow causing smell",
        "Power cut frequent in our colony",
        "Bridge railing broken dangerous crossing"
    ]
}

def generate_dataset(filename="data/training_set_large.csv"):
    rows = []
    
    # Generate combinations
    for intent, templates in TEMPLATES.items():
        for template in templates:
            # Add original
            rows.append({"text": template, "intent": intent})
            
            # Add slight variations (random word swaps if applicable, though static list is safer for demo)
            # For this script, we rely on the diversity of the templates provided above.
            pass
            
    # Shuffle slightly to avoid bias during training
    random.shuffle(rows)
    
    with open(filename, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["text", "intent"])
        writer.writeheader()
        writer.writerows(rows)
        
    print(f"✅ Generated {len(rows)} training samples in {filename}")

if __name__ == "__main__":
    generate_dataset()
