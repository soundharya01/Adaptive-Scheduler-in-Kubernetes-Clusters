# ⚙️ Adaptive Energy-Efficient Kubernetes Scheduler

## 🧩 Overview
This project introduces a **custom adaptive scheduler** for Kubernetes that improves **energy efficiency** by dynamically powering cluster nodes **on or off** based on **real-time workload thresholds**.

Instead of keeping all worker nodes running continuously, the scheduler:
- Monitors **Prometheus metrics** and **pod CPU requests**  
- Uses **adaptive thresholding** to decide when to scale nodes up or down  
- Reduces **idle resource consumption** while maintaining **balanced workload distribution**

---

## 🔍 Key Features
- ✅ **Dynamic Node Power Management:** Automatically powers nodes on/off based on cluster workload.  
- 📊 **Prometheus Integration:** Collects live CPU and resource utilization metrics.  
- ⚖️ **Adaptive Thresholding:** Continuously adjusts scheduling thresholds to match workload changes.  
- 🧠 **Smart Scheduling:** Custom Python logic extending Kubernetes’ default scheduler.   

---

## 🧱 Architecture Overview
      ![Architecture Diagram](./images/architecture.png)
  

---

## 🧠 How It Works
1. **Prometheus** gathers CPU and resource usage metrics from all nodes.  
2. **Custom Scheduler (Python)** listens for unscheduled pods from the API Server.  
3. Based on adaptive thresholds and available resources, it:  
   - Powers on new nodes when workload increases  
   - Powers off idle nodes when usage drops  
4. Results are visualized in **Grafana dashboards**.  

---

## ⚙️ Tools & Technologies
- **Kubernetes**
- **Docker**
- **Prometheus**
- **Grafana**
- **Python (Custom Scheduler Logic)**
- **Bash**

