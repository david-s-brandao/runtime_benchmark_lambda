import dash
from dash import dcc, html
import plotly.graph_objects as go
import json

# Your raw JSON data
json_data = """{
  "generated_at": "2026-05-05T23:07:43Z",
  "window": "last_24h",
  "functions": {
    "java_function": {
      "cloudwatch": {
        "invocations": 1026,
        "cold_starts": 116,
        "duration_ms": {
          "min": 318.14, "avg": 1248.19, "p50": 498.18, "p95": 6262.76, "p99": 8237.59, "max": 15955.58
        },
        "billed_ms": { "avg": 1453.86, "total": 1491664.0 },
        "memory_used_mb": { "avg": 198.39, "max": 209 },
        "cold_start_ms": { "avg": 1814.78, "max": 2395.67 }
      }
    },
    "rust_function": {
      "cloudwatch": {
        "invocations": 1028,
        "cold_starts": 98,
        "duration_ms": {
          "min": 120.48, "avg": 371.05, "p50": 254.48, "p95": 683.81, "p99": 3692.22, "max": 6766.31
        },
        "billed_ms": { "avg": 388.25, "total": 399116.0 },
        "memory_used_mb": { "avg": 43.79, "max": 45 },
        "cold_start_ms": { "avg": 175.17, "max": 253.64 }
      }
    }
  }
}"""

data = json.loads(json_data)
funcs = data['functions']

# Extracting data for the charts
labels = ['Java', 'Rust']
avg_duration = [funcs['java_function']['cloudwatch']['duration_ms']['avg'], 
                funcs['rust_function']['cloudwatch']['duration_ms']['avg']]
p95_duration = [funcs['java_function']['cloudwatch']['duration_ms']['p95'], 
                funcs['rust_function']['cloudwatch']['duration_ms']['p95']]
max_memory = [funcs['java_function']['cloudwatch']['memory_used_mb']['max'], 
              funcs['rust_function']['cloudwatch']['memory_used_mb']['max']]
avg_cold_start = [funcs['java_function']['cloudwatch']['cold_start_ms']['avg'], 
                  funcs['rust_function']['cloudwatch']['cold_start_ms']['avg']]

app = dash.Dash(__name__)

app.layout = html.Div([
    html.H1("Function Performance Dashboard", style={'textAlign': 'center', 'fontFamily': 'sans-serif'}),
    
    html.Div([
        # Duration Chart
        dcc.Graph(
            figure=go.Figure(data=[
                go.Bar(name='Average (ms)', x=labels, y=avg_duration),
                go.Bar(name='p95 (ms)', x=labels, y=p95_duration)
            ]).update_layout(title='Execution Duration (ms)', barmode='group')
        ),
        
        # Memory Chart
        dcc.Graph(
            figure=go.Figure(data=[
                go.Bar(name='Max Memory (MB)', x=labels, y=max_memory)
            ]).update_layout(title='Maximum Memory Usage (MB)')
        ),

        # Cold Start Chart
        dcc.Graph(
            figure=go.Figure(data=[
                go.Bar(name='Avg Cold Start (ms)', x=labels, y=avg_cold_start)
            ]).update_layout(title='Average Cold Start Time (ms)')
        )
    ], style={'maxWidth': '1000px', 'margin': '0 auto'})
])

if __name__ == '__main__':
    app.run(debug=True)