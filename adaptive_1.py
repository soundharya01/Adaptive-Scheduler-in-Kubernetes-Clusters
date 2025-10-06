import os
import json
import time
import csv
import subprocess

# Constants
IPMI_WORKER_IPS = {
    'kworker-sys-e300-8d': '192.168.100.12',
    'kworker2-sys-e300-8d': '192.168.100.11'
}
IPMI_USER = "ADMIN"
IPMI_PASSWORD = "admin"
EWMA_FILE = "ewma_metrics.json"
CSV_LOG_FILE = "node_threshold_metrics.csv"
EWMA_LOG_FILE = "ewma_values.csv"
KWORKER_LOG_FILE = "kworker_utilization.csv"
ALPHA = 0.4

# Thresholds per node
adaptive_thresholds = {}

# Utility functions
def load_json_file(filename):
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Reading {filename}: {e}")
    return []

def save_json_file(filename, data):
    try:
        with open(filename, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[ERROR] Writing {filename}: {e}")

def get_node_metrics():
    cpu_data = load_json_file("node_cpu.json")
    mem_data = load_json_file("node_memory.json")
    node_metrics = {}

    for item in cpu_data:
        node = item['metric'].get('node')
        if node:
            cpu = float(item['value'][1])
            node_metrics.setdefault(node, {})['cpu'] = cpu

    for item in mem_data:
        node = item['metric'].get('node')
        if node:
            memory = float(item['value'][1])
            node_metrics.setdefault(node, {})['memory'] = memory

    return node_metrics

def get_workload_pods():
    data = load_json_file("workload_pods.json")
    pods = {}
    for item in data:
        node = item['metric'].get('node')
        pod = item['metric'].get('pod')
        if node and pod:
            pods.setdefault(node, []).append(pod)
    return pods

def calculate_ewma(current, previous, bias=True, margin=5):
    ewma = ALPHA * current + (1 - ALPHA) * previous
    if bias and ewma < current:
        ewma = current + margin
    return ewma

def determine_thresholds(node, ewma_val):
    if node not in adaptive_thresholds:
        adaptive_thresholds[node] = {'upper': 50.0}

    if ewma_val >= 70:
        adaptive_thresholds[node]['upper'] *= 0.9
    else:
        adaptive_thresholds[node]['upper'] *= 1.1

    adaptive_thresholds[node]['upper'] = max(0, min(100, adaptive_thresholds[node]['upper']))

    return adaptive_thresholds[node]['upper']

def save_metrics_to_csv(filename, node, cpu_util, ewma_cpu, upper):
    file_exists = os.path.isfile(filename)
    with open(filename, mode='a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "Node", "CPU_Util", "EWMA_CPU", "Upper_Threshold"])
        writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), node, f"{cpu_util:.2f}", f"{ewma_cpu:.2f}", f"{upper:.2f}"])

def log_ewma_values(filename, node, ewma):
    file_exists = os.path.isfile(filename)
    with open(filename, mode='a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "Node", "EWMA_CPU"])
        writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), node, f"{ewma:.2f}"])

def log_kworker_utilization(filename, node, cpu):
    file_exists = os.path.isfile(filename)
    with open(filename, mode='a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "Node", "CPU_Util"])
        writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), node, f"{cpu:.2f}"])

def label_node(node_name, label_value):
    try:
        subprocess.run(
            ["kubectl", "label", "node", node_name, f"usage={label_value}", "--overwrite"],
            check=True, capture_output=True, text=True
        )
        print(f"[LABEL] {node_name} → usage={label_value}")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Labeling node {node_name}: {e.stderr.strip()}")

def is_node_powered_on(node_name):
    ipmi_ip = IPMI_WORKER_IPS.get(node_name)
    if ipmi_ip:
        try:
            result = subprocess.run(
                ["ipmitool", "-I", "lanplus", "-H", ipmi_ip, "-U", IPMI_USER, "-P", IPMI_PASSWORD, "chassis", "power", "status"],
                capture_output=True, text=True, timeout=5
            )
            return "on" in result.stdout.lower()
        except Exception as e:
            print(f"[ERROR] Checking power state for {node_name}: {e}")
    return False

def power_on_node(node_name):
    ipmi_ip = IPMI_WORKER_IPS.get(node_name)
    if ipmi_ip:
        try:
            subprocess.run(
                ["ipmitool", "-I", "lanplus", "-H", ipmi_ip, "-U", IPMI_USER, "-P", IPMI_PASSWORD, "chassis", "power", "on"],
                check=True, capture_output=True, text=True
            )
            print(f"[POWER ON] Powered on {node_name} (IP: {ipmi_ip})")
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Powering on {node_name}: {e.stderr.strip()}")

