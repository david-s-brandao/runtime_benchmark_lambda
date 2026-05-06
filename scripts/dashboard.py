import matplotlib.pyplot as plt
import numpy as np
import os

labels = ['Java 21', 'Rust']
cold_starts = [1814.78, 175.26]       # ms
p99_duration = [8229.60, 3691.89]     # ms
memory_peak = [209.00, 45.00]         # MB

plt.style.use('dark_background')
fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(15, 6))
fig.suptitle('AWS Lambda: Java 21 vs Rust Benchmark', fontsize=18, fontweight='bold', color='#FF9900')

colors = ['#ED8B00', '#DEA584']

# 1. Cold Starts
ax1.bar(labels, cold_starts, color=colors, width=0.6)
ax1.set_title('Avg Cold Start (ms)', fontsize=14)
ax1.set_ylabel('Milliseconds')
for i, v in enumerate(cold_starts):
    ax1.text(i, v + 50, f"{v} ms", ha='center', fontweight='bold')

# 2. Tail Latency (p99)
ax2.bar(labels, p99_duration, color=colors, width=0.6)
ax2.set_title('p99 Execution Tail Latency (ms)', fontsize=14)
for i, v in enumerate(p99_duration):
    ax2.text(i, v + 200, f"{v} ms", ha='center', fontweight='bold')

# 3. Memory Usage
ax3.bar(labels, memory_peak, color=colors, width=0.6)
ax3.set_title('Peak Memory Usage (MB)', fontsize=14)
ax3.set_ylabel('Megabytes')
for i, v in enumerate(memory_peak):
    ax3.text(i, v + 5, f"{v} MB", ha='center', fontweight='bold')
plt.tight_layout(rect=[0, 0.03, 1, 0.95])
os.makedirs('images', exist_ok=True)
output_path = 'images/benchmark_overview.png'
plt.savefig(output_path, transparent=True, dpi=300)
print(f"Chart successfully saved to {output_path}")