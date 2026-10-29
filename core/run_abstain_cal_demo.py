import yaml
import os

def load_yaml(file_path):
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)

def calculate_confidence(utterance):
    # Placeholder for the real confidence formula
    # This should be replaced with the actual formula
    confidence = 0.8  # Example confidence value
    return confidence

def determine_action(confidence, slots):
    threshold = 0.7  # Example threshold value
    if confidence >= threshold:
        return "accept"
    elif confidence >= 0.5:
        return "one-question"
    else:
        return "abstain"

def main():
    yaml_files = [f for f in os.listdir('rulepack/routes') if f.endswith('.yaml')]
    for yaml_file in yaml_files:
        file_path = os.path.join('rulepack/routes', yaml_file)
        data = load_yaml(file_path)
        clock = data.get('clock')
        desk = data.get('desk')
        print(f"Using clock: {clock}, desk: {desk}")

    utterance = "hardcoded_demo_string"
    slots = {}  # Placeholder for slots, should be populated from actual slots
    confidence = calculate_confidence(utterance)
    action = determine_action(confidence, slots)
    print(f"Action: {action}")

if __name__ == '__main__':
    main()
