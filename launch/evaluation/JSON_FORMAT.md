# Cost Analysis JSON Output Format

This document describes the JSON output format from `analyze_cost.py --export_json`.

## JSON Structure

```json
{
  "summary": {
    "total_instances": 88,
    "models": ["kimi-k2-instruct"]
  },
  "overall_statistics": {
    "elapsed_seconds": {
      "count": 88,
      "total": 209721.81,
      "mean": 2383.20,
      "min": 191.70,
      "max": 17235.77,
      "median": 1827.02
    },
    "elapsed_seconds_without_max": {
      "count": 87,
      "total": 192486.04,
      "mean": 2212.48,
      "min": 191.70,
      "max": 13636.77,
      "median": 1817.20,
      "excluded_max": 17235.77
    },
    "input_tokens": {
      "count": 88,
      "total": 63926565,
      "mean": 726438.24,
      "min": 126815,
      "max": 5760114,
      "median": 518784.5
    },
    "output_tokens": {
      "count": 88,
      "total": 3734643,
      "mean": 42439.12,
      "min": 1414,
      "max": 657291,
      "median": 19427.5
    },
    "total_tokens": {
      "count": 88,
      "total": 67661208,
      "mean": 768877.36,
      "min": 132543,
      "max": 5765408,
      "median": 563589.5
    }
  },
  "per_model_statistics": {
    "kimi-k2-instruct": {
      "count": 88,
      "elapsed_seconds": { ... },
      "input_tokens": { ... },
      "output_tokens": { ... },
      "total_tokens": { ... }
    }
  },
  "top_instances": {
    "by_time": [
      {
        "instance_id": "alteryx__featuretools-1382",
        "elapsed_seconds": 17235.77,
        "total_tokens": 3927796,
        "model": "kimi-k2-instruct"
      },
      ...
    ],
    "by_total_tokens": [
      {
        "instance_id": "googleapis__google-cloud-python-9642",
        "total_tokens": 5765408,
        "elapsed_seconds": 580.22,
        "model": "kimi-k2-instruct"
      },
      ...
    ],
    "by_input_tokens": [
      {
        "instance_id": "googleapis__google-cloud-python-9642",
        "input_tokens": 5760114,
        "model": "kimi-k2-instruct"
      },
      ...
    ],
    "by_output_tokens": [
      {
        "instance_id": "alteryx__featuretools-1382",
        "output_tokens": 657291,
        "model": "kimi-k2-instruct"
      },
      ...
    ]
  }
}
```

## Field Descriptions

### `summary`
- `total_instances`: Total number of instances analyzed
- `models`: List of unique models found in the cost.json files

### `overall_statistics`
Statistics aggregated across all instances:
- `elapsed_seconds`: Execution time statistics (all instances)
- `elapsed_seconds_without_max`: Execution time statistics **excluding the maximum outlier**
  - Useful for understanding typical performance without extreme cases
  - Contains an additional `excluded_max` field showing the removed value
- `input_tokens`: Input token usage statistics
- `output_tokens`: Output token usage statistics
- `total_tokens`: Total token usage statistics

Each statistic contains:
- `count`: Number of instances
- `total`: Sum of all values
- `mean`: Average value
- `min`: Minimum value
- `max`: Maximum value
- `median`: Median value

The `elapsed_seconds_without_max` statistic additionally contains:
- `excluded_max`: The maximum value that was excluded from the calculation

### `per_model_statistics`
Same structure as `overall_statistics`, but broken down by model. Also includes `elapsed_seconds_without_max` for each model.

### `top_instances`
Top 10 instances for each category:
- `by_time`: Longest running instances
- `by_total_tokens`: Instances with most total tokens
- `by_input_tokens`: Instances with most input tokens
- `by_output_tokens`: Instances with most output tokens

## Usage Examples

