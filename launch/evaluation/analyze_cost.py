#!/usr/bin/env python3
"""
Analyze cost.json files to compute statistics on token usage and time.
"""

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


def find_cost_files(base_dir: str) -> List[str]:
    """
    Find all cost.json files in the directory tree.

    Args:
        base_dir: Base directory to search

    Returns:
        List of paths to cost.json files
    """
    cost_files = []
    for root, dirs, files in os.walk(base_dir):
        if 'cost.json' in files:
            cost_files.append(os.path.join(root, 'cost.json'))
    return sorted(cost_files)


def load_cost_data(cost_file: str) -> Dict:
    """
    Load cost data from JSON file.

    Args:
        cost_file: Path to cost.json file

    Returns:
        Dictionary with cost data, or None if error
    """
    try:
        with open(cost_file, 'r') as f:
            data = json.load(f)
            # Add instance_id from parent directory
            instance_id = os.path.basename(os.path.dirname(cost_file))
            data['instance_id'] = instance_id
            return data
    except Exception as e:
        print(f"Warning: Failed to load {cost_file}: {e}")
        return None


def compute_statistics(values: List[float]) -> Dict:
    """
    Compute statistics for a list of values.

    Args:
        values: List of numeric values

    Returns:
        Dictionary with statistics
    """
    if not values:
        return {
            'count': 0,
            'total': 0,
            'mean': 0,
            'min': 0,
            'max': 0,
            'median': 0
        }

    sorted_values = sorted(values)
    n = len(sorted_values)
    median = sorted_values[n // 2] if n % 2 == 1 else (sorted_values[n // 2 - 1] + sorted_values[n // 2]) / 2

    return {
        'count': n,
        'total': sum(values),
        'mean': sum(values) / n,
        'min': min(values),
        'max': max(values),
        'median': median
    }


def compute_statistics_without_max(values: List[float]) -> Dict:
    """
    Compute statistics for a list of values after removing the maximum value.
    Useful for removing outliers.

    Args:
        values: List of numeric values

    Returns:
        Dictionary with statistics (excluding the max value)
    """
    if len(values) <= 1:
        return compute_statistics(values)

    # Remove the maximum value
    filtered_values = sorted(values)[:-1]

    n = len(filtered_values)
    median = filtered_values[n // 2] if n % 2 == 1 else (filtered_values[n // 2 - 1] + filtered_values[n // 2]) / 2

    return {
        'count': n,
        'total': sum(filtered_values),
        'mean': sum(filtered_values) / n,
        'min': min(filtered_values),
        'max': max(filtered_values),
        'median': median,
        'excluded_max': max(values)
    }


def analyze_costs(base_dir: str, verbose: bool = False) -> Dict:
    """
    Analyze all cost.json files in directory.

    Args:
        base_dir: Base directory to search
        verbose: Print detailed information

    Returns:
        Dictionary with analysis results
    """
    print(f"Searching for cost.json files in: {base_dir}")
    cost_files = find_cost_files(base_dir)
    print(f"Found {len(cost_files)} cost.json files\n")

    if not cost_files:
        print("No cost.json files found!")
        return {}

    # Load all cost data
    all_data = []
    for cost_file in cost_files:
        data = load_cost_data(cost_file)
        if data:
            all_data.append(data)

    if not all_data:
        print("No valid cost data found!")
        return {}

    # Group by model
    by_model = defaultdict(list)
    for data in all_data:
        model = data.get('model', 'unknown')
        by_model[model].append(data)

    # Overall statistics
    elapsed_times = [d['elapsed_seconds'] for d in all_data if 'elapsed_seconds' in d]
    input_tokens = [d['total_input_tokens'] for d in all_data if 'total_input_tokens' in d]
    output_tokens = [d['total_output_tokens'] for d in all_data if 'total_output_tokens' in d]
    total_tokens = [d['total_tokens'] for d in all_data if 'total_tokens' in d]

    results = {
        'total_instances': len(all_data),
        'models': list(by_model.keys()),
        'overall': {
            'elapsed_seconds': compute_statistics(elapsed_times),
            'elapsed_seconds_without_max': compute_statistics_without_max(elapsed_times),
            'input_tokens': compute_statistics(input_tokens),
            'output_tokens': compute_statistics(output_tokens),
            'total_tokens': compute_statistics(total_tokens)
        },
        'by_model': {}
    }

    # Per-model statistics
    for model, model_data in by_model.items():
        model_elapsed = [d['elapsed_seconds'] for d in model_data if 'elapsed_seconds' in d]
        model_input = [d['total_input_tokens'] for d in model_data if 'total_input_tokens' in d]
        model_output = [d['total_output_tokens'] for d in model_data if 'total_output_tokens' in d]
        model_total = [d['total_tokens'] for d in model_data if 'total_tokens' in d]

        results['by_model'][model] = {
            'count': len(model_data),
            'elapsed_seconds': compute_statistics(model_elapsed),
            'elapsed_seconds_without_max': compute_statistics_without_max(model_elapsed),
            'input_tokens': compute_statistics(model_input),
            'output_tokens': compute_statistics(model_output),
            'total_tokens': compute_statistics(model_total)
        }

    # Find top instances by various metrics
    results['top_instances'] = {
        'longest_time': sorted(all_data, key=lambda x: x.get('elapsed_seconds', 0), reverse=True)[:10],
        'most_tokens': sorted(all_data, key=lambda x: x.get('total_tokens', 0), reverse=True)[:10],
        'most_input': sorted(all_data, key=lambda x: x.get('total_input_tokens', 0), reverse=True)[:10],
        'most_output': sorted(all_data, key=lambda x: x.get('total_output_tokens', 0), reverse=True)[:10]
    }

    return results


def print_statistics(stats: Dict, metric_name: str, unit: str = ""):
    """
    Print statistics in a formatted way.

    Args:
        stats: Statistics dictionary
        metric_name: Name of the metric
        unit: Unit of measurement
    """
    if stats['count'] == 0:
        print(f"  {metric_name}: No data")
        return

    print(f"  {metric_name}:")
    print(f"    Count:   {stats['count']}")
    print(f"    Total:   {stats['total']:,.2f}{unit}")
    print(f"    Mean:    {stats['mean']:,.2f}{unit}")
    print(f"    Median:  {stats['median']:,.2f}{unit}")
    print(f"    Min:     {stats['min']:,.2f}{unit}")
    print(f"    Max:     {stats['max']:,.2f}{unit}")


def print_results(results: Dict, verbose: bool = False):
    """
    Print analysis results.

    Args:
        results: Analysis results dictionary
        verbose: Print detailed information
    """
    print("="*80)
    print("COST ANALYSIS RESULTS")
    print("="*80)
    print(f"Total instances analyzed: {results['total_instances']}")
    print(f"Models found: {', '.join(results['models'])}")
    print()

    # Overall statistics
    print("-"*80)
    print("OVERALL STATISTICS")
    print("-"*80)
    print()

    overall = results['overall']
    print_statistics(overall['elapsed_seconds'], "Elapsed Time", " seconds")
    print()

    # Print elapsed time without max (outlier removed)
    without_max = overall['elapsed_seconds_without_max']
    if 'excluded_max' in without_max:
        print(f"  Elapsed Time (excluding max outlier):")
        print(f"    Excluded:    {without_max['excluded_max']:,.2f} seconds")
        print(f"    Count:       {without_max['count']}")
        print(f"    Mean:        {without_max['mean']:,.2f} seconds")
        print(f"    Median:      {without_max['median']:,.2f} seconds")
        print(f"    Improvement: {((overall['elapsed_seconds']['mean'] - without_max['mean']) / overall['elapsed_seconds']['mean'] * 100):,.1f}% lower")
        print()

    print_statistics(overall['input_tokens'], "Input Tokens", " tokens")
    print()
    print_statistics(overall['output_tokens'], "Output Tokens", " tokens")
    print()
    print_statistics(overall['total_tokens'], "Total Tokens", " tokens")
    print()

    # Calculate token rate
    if overall['elapsed_seconds']['mean'] > 0:
        tokens_per_second = overall['total_tokens']['mean'] / overall['elapsed_seconds']['mean']
        print(f"  Average tokens per second: {tokens_per_second:,.2f}")
        print()

    # Per-model statistics
    if len(results['by_model']) > 1:
        print("-"*80)
        print("PER-MODEL STATISTICS")
        print("-"*80)
        print()

        for model, model_stats in results['by_model'].items():
            print(f"Model: {model}")
            print(f"  Instances: {model_stats['count']}")
            print(f"  Avg elapsed time: {model_stats['elapsed_seconds']['mean']:,.2f}s")

            # Show time without max if available
            if 'excluded_max' in model_stats['elapsed_seconds_without_max']:
                without_max = model_stats['elapsed_seconds_without_max']
                print(f"  Avg elapsed time (excl. max): {without_max['mean']:,.2f}s (excluded: {without_max['excluded_max']:,.2f}s)")

            print(f"  Avg input tokens: {model_stats['input_tokens']['mean']:,.0f}")
            print(f"  Avg output tokens: {model_stats['output_tokens']['mean']:,.0f}")
            print(f"  Avg total tokens: {model_stats['total_tokens']['mean']:,.0f}")
            print()

    # Top instances
    if verbose:
        print("-"*80)
        print("TOP 10 INSTANCES BY TIME")
        print("-"*80)
        for i, inst in enumerate(results['top_instances']['longest_time'], 1):
            print(f"{i:2d}. {inst['instance_id']:50s} {inst['elapsed_seconds']:8.2f}s  "
                  f"{inst['total_tokens']:10,d} tokens  ({inst.get('model', 'unknown')})")
        print()

        print("-"*80)
        print("TOP 10 INSTANCES BY TOTAL TOKENS")
        print("-"*80)
        for i, inst in enumerate(results['top_instances']['most_tokens'], 1):
            print(f"{i:2d}. {inst['instance_id']:50s} {inst['total_tokens']:10,d} tokens  "
                  f"{inst['elapsed_seconds']:8.2f}s  ({inst.get('model', 'unknown')})")
        print()

        print("-"*80)
        print("TOP 10 INSTANCES BY OUTPUT TOKENS")
        print("-"*80)
        for i, inst in enumerate(results['top_instances']['most_output'], 1):
            print(f"{i:2d}. {inst['instance_id']:50s} {inst['total_output_tokens']:10,d} tokens  "
                  f"({inst.get('model', 'unknown')})")
        print()

    print("="*80)


def export_json(results: Dict, output_file: str):
    """
    Export results to JSON file.

    Args:
        results: Analysis results
        output_file: Output JSON file path
    """
    # Prepare clean output structure
    output = {
        'summary': {
            'total_instances': results['total_instances'],
            'models': results['models']
        },
        'overall_statistics': {
            'elapsed_seconds': results['overall']['elapsed_seconds'],
            'elapsed_seconds_without_max': results['overall']['elapsed_seconds_without_max'],
            'input_tokens': results['overall']['input_tokens'],
            'output_tokens': results['overall']['output_tokens'],
            'total_tokens': results['overall']['total_tokens']
        },
        'per_model_statistics': {}
    }

    # Add per-model statistics
    for model, model_stats in results['by_model'].items():
        output['per_model_statistics'][model] = {
            'count': model_stats['count'],
            'elapsed_seconds': model_stats['elapsed_seconds'],
            'elapsed_seconds_without_max': model_stats['elapsed_seconds_without_max'],
            'input_tokens': model_stats['input_tokens'],
            'output_tokens': model_stats['output_tokens'],
            'total_tokens': model_stats['total_tokens']
        }

    # Add top instances
    output['top_instances'] = {
        'by_time': [
            {
                'instance_id': inst['instance_id'],
                'elapsed_seconds': inst['elapsed_seconds'],
                'total_tokens': inst['total_tokens'],
                'model': inst.get('model', 'unknown')
            }
            for inst in results['top_instances']['longest_time']
        ],
        'by_total_tokens': [
            {
                'instance_id': inst['instance_id'],
                'total_tokens': inst['total_tokens'],
                'elapsed_seconds': inst['elapsed_seconds'],
                'model': inst.get('model', 'unknown')
            }
            for inst in results['top_instances']['most_tokens']
        ],
        'by_input_tokens': [
            {
                'instance_id': inst['instance_id'],
                'input_tokens': inst['total_input_tokens'],
                'model': inst.get('model', 'unknown')
            }
            for inst in results['top_instances']['most_input']
        ],
        'by_output_tokens': [
            {
                'instance_id': inst['instance_id'],
                'output_tokens': inst['total_output_tokens'],
                'model': inst.get('model', 'unknown')
            }
            for inst in results['top_instances']['most_output']
        ]
    }

    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\nResults exported to: {output_file}")


def export_csv(results: Dict, output_file: str):
    """
    Export results to CSV file.

    Args:
        results: Analysis results
        output_file: Output CSV file path
    """
    import csv

    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)

        # Write overall statistics
        writer.writerow(['Metric', 'Count', 'Total', 'Mean', 'Median', 'Min', 'Max'])
        writer.writerow([])
        writer.writerow(['Overall Statistics'])

        overall = results['overall']
        for metric in ['elapsed_seconds', 'input_tokens', 'output_tokens', 'total_tokens']:
            stats = overall[metric]
            writer.writerow([
                metric,
                stats['count'],
                f"{stats['total']:.2f}",
                f"{stats['mean']:.2f}",
                f"{stats['median']:.2f}",
                f"{stats['min']:.2f}",
                f"{stats['max']:.2f}"
            ])

        # Write per-model statistics
        writer.writerow([])
        writer.writerow(['Per-Model Statistics'])
        writer.writerow(['Model', 'Count', 'Avg Time (s)', 'Avg Input Tokens', 'Avg Output Tokens', 'Avg Total Tokens'])

        for model, model_stats in results['by_model'].items():
            writer.writerow([
                model,
                model_stats['count'],
                f"{model_stats['elapsed_seconds']['mean']:.2f}",
                f"{model_stats['input_tokens']['mean']:.0f}",
                f"{model_stats['output_tokens']['mean']:.0f}",
                f"{model_stats['total_tokens']['mean']:.0f}"
            ])

    print(f"\nResults exported to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Analyze cost.json files to compute token and time statistics'
    )
    parser.add_argument(
        '--base_dir',
        type=str,
        default='playground/benchmark_python_v3.0',
        help='Base directory to search for cost.json files (default: playground/benchmark_python_v3.0)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Print detailed information including top instances'
    )
    parser.add_argument(
        '--export_json',
        type=str,
        help='Export results to JSON file'
    )
    parser.add_argument(
        '--export_csv',
        type=str,
        help='Export results to CSV file'
    )

    args = parser.parse_args()

    # Analyze costs
    results = analyze_costs(args.base_dir, args.verbose)

    if not results:
        return 1

    # Print results
    print_results(results, args.verbose)

    # Export to JSON if requested
    if args.export_json:
        export_json(results, args.export_json)

    # Export to CSV if requested
    if args.export_csv:
        export_csv(results, args.export_csv)

    return 0


if __name__ == '__main__':
    exit(main())
