import yaml
import glob

files = glob.glob('rulepack/schemes/*.yaml') + glob.glob('rulepack/routes/*.yaml')

for f in files:
    try:
        with open(f, encoding='utf-8') as file:
            data = yaml.safe_load(file)
        
        if not isinstance(data, dict):
            print(f"❌ BROKEN FILE: {f} (It is a {type(data).__name__} instead of a dict)")
        else:
            print(f"✅ OK: {f}")
    except Exception as e:
        print(f"⚠️ ERROR READING {f}: {str(e)}")