import yaml
import os

def load_yaml(file_path):
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)

def handle_grievance(utterance):
    if not utterance.strip():
        return "Abstain"

    grievance_types = ["handpump", "drain", "road"]
    if utterance in grievance_types:
        return "OPEN civic_intake case for grievance"
    else:
        return "Invalid grievance type"

def main():
    yaml_files = [f for f in os.listdir('rulepack/routes') if f.endswith('.yaml')]
    for yaml_file in yaml_files:
        file_path = os.path.join('rulepack/routes', yaml_file)
        data = load_yaml(file_path)
        clock = data.get('clock')
        desk = data.get('desk')
        print(f"Using clock: {clock}, desk: {desk}")

    utterance = "hardcoded_demo_string"
    result = handle_grievance(utterance)
    print(result)

if __name__ == '__main__':
    main()
