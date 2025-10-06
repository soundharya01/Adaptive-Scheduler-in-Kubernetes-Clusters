import requests
import json
import tempfile
import shutil
import os

PROMETHEUS_URL = "http://161.200.90.106:32090/api/v1/query"

def safe_write_json(filename, data):
    try:
        temp_file = tempfile.NamedTemporaryFile("w", delete=False, dir=".")
        json.dump(data, temp_file, indent=2)
        temp_file.close()
        shutil.move(temp_file.name, filename)
    except Exception as e:
        print(f"Failed to write {filename}: {e}")

def query_prometheus(query):
    try:
        response = requests.get(PROMETHEUS_URL, params={"query": query})
        response.raise_for_status()
        return response.json()["data"]["result"]
    except Exception as e:
        print(f"Prometheus query failed: {e}")
        return []

def merge_usage_and_request(usage_data, request_data):
    merged = []
    request_map = {}

    # Build request lookup
    for item in request_data:
        pod = item["metric"].get("pod")
        namespace = item["metric"].get("namespace")
        if not pod or not namespace:
            continue
        try:
            value = float(item["value"][1])
        except:
            value = 0
        request_map[(namespace, pod)] = value

    # Merge usage and request
    for item in usage_data:
        metric = item.get("metric", {})
        pod = metric.get("pod")
        namespace = metric.get("namespace")
        node = metric.get("node")

        if not pod or not namespace or not node:
            continue

        try:
            usage_value = float(item["value"][1])
        except:
            usage_value = 0

        cpu_request = request_map.get((namespace, pod), 0)

        merged.append({
            "metric": {
                "node": node,
                "pod": pod,
                "namespace": namespace,
                "cpu_request": cpu_request
            },
            "value": [item["value"][0], usage_value]
        })

    return merged

if __name__ == "__main__":
    os.chdir("/home/k-master/prom_matrix/cronjob")  # Correct working directory

    # 1. Pod CPU usage
    cpu_usage_query = '''
        sum(rate(container_cpu_usage_seconds_total{
            job="kubelet",
            image!="",
            container!="",
            namespace!~"^(kube-system|monitoring)$",
            pod!~"^(kepler|prometheus|grafana|alertmanager|kube-proxy|kube-apiserver|kube-scheduler|kube-controller-manager|etcd)(-|$)"
        }[1m])) by (node, pod, namespace)
    '''
    usage_data = query_prometheus(cpu_usage_query)

    # 2. Pod CPU requests
    cpu_request_query = '''
        sum(kube_pod_container_resource_requests_cpu_cores{
            namespace!~"^(kube-system|monitoring)$"
        }) by (pod, namespace)
    '''
    request_data = query_prometheus(cpu_request_query)

    # Merge and save
    merged_data = merge_usage_and_request(usage_data, request_data)
    safe_write_json("pod_cpu_usage.json", merged_data)

    # 3. Node CPU %
    cpu_percentage_query = '''
        100 * sum(rate(container_cpu_usage_seconds_total{job="kubelet", mode!="idle", image!="", pod!=""}[1m])) by (node) 
        / sum(machine_cpu_cores{job="kubelet"}) by (node)
    '''
    cpu_data = query_prometheus(cpu_percentage_query)
    safe_write_json("node_cpu.json", cpu_data)

    # 4. Node Memory %
    memory_percentage_query = '''
        100 * sum(container_memory_usage_bytes{job="kubelet", image!="", pod!=""}) by (node)
        / sum(machine_memory_bytes{job="kubelet"}) by (node)
    '''
    memory_data = query_prometheus(memory_percentage_query)
    safe_write_json("node_memory.json", memory_data)

    # 5. Workload Pods
    workload_pods_query = '''
        kube_pod_info{
            created_by_kind!="DaemonSet",
            namespace!~"^(kube-system|monitoring)$",
            pod!~"^(kepler|prometheus|kube-proxy|kube-apiserver|kube-scheduler|kube-controller-manager|etcd)"
        }
    '''
    workload_data = query_prometheus(workload_pods_query)
    safe_write_json("workload_pods.json", workload_data)