### Python
```python
import json

# Load the JSON file
with open('cost_analysis.json', 'r') as f:
    data = json.load(f)

# Get average time
avg_time = data['overall_statistics']['elapsed_seconds']['mean']
print(f"Average time: {avg_time:.2f} seconds")

# Get average time excluding outlier
without_max = data['overall_statistics']['elapsed_seconds_without_max']
avg_time_clean = without_max['mean']
excluded = without_max['excluded_max']
improvement = (avg_time - avg_time_clean) / avg_time * 100
print(f"Average time (excl. outlier): {avg_time_clean:.2f} seconds")
print(f"Excluded outlier: {excluded:.2f} seconds")
print(f"Improvement: {improvement:.1f}% lower")

# Get top 5 instances by time
top_5_by_time = data['top_instances']['by_time'][:5]
for i, inst in enumerate(top_5_by_time, 1):
    print(f"{i}. {inst['instance_id']}: {inst['elapsed_seconds']:.2f}s")

# Get model statistics
for model, stats in data['per_model_statistics'].items():
    print(f"{model}: {stats['count']} instances")
    print(f"  Avg tokens: {stats['total_tokens']['mean']:.0f}")
    print(f"  Avg time: {stats['elapsed_seconds']['mean']:.2f}s")
    print(f"  Avg time (excl. max): {stats['elapsed_seconds_without_max']['mean']:.2f}s")
```

### jq (Command Line)
```bash
# Get average time
jq '.overall_statistics.elapsed_seconds.mean' cost_analysis.json

# Get average time without outlier
jq '.overall_statistics.elapsed_seconds_without_max.mean' cost_analysis.json

# Get excluded outlier value
jq '.overall_statistics.elapsed_seconds_without_max.excluded_max' cost_analysis.json

# Calculate improvement percentage
jq '(.overall_statistics.elapsed_seconds.mean - .overall_statistics.elapsed_seconds_without_max.mean) / .overall_statistics.elapsed_seconds.mean * 100' cost_analysis.json

# Get top 3 instances by time
jq '.top_instances.by_time[:3]' cost_analysis.json

# Get total tokens used
jq '.overall_statistics.total_tokens.total' cost_analysis.json

# List all models
jq '.summary.models[]' cost_analysis.json

# Get instances that took > 5000 seconds
jq '.top_instances.by_time[] | select(.elapsed_seconds > 5000)' cost_analysis.json
```

### JavaScript
```javascript
// Load the JSON
const data = require('./cost_analysis.json');

// Calculate tokens per second
const avgTime = data.overall_statistics.elapsed_seconds.mean;
const avgTokens = data.overall_statistics.total_tokens.mean;
const tokensPerSecond = avgTokens / avgTime;
console.log(`Tokens per second: ${tokensPerSecond.toFixed(2)}`);

// Find most expensive instance
const mostExpensive = data.top_instances.by_total_tokens[0];
console.log(`Most expensive: ${mostExpensive.instance_id} (${mostExpensive.total_tokens} tokens)`);
```

## Benefits of JSON Format

1. **Machine Readable**: Easy to parse and process programmatically
2. **Structured**: Hierarchical data structure preserves relationships
3. **Type Safe**: Numbers remain numbers (not strings like in CSV)
4. **Flexible**: Can include nested data and arrays
5. **Universal**: Supported by virtually all programming languages
6. **Self-Documenting**: Field names are included with the data

## Comparison with CSV

| Feature | JSON | CSV |
|---------|------|-----|
| Nested data | ✓ | ✗ |
| Arrays | ✓ | ✗ |
| Type preservation | ✓ | ✗ |
| Human readable | Medium | High |
| File size | Larger | Smaller |
| Spreadsheet import | Medium | Easy |
| API friendly | ✓ | ✗ |

Choose JSON for:
- Programmatic processing
- API integration
- Complex data structures
- Type preservation

Choose CSV for:
- Simple tabular data
- Spreadsheet analysis
- Smaller file sizes
- Maximum compatibility
