# Cost Analysis Example

This shows an example output from `analyze_cost.py` analyzing 88 instances.

## Summary Statistics

```
Total instances analyzed: 88
Models found: kimi-k2-instruct

OVERALL STATISTICS

Elapsed Time:
  Count:   88
  Total:   209,721.81 seconds (58.3 hours)
  Mean:    2,383.20 seconds (~40 minutes)
  Median:  1,827.02 seconds (~30 minutes)
  Min:     191.70 seconds (~3 minutes)
  Max:     17,235.77 seconds (~4.8 hours)

Elapsed Time (excluding max outlier):
  Excluded:    17,235.77 seconds (~4.8 hours)
  Count:       87
  Mean:        2,212.48 seconds (~37 minutes)
  Median:      1,817.20 seconds (~30 minutes)
  Improvement: 7.2% lower

Input Tokens:
  Count:   88
  Total:   63,926,565 tokens
  Mean:    726,438 tokens
  Median:  518,785 tokens
  Min:     126,815 tokens
  Max:     5,760,114 tokens

Output Tokens:
  Count:   88
  Total:   3,734,643 tokens
  Mean:    42,439 tokens
  Median:  19,428 tokens
  Min:     1,414 tokens
  Max:     657,291 tokens

Total Tokens:
  Count:   88
  Total:   67,661,208 tokens (~68M)
  Mean:    768,877 tokens
  Median:  563,590 tokens
  Min:     132,543 tokens
  Max:     5,765,408 tokens

Average tokens per second: 322.62
```

## Top Instances by Time

The longest-running instances:

1. **alteryx__featuretools-1382** - 17,236s (4.8 hours)
2. **pydata__xarray-4750** - 13,637s (3.8 hours)
3. **googleapis__google-cloud-python-519** - 9,255s (2.6 hours)
4. **alteryx__featuretools-2129** - 7,671s (2.1 hours)
5. **alteryx__featuretools-245** - 5,946s (1.7 hours)

## Top Instances by Token Usage

The most token-intensive instances:

1. **googleapis__google-cloud-python-9642** - 5,765,408 tokens (580s)
2. **alteryx__featuretools-1382** - 3,927,796 tokens (17,236s)
3. **googleapis__google-cloud-python-7697** - 3,357,283 tokens (685s)
4. **googleapis__google-cloud-python-519** - 2,383,838 tokens (9,255s)
5. **googleapis__google-cloud-python-5935** - 1,985,658 tokens (349s)

## Insights

- **Average processing time**: ~40 minutes per instance
- **Average without outlier**: ~37 minutes (7.2% improvement)
- **Token efficiency**: ~323 tokens/second
- **Output ratio**: ~5.5% output tokens (42K out of 769K total)
- **Wide variance**: Time ranges from 3 min to 4.8 hours
- **Token range**: 132K to 5.7M tokens per instance

## Outlier Analysis

The analysis automatically computes statistics **excluding the maximum value** to show the impact of outliers:

- **Original mean**: 2,383.20 seconds (~40 minutes)
- **Without max outlier**: 2,212.48 seconds (~37 minutes)
- **Improvement**: 7.2% reduction in average time
- **Excluded instance**: alteryx__featuretools-1382 (17,236 seconds / 4.8 hours)

This shows that one extremely long-running instance significantly inflates the average. The "without max" statistic provides a more representative measure of typical processing time.

### When to Use Each Metric

**Use original mean when:**
- You need to account for all instances including worst-case scenarios
- Planning total execution time and resources
- Budgeting for complete dataset processing

**Use mean without max when:**
- Estimating typical instance processing time
- Identifying performance baselines
- Detecting whether outliers indicate bugs or special cases
- Setting realistic expectations for "normal" instances
