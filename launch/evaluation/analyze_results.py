#!/usr/bin/env python3
"""
Analyze evaluation results from evaluate_containers.py
"""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def load_results(result_file: str) -> dict:
    """Load evaluation results from JSON file."""
    with open(result_file, 'r') as f:
        return json.load(f)


def print_statistics(results: dict):
    """Print detailed statistics."""
    stats = results['statistics']

    print(f"\n{'='*80}")
    print("EVALUATION STATISTICS")
    print(f"{'='*80}")
    print(f"Total Instances:        {stats['total']}")
    print(f"F2P Passed:            {stats['f2p_passed']} ({stats['f2p_pass_rate']})")
    print(f"Env Passed:            {stats['env_passed']} ({stats['env_pass_rate']})")
    print(f"Failed:                {stats['failed']}")
    print()

    print("Failure Breakdown:")
    for reason, count in stats['failure_breakdown'].items():
        print(f"  - {reason:20s}: {count}")
    print()

    print(f"Evaluation Time:       {results['elapsed_seconds']:.2f} seconds")
    print(f"Average per Instance:  {results['elapsed_seconds'] / stats['total']:.2f} seconds")
    print(f"Timestamp:             {results['timestamp']}")
    print(f"{'='*80}\n")


def list_by_status(results: dict, status_filter: str = None):
    """List instances by status."""
    details = results['details']

    # Group by status
    status_groups = defaultdict(list)
    for detail in details:
        status_groups[detail['status']].append(detail['instance_id'])

    print(f"\n{'='*80}")
    print("INSTANCES BY STATUS")
    print(f"{'='*80}")

    if status_filter:
        if status_filter in status_groups:
            print(f"\n{status_filter.upper()} ({len(status_groups[status_filter])} instances):")
            for instance_id in sorted(status_groups[status_filter]):
                print(f"  - {instance_id}")
        else:
            print(f"\nNo instances with status: {status_filter}")
    else:
        for status, instances in sorted(status_groups.items()):
            print(f"\n{status.upper()} ({len(instances)} instances):")
            for instance_id in sorted(instances):
                print(f"  - {instance_id}")

    print(f"\n{'='*80}\n")


def list_failed(results: dict):
    """List all failed instances with details."""
    details = results['details']

    failed_instances = [d for d in details if not d['f2p_pass'] and not d['env_pass']]

    print(f"\n{'='*80}")
    print(f"FAILED INSTANCES ({len(failed_instances)} total)")
    print(f"{'='*80}\n")

    for detail in failed_instances:
        print(f"Instance: {detail['instance_id']}")
        print(f"  Status:  {detail['status']}")
        print(f"  Message: {detail['message']}")
        if 'test_only_log' in detail:
            print(f"  Logs:    {detail['test_only_log']}")
            print(f"           {detail['both_patches_log']}")
        print()

    print(f"{'='*80}\n")


def export_csv(results: dict, output_file: str):
    """Export results to CSV."""
    details = results['details']

    with open(output_file, 'w', newline='') as f:
        fieldnames = [
            'instance_id',
            'status',
            'f2p_pass',
            'env_pass',
            'test_only_all_passed',
            'both_patches_all_passed',
            'test_only_time',
            'both_patches_time',
            'message',
        ]

        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for detail in details:
            row = {
                'instance_id': detail['instance_id'],
                'status': detail['status'],
                'f2p_pass': detail['f2p_pass'],
                'env_pass': detail['env_pass'],
                'test_only_all_passed': detail.get('test_only_all_passed', False),
                'both_patches_all_passed': detail.get('both_patches_all_passed', False),
                'test_only_time': detail.get('test_only_time', 0),
                'both_patches_time': detail.get('both_patches_time', 0),
                'message': detail.get('message', ''),
            }
            writer.writerow(row)

    print(f"Results exported to: {output_file}\n")


def print_performance_stats(results: dict):
    """Print performance statistics."""
    details = results['details']

    test_only_times = [d.get('test_only_time', 0) for d in details if d.get('test_only_time', 0) > 0]
    both_patches_times = [d.get('both_patches_time', 0) for d in details if d.get('both_patches_time', 0) > 0]

    print(f"\n{'='*80}")
    print("PERFORMANCE STATISTICS")
    print(f"{'='*80}\n")

    if test_only_times:
        avg_test_only = sum(test_only_times) / len(test_only_times)
        max_test_only = max(test_only_times)
        min_test_only = min(test_only_times)
        print(f"Test Only Stage:")
        print(f"  Average: {avg_test_only:.2f}s")
        print(f"  Min:     {min_test_only:.2f}s")
        print(f"  Max:     {max_test_only:.2f}s")
        print()

    if both_patches_times:
        avg_both = sum(both_patches_times) / len(both_patches_times)
        max_both = max(both_patches_times)
        min_both = min(both_patches_times)
        print(f"Both Patches Stage:")
        print(f"  Average: {avg_both:.2f}s")
        print(f"  Min:     {min_both:.2f}s")
        print(f"  Max:     {max_both:.2f}s")
        print()

    print(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(
        description='Analyze evaluation results from evaluate_containers.py'
    )
    parser.add_argument(
        '--result_file',
        type=str,
        required=True,
        help='Path to evaluation results JSON file'
    )
    parser.add_argument(
        '--list_status',
        type=str,
        help='List instances by specific status (e.g., failed, f2p_passed, env_passed)'
    )
    parser.add_argument(
        '--list_failed',
        action='store_true',
        help='List all failed instances with details'
    )
    parser.add_argument(
        '--export_csv',
        type=str,
        help='Export results to CSV file'
    )
    parser.add_argument(
        '--performance',
        action='store_true',
        help='Show performance statistics'
    )

    args = parser.parse_args()

    # Load results
    if not Path(args.result_file).exists():
        print(f"Error: Result file not found: {args.result_file}")
        return 1

    results = load_results(args.result_file)

    # Always show basic statistics
    print_statistics(results)

    # Optional outputs
    if args.list_status:
        list_by_status(results, args.list_status)
    elif args.list_failed:
        list_failed(results)
    else:
        # Default: show all statuses
        list_by_status(results)

    if args.performance:
        print_performance_stats(results)

    if args.export_csv:
        export_csv(results, args.export_csv)

    return 0


if __name__ == '__main__':
    exit(main())