def power_off_node(node_name):
    ipmi_ip = IPMI_WORKER_IPS.get(node_name)
    if ipmi_ip:
        try:
            subprocess.run(
                ["ipmitool", "-I", "lanplus", "-H", ipmi_ip, "-U", IPMI_USER, "-P", IPMI_PASSWORD, "chassis", "power", "off"],
                check=True, capture_output=True, text=True
            )
            print(f"[POWER OFF] Powered off {node_name} (IP: {ipmi_ip})")
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Powering off {node_name}: {e.stderr.strip()}")

def manage_alternative_nodes(target_nodes, alternative_nodes, ewma_metrics):
    if not target_nodes:
        print("[INFO] No target nodes found, skipping power management.")
        return

    workload_pods = get_workload_pods()
    target_node = target_nodes[0]
    target_ewma = ewma_metrics.get(target_node, {'cpu': 0, 'memory': 0})
    upper = determine_thresholds(target_node, target_ewma['cpu'])

    print(f"[MANAGE] Target node {target_node} EWMA_CPU={target_ewma['cpu']:.2f} UPPER={upper:.2f}")

    if target_ewma['cpu'] >= 60 or target_ewma['memory'] >= 60:
        if alternative_nodes:
            first_alt_node, _ = alternative_nodes[0]
            if not is_node_powered_on(first_alt_node):
                print(f"[ACTION] Turning on powered-off alternative node: {first_alt_node}")
                power_on_node(first_alt_node)
            label_node(first_alt_node, "active")
            target_nodes.append(first_alt_node)
    else:
        for node, _ in alternative_nodes:
            if not workload_pods.get(node, []) and is_node_powered_on(node):
                print(f"[ACTION] Alternative node {node} has no workload pods, powering off.")
                power_off_node(node)
                label_node(node, "wait")

def label_nodes_based_on_usage():
    ewma_metrics = {}
    if os.path.exists(EWMA_FILE):
        try:
            with open(EWMA_FILE, 'r') as f:
                ewma_metrics = json.load(f)
        except Exception as e:
            print(f"[ERROR] Loading EWMA metrics: {e}")

    node_metrics = get_node_metrics()
    valid_nodes = {node: metrics for node, metrics in node_metrics.items()
                   if metrics.get('cpu', -1) >= 0 and metrics.get('memory', -1) >= 0 and "master" not in node}

    powered_off_nodes = [node for node in IPMI_WORKER_IPS.keys() if node not in valid_nodes]

    updated_ewma = {}
    alternative_nodes = []
    target_nodes = []

    for node, metrics in valid_nodes.items():
        cpu = metrics.get('cpu', 0)
        mem = metrics.get('memory', 0)
        prev = ewma_metrics.get(node, {'cpu': cpu, 'memory': mem})
        ewma_cpu = calculate_ewma(cpu, prev.get('cpu', cpu))
        ewma_mem = calculate_ewma(mem, prev.get('memory', mem))
        updated_ewma[node] = {'cpu': ewma_cpu, 'memory': ewma_mem}

        upper = determine_thresholds(node, ewma_cpu)
        save_metrics_to_csv(CSV_LOG_FILE, node, cpu, ewma_cpu, upper)
        log_ewma_values(EWMA_LOG_FILE, node, ewma_cpu)
        log_kworker_utilization(KWORKER_LOG_FILE, node, cpu)

        print(f"[METRICS] {node}: CPU={cpu:.2f}%, EWMA_CPU={ewma_cpu:.2f}% | Mem={mem:.2f}%, EWMA_MEM={ewma_mem:.2f}%")
        print(f"[THRESHOLDS] {node}: UPPER={upper:.2f}")

        if ewma_cpu >= upper or ewma_mem >= upper:
            label_node(node, "high")
        else:
            alternative_nodes.append((node, metrics))

    alternative_nodes = sorted(alternative_nodes, key=lambda x: (x[1]['cpu'], x[1]['memory']), reverse=True)
    print(f"[SORTED ALTERNATIVES] {[node for node, _ in alternative_nodes]}")

    for node in powered_off_nodes:
        alternative_nodes.append((node, None))

    if alternative_nodes:
        target_node, target_metrics = alternative_nodes.pop(0)
        if not is_node_powered_on(target_node):
            print(f"[POWER] Node {target_node} is powered off, turning it on.")
            power_on_node(target_node)
        label_node(target_node, "active")
        target_nodes.append(target_node)
        for node, _ in alternative_nodes:
            label_node(node, "wait")

    print(f"[TARGETS] Active Nodes: {target_nodes}")
    print(f"[ALTERNATIVES] Remaining: {[node for node, _ in alternative_nodes]}")

    manage_alternative_nodes(target_nodes, alternative_nodes, updated_ewma)
    save_json_file(EWMA_FILE, updated_ewma)

if __name__ == "__main__":
    while True:
        print("\n[INFO] Running Kubernetes power management logic...\n")
        label_nodes_based_on_usage()
        time.sleep(60)
