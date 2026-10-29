import yaml
import os

def load_yaml(file_path):
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)

def compute_stall_reject_rates(ledger_rows):
    # Placeholder for the real stall/reject rates computation
    # This should be replaced with the actual computation
    stall_rates = {"desk1": 0.1, "desk2": 0.2, "desk3": 0.3}  # Example stall rates
    reject_rates = {"desk1": 0.05, "desk2": 0.1, "desk3": 0.15}  # Example reject rates
    return stall_rates, reject_rates

def flag_risk(stall_rates, reject_rates):
    flags = {}
    for desk, stall_rate in stall_rates.items():
        if stall_rate > 0.2:
            flags[desk] = "HIGH RISK"
        elif stall_rate > 0.1:
            flags[desk] = "CRITICAL RISK"
    for desk, reject_rate in reject_rates.items():
        if reject_rate > 0.1:
            flags[desk] = "HIGH RISK"
        elif reject_rate > 0.05:
            flags[desk] = "CRITICAL RISK"
    return flags

def main():
    yaml_files = [f for f in os.listdir('rulepack/routes') if f.endswith('.yaml')]
    for yaml_file in yaml_files:
        file_path = os.path.join('rulepack/routes', yaml_file)
        data = load_yaml(file_path)
        clock = data.get('clock')
        desk = data.get('desk')
        print(f"Using clock: {clock}, desk: {desk}")

    ledger_rows = []  # Placeholder for ledger rows, should be populated from actual ledger
    stall_rates, reject_rates = compute_stall_reject_rates(ledger_rows)
    flags = flag_risk(stall_rates, reject_rates)
    for desk, flag in flags.items():
        print(f"Desk: {desk}, Flag: {flag}")

if __name__ == '__main__':
    main()
