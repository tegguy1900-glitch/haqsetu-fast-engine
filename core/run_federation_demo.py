import yaml
import os

def load_yaml(file_path):
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)

def verify_village_chain(village_chain):
    # Placeholder for the real verification logic
    # This should be replaced with the actual verification logic
    return True

def aggregate_district(village_chains):
    aggregated_data = {}
    for chain in village_chains:
        for key, value in chain.items():
            if key in aggregated_data:
                aggregated_data[key] += value
            else:
                aggregated_data[key] = value

    # Suppress small-cell data (<5)
    for key in list(aggregated_data.keys()):
        if aggregated_data[key] < 5:
            del aggregated_data[key]

    return aggregated_data

def main():
    yaml_files = [f for f in os.listdir('rulepack/routes') if f.endswith('.yaml')]
    for yaml_file in yaml_files:
        file_path = os.path.join('rulepack/routes', yaml_file)
        data = load_yaml(file_path)
        clock = data.get('clock')
        desk = data.get('desk')
        print(f"Using clock: {clock}, desk: {desk}")

    # Placeholder for village chains, should be populated from actual data
    village_chains = [
        {"chain1": 10, "chain2": 3},
        {"chain1": 5, "chain3": 7},
        {"chain2": 2, "chain3": 8}
    ]

    for chain in village_chains:
        if not verify_village_chain(chain):
            print("Forged row rejected")
            return

    aggregated_data = aggregate_district(village_chains)
    print("Aggregated Data:", aggregated_data)

if __name__ == '__main__':
    main()
