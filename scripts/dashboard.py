import matplotlib.pyplot as plt
import json
import os
import glob

REPORTS_DIR = 'reports'
report_files = glob.glob(os.path.join(REPORTS_DIR, '*_daily_report.json'))
if not report_files:
    raise FileNotFoundError(f"No file found inside {REPORTS_DIR}/")

latest_report = max(report_files, key=os.path.getctime)
print(f"Reading data: {latest_report}")

with open(latest_report, 'r') as f:
    data = json.load(f)
funcs = data['functions']

labels = ['Java 21', 'Rust']
cold_starts = [
    funcs['java_function']['cloudwatch']['cold_start_ms']['avg'],
    funcs['rust_function']['cloudwatch']['cold_start_ms']['avg']
]
p99_duration = [
    funcs['java_function']['cloudwatch']['duration_ms']['p99'],
    funcs['rust_function']['cloudwatch']['duration_ms']['p99']
]
memory_peak = [
    funcs['java_function']['cloudwatch']['memory_used_mb']['max'],
    funcs['rust_function']['cloudwatch']['memory_used_mb']['max']
]

plt.style.use('default')
fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(15, 5))
fig.suptitle('AWS Lambda: Java 21 vs Rust Benchmark', fontsize=18, fontweight='bold', color='#FF9900')
colors = ['#ED8B00', '#DEA584']


# Cold Starts
ax1.bar(labels, cold_starts, color=colors, width=0.6)
ax1.set_title('Avg Cold Start (ms)', fontsize=14)
ax1.set_ylabel('Milliseconds')
ax1.set_ylim(0, max(cold_starts) * 1.2) 
for i, v in enumerate(cold_starts):
    ax1.text(i, v + (max(cold_starts) * 0.03), f"{v} ms", ha='center', fontweight='bold')

# Tail Latency (p99)
ax2.bar(labels, p99_duration, color=colors, width=0.6)
ax2.set_title('p99 Execution Tail Latency (ms)', fontsize=14)
ax2.set_ylim(0, max(p99_duration) * 1.2) 
for i, v in enumerate(p99_duration):
    ax2.text(i, v + (max(p99_duration) * 0.03), f"{v} ms", ha='center', fontweight='bold')

# Memory Usage
ax3.bar(labels, memory_peak, color=colors, width=0.6)
ax3.set_title('Peak Memory Usage (MB)', fontsize=14)
ax3.set_ylabel('Megabytes')
ax3.set_ylim(0, max(memory_peak) * 1.2) 
for i, v in enumerate(memory_peak):
    ax3.text(i, v + (max(memory_peak) * 0.03), f"{v} MB", ha='center', fontweight='bold')



plt.tight_layout(rect=[0, 0.03, 1, 0.95])
os.makedirs('images', exist_ok=True)
output_path = 'images/benchmark_overview.png'
plt.savefig(output_path, transparent=False, facecolor='white', dpi=300)
print(f"Diagram saved in {output_path}")