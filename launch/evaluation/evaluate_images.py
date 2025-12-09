#!/usr/bin/env python3
"""
Evaluate launch instances using Docker images.
Runs two-stage tests:
  Stage 1: Apply test_patch only (expected to fail)
  Stage 2: Apply fix_patch + test_patch (expected to pass)
"""

import argparse
import docker
import json
import os
import re
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


def get_image_name(instance_id: str, namespace: str = "starryzhang", arch: str = "x86_64", tag: str = "latest") -> str:
    """
    Get Docker image name for instance.

    Format: {namespace}/sweb.eval.{arch}.{instance_id.lower()}:{tag}
    Where __ is replaced with _1776_

    Args:
        instance_id: Instance ID (e.g., alteryx__featuretools-1018)
        namespace: Docker registry namespace
        arch: Architecture (x86_64 or arm64)
        tag: Image tag

    Returns:
        Full image name
    """
    image_key = f"sweb.eval.{arch}.{instance_id.lower()}"
    return f"{namespace}/{image_key}:{tag}"


def extract_test_files_from_patch(test_patch: str) -> List[str]:
    """
    Extract test file paths from test_patch.

    Args:
        test_patch: The test patch content in git diff format

    Returns:
        List of test file paths
    """
    test_files = []
    if not test_patch:
        return test_files

    lines = test_patch.split('\n')
    for line in lines:
        # Look for lines like "diff --git a/path/to/test.py b/path/to/test.py"
        if line.startswith('diff --git'):
            parts = line.split()
            if len(parts) >= 3:
                file_path = parts[2][2:]  # Remove 'a/' prefix
                # Only include test files
                if 'test' in file_path.lower() and file_path.endswith('.py'):
                    test_files.append(file_path)

    return test_files


def write_patch_to_container(container, patch_content: str, dest_path: str):
    """
    Write patch content to container using heredoc.

    Args:
        container: Docker container
        patch_content: Patch content
        dest_path: Destination path in container
    """
    # Use heredoc to write patch (handles special characters well)
    heredoc_cmd = f"""cat > {dest_path} << 'EOF_PATCH_DELIMITER'
{patch_content}
EOF_PATCH_DELIMITER"""

    result = container.exec_run(
        ["bash", "-c", heredoc_cmd],
        workdir="/testbed"
    )

    if result.exit_code != 0:
        raise RuntimeError(f"Failed to write patch to {dest_path}: {result.output.decode()}")


def check_test_results(exit_code: int) -> bool:
    """
    Check if all tests passed based on exit code.

    Args:
        exit_code: Exit code from pytest

    Returns:
        True if all tests passed (exit code 0), False otherwise
    """
    return exit_code == 0


def evaluate_single_instance(
    instance_id: str,
    output_dir: str,
    namespace: str = "starryzhang",
    arch: str = "x86_64",
    tag: str = "latest",
    timeout: int = 600,
) -> Dict:
    """
    Evaluate a single instance using its Docker image.

    Args:
        instance_id: Instance identifier
        output_dir: Output directory containing instance data
        namespace: Docker registry namespace
        arch: Architecture
        tag: Image tag
        timeout: Timeout in seconds

    Returns:
        Result dictionary
    """
    result = {
        'instance_id': instance_id,
        'status': 'unknown',
        'env_pass': False,
        'f2p_pass': False,
        'message': '',
        'test_only_time': 0,
        'both_patches_time': 0,
        'test_only_passed': False,
        'both_patches_passed': False,
        'timestamp': datetime.now().isoformat()
    }

    instance_dir = os.path.join(output_dir, instance_id)

    # Check if instance directory exists
    if not os.path.exists(instance_dir):
        result['status'] = 'no_instance_dir'
        result['message'] = 'Instance directory does not exist'
        return result

    # Load instance.json
    instance_json_path = os.path.join(instance_dir, 'instance.json')
    if not os.path.exists(instance_json_path):
        result['status'] = 'no_instance_json'
        result['message'] = 'instance.json not found'
        return result

    with open(instance_json_path, 'r') as f:
        instance_data = json.load(f)

    test_patch = instance_data.get('test_patch', '')
    fix_patch = instance_data.get('patch', '')

    if not test_patch:
        result['status'] = 'no_test_patch'
        result['message'] = 'test_patch is empty'
        return result

    # Extract test files
    test_files = extract_test_files_from_patch(test_patch)
    if not test_files:
        result['status'] = 'no_test_files'
        result['message'] = 'No test files found in test_patch'
        return result

    # Get image name
    image_name = get_image_name(instance_id, namespace, arch, tag)
    result['image_name'] = image_name

    # Check if image exists
    client = docker.from_env()
    try:
        client.images.get(image_name)
    except docker.errors.ImageNotFound:
        result['status'] = 'no_image'
        result['message'] = f'Docker image not found: {image_name}'
        return result

    # Create logs directory
    logs_dir = os.path.join(instance_dir, 'evaluation_logs')
    os.makedirs(logs_dir, exist_ok=True)

    # Build test command
    test_files_str = ' '.join(test_files)
    test_cmd = f'cd /testbed && pytest -rA {test_files_str} -v'

    container = None
    container_name = f"eval_{instance_id.replace('/', '_')}_{int(time.time())}"

    try:
        # ========================================
        # Stage 1: Test with only test_patch
        # ========================================
        test_only_log_path = os.path.join(logs_dir, 'test_only.log')

        test_only_start = time.time()

        # Start container from image
        container = client.containers.run(
            image_name,
            name=container_name,
            command="tail -f /dev/null",
            detach=True,
            remove=False
        )

        # Wait for container to be ready
        time.sleep(1)

        # Write and apply test_patch
        write_patch_to_container(container, test_patch, "/tmp/test.patch")
        apply_result = container.exec_run(
            ["bash", "-c", "cd /testbed && git apply /tmp/test.patch"],
            workdir="/testbed"
        )

        if apply_result.exit_code != 0:
            result['status'] = 'test_patch_apply_failed'
            result['message'] = f'Failed to apply test_patch: {apply_result.output.decode()}'
            with open(test_only_log_path, 'w') as f:
                f.write("=== Failed to apply test_patch ===\n")
                f.write(apply_result.output.decode())
            return result

        # Run tests
        test_result = container.exec_run(
            ["bash", "-c", test_cmd],
            workdir="/testbed"
        )

        test_only_output = test_result.output.decode()
        test_only_exit_code = test_result.exit_code

        result['test_only_time'] = time.time() - test_only_start
        result['test_only_passed'] = check_test_results(test_only_exit_code)

        # Save log
        with open(test_only_log_path, 'w') as f:
            f.write("=== Stage 1: Test with only test_patch ===\n\n")
            f.write(f"=== Image ===\n{image_name}\n\n")
            f.write("=== Test Files ===\n")
            for tf in test_files:
                f.write(f"  - {tf}\n")
            f.write("\n=== Test Command ===\n")
            f.write(f"{test_cmd}\n\n")
            f.write("=== Test Output ===\n")
            f.write(test_only_output)
            f.write(f"\n\n=== Exit Code ===\n{test_only_exit_code}\n")
            f.write(f"\n=== Test Time ===\n{result['test_only_time']:.2f} seconds\n")
            f.write(f"\n=== All Passed ===\n{result['test_only_passed']}\n")

        # Stop and remove container
        container.stop(timeout=5)
        container.remove()
        container = None

        # ========================================
        # Stage 2: Test with both patches
        # ========================================
        both_patches_log_path = os.path.join(logs_dir, 'both_patches.log')

        both_patches_start = time.time()

        # Start new container from image
        container = client.containers.run(
            image_name,
            name=container_name,
            command="tail -f /dev/null",
            detach=True,
            remove=False
        )

        # Wait for container to be ready
        time.sleep(1)

        # Write and apply fix_patch
        write_patch_to_container(container, fix_patch, "/tmp/fix.patch")
        apply_fix_result = container.exec_run(
            ["bash", "-c", "cd /testbed && git apply /tmp/fix.patch"],
            workdir="/testbed"
        )

        if apply_fix_result.exit_code != 0:
            result['status'] = 'fix_patch_apply_failed'
            result['message'] = f'Failed to apply fix_patch: {apply_fix_result.output.decode()}'
            with open(both_patches_log_path, 'w') as f:
                f.write("=== Failed to apply fix_patch ===\n")
                f.write(apply_fix_result.output.decode())
            return result

        # Write and apply test_patch
        write_patch_to_container(container, test_patch, "/tmp/test.patch")
        apply_test_result = container.exec_run(
            ["bash", "-c", "cd /testbed && git apply /tmp/test.patch"],
            workdir="/testbed"
        )

        if apply_test_result.exit_code != 0:
            result['status'] = 'test_patch_apply_failed_stage2'
            result['message'] = f'Failed to apply test_patch in stage 2: {apply_test_result.output.decode()}'
            with open(both_patches_log_path, 'w') as f:
                f.write("=== Failed to apply test_patch (stage 2) ===\n")
                f.write(apply_test_result.output.decode())
            return result

        # Run tests
        test_result = container.exec_run(
            ["bash", "-c", test_cmd],
            workdir="/testbed"
        )

        both_patches_output = test_result.output.decode()
        both_patches_exit_code = test_result.exit_code

        result['both_patches_time'] = time.time() - both_patches_start
        result['both_patches_passed'] = check_test_results(both_patches_exit_code)

        # Save log
        with open(both_patches_log_path, 'w') as f:
            f.write("=== Stage 2: Test with both fix_patch and test_patch ===\n\n")
            f.write(f"=== Image ===\n{image_name}\n\n")
            f.write("=== Test Files ===\n")
            for tf in test_files:
                f.write(f"  - {tf}\n")
            f.write("\n=== Test Command ===\n")
            f.write(f"{test_cmd}\n\n")
            f.write("=== Test Output ===\n")
            f.write(both_patches_output)
            f.write(f"\n\n=== Exit Code ===\n{both_patches_exit_code}\n")
            f.write(f"\n=== Test Time ===\n{result['both_patches_time']:.2f} seconds\n")
            f.write(f"\n=== All Passed ===\n{result['both_patches_passed']}\n")

        # ========================================
        # Determine final result
        # ========================================
        result['test_only_log'] = test_only_log_path
        result['both_patches_log'] = both_patches_log_path

        # env_pass: both_patches all passed
        result['env_pass'] = result['both_patches_passed']

        # f2p_pass: test_only failed AND both_patches passed
        test_only_failed = not result['test_only_passed']
        result['f2p_pass'] = test_only_failed and result['both_patches_passed']

        if result['f2p_pass']:
            result['status'] = 'f2p_passed'
            result['message'] = 'F2P passed: test_only failed, both_patches passed'
        elif result['env_pass']:
            result['status'] = 'env_passed'
            result['message'] = 'Env passed: both_patches passed (but test_only also passed)'
        else:
            result['status'] = 'failed'
            result['message'] = 'Both_patches stage failed'

    except docker.errors.ImageNotFound:
        result['status'] = 'no_image'
        result['message'] = f'Docker image not found: {image_name}'
    except Exception as e:
        result['status'] = 'error'
        result['message'] = f'Unexpected error: {str(e)}'

        # Save error log
        error_log_path = os.path.join(logs_dir, 'error.log')
        with open(error_log_path, 'w') as f:
            f.write(f"=== Unexpected Error ===\n")
            f.write(f"Error: {str(e)}\n")
            f.write(f"Instance: {instance_id}\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        result['error_log'] = error_log_path

    finally:
        # Cleanup container
        if container:
            try:
                container.stop(timeout=5)
            except:
                pass
            try:
                container.remove()
            except:
                pass

    return result


def evaluate_instance_wrapper(args):
    """Wrapper for parallel execution."""
    return evaluate_single_instance(*args)


def main():
    parser = argparse.ArgumentParser(
        description='Evaluate launch instances using Docker images'
    )
    parser.add_argument(
        '--output_dir',
        type=str,
        required=True,
        help='Output directory containing instance subdirectories'
    )
    parser.add_argument(
        '--namespace',
        type=str,
        default='starryzhang',
        help='Docker registry namespace (default: starryzhang)'
    )
    parser.add_argument(
        '--arch',
        type=str,
        default='x86_64',
        choices=['x86_64', 'arm64'],
        help='Architecture (default: x86_64)'
    )
    parser.add_argument(
        '--tag',
        type=str,
        default='latest',
        help='Image tag (default: latest)'
    )
    parser.add_argument(
        '--instances',
        type=str,
        nargs='*',
        help='Specific instance IDs to evaluate (if not provided, evaluate all)'
    )
    parser.add_argument(
        '--parallel',
        type=int,
        default=1,
        help='Number of parallel workers (default: 1)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=600,
        help='Timeout in seconds for each instance (default: 600)'
    )
    parser.add_argument(
        '--max_instances',
        type=int,
        default=None,
        help='Maximum number of instances to evaluate'
    )

    args = parser.parse_args()

    # Normalize paths
    output_dir = os.path.abspath(args.output_dir)

    if not os.path.exists(output_dir):
        print(f"Error: Output directory does not exist: {output_dir}")
        return 1

    print(f"{'='*80}")
    print(f"Image-based Evaluation")
    print(f"{'='*80}")
    print(f"Output directory: {output_dir}")
    print(f"Namespace:        {args.namespace}")
    print(f"Architecture:     {args.arch}")
    print(f"Image tag:        {args.tag}")
    print(f"Parallel workers: {args.parallel}")
    print(f"Timeout:          {args.timeout}s")
    print()

    # Find instances to evaluate
    if args.instances:
        instances_to_eval = args.instances
        print(f"Evaluating {len(instances_to_eval)} specified instance(s)")
    else:
        # Find all instance directories with completed results
        instances_to_eval = []
        for item in sorted(os.listdir(output_dir)):
            item_path = os.path.join(output_dir, item)
            if os.path.isdir(item_path):
                # Check if instance.json exists
                instance_json = os.path.join(item_path, 'instance.json')
                if os.path.exists(instance_json):
                    instances_to_eval.append(item)

        print(f"Found {len(instances_to_eval)} instance(s)")

    if args.max_instances:
        instances_to_eval = instances_to_eval[:args.max_instances]
        print(f"Limiting to first {args.max_instances} instance(s)")

    print()

    # Initialize results tracking
    results = {
        'total': len(instances_to_eval),
        'env_passed': 0,
        'f2p_passed': 0,
        'failed': 0,
        'no_image': 0,
        'error': 0,
        'details': []
    }

    start_time = time.time()

    # Prepare arguments for parallel execution
    eval_args = [
        (inst_id, output_dir, args.namespace, args.arch, args.tag, args.timeout)
        for inst_id in instances_to_eval
    ]

    # Evaluate instances
    if args.parallel > 1:
        # Parallel execution
        print(f"Starting parallel evaluation with {args.parallel} workers...")
        print()

        with ProcessPoolExecutor(max_workers=args.parallel) as executor:
            futures = {
                executor.submit(evaluate_instance_wrapper, arg): arg[0]
                for arg in eval_args
            }

            completed = 0
            for future in as_completed(futures):
                instance_id = futures[future]
                completed += 1

                try:
                    result = future.result()
                    results['details'].append(result)

                    # Update counts
                    if result['f2p_pass']:
                        results['f2p_passed'] += 1
                        status_symbol = '✓ F2P'
                    elif result['env_pass']:
                        results['env_passed'] += 1
                        status_symbol = '✓ ENV'
                    else:
                        results['failed'] += 1
                        status_symbol = '✗'

                        # Update specific failure counts
                        if result['status'] == 'no_image':
                            results['no_image'] += 1
                        elif result['status'] == 'error':
                            results['error'] += 1

                    # Print progress
                    print(f"[{completed}/{len(instances_to_eval)}] {status_symbol} {instance_id}: {result['status']}")

                except Exception as e:
                    print(f"[{completed}/{len(instances_to_eval)}] ✗ {instance_id}: Exception - {str(e)}")
                    results['failed'] += 1
                    results['error'] += 1
                    results['details'].append({
                        'instance_id': instance_id,
                        'status': 'error',
                        'env_pass': False,
                        'f2p_pass': False,
                        'message': str(e)
                    })
    else:
        # Sequential execution
        print("Starting sequential evaluation...")
        print()

        for idx, (inst_id, output_dir, namespace, arch, tag, timeout) in enumerate(eval_args, 1):
            print(f"[{idx}/{len(instances_to_eval)}] Evaluating: {inst_id}")

            result = evaluate_single_instance(inst_id, output_dir, namespace, arch, tag, timeout)
            results['details'].append(result)

            # Update counts
            if result['f2p_pass']:
                results['f2p_passed'] += 1
                print(f"  ✓ F2P: {result['message']}")
            elif result['env_pass']:
                results['env_passed'] += 1
                print(f"  ✓ ENV: {result['message']}")
            else:
                results['failed'] += 1
                print(f"  ✗ {result['status']}: {result['message']}")

                # Update specific failure counts
                if result['status'] == 'no_image':
                    results['no_image'] += 1
                elif result['status'] == 'error':
                    results['error'] += 1

            print()

    elapsed_time = time.time() - start_time

    # Save detailed results
    output_dir_name = os.path.basename(output_dir.rstrip('/'))
    result_file = os.path.join(
        os.path.dirname(output_dir),
        f'evaluation_results_{output_dir_name}.json'
    )

    summary = {
        'timestamp': datetime.now().isoformat(),
        'output_dir': output_dir,
        'namespace': args.namespace,
        'arch': args.arch,
        'tag': args.tag,
        'elapsed_seconds': elapsed_time,
        'statistics': {
            'total': results['total'],
            'f2p_passed': results['f2p_passed'],
            'env_passed': results['env_passed'],
            'failed': results['failed'],
            'f2p_pass_rate': f"{results['f2p_passed'] / results['total'] * 100:.2f}%" if results['total'] > 0 else "0%",
            'env_pass_rate': f"{results['env_passed'] / results['total'] * 100:.2f}%" if results['total'] > 0 else "0%",
            'failure_breakdown': {
                'no_image': results['no_image'],
                'error': results['error'],
            }
        },
        'details': results['details']
    }

    with open(result_file, 'w') as f:
        json.dump(summary, f, indent=2)

    # Print summary
    print()
    print(f"{'='*80}")
    print("EVALUATION SUMMARY")
    print(f"{'='*80}")
    print(f"Total instances:     {results['total']}")
    print(f"F2P Passed:          {results['f2p_passed']} ({results['f2p_passed'] / results['total'] * 100:.1f}%)" if results['total'] > 0 else "F2P Passed: 0")
    print(f"Env Passed:          {results['env_passed']} ({results['env_passed'] / results['total'] * 100:.1f}%)" if results['total'] > 0 else "Env Passed: 0")
    print(f"Failed:              {results['failed']} ({results['failed'] / results['total'] * 100:.1f}%)" if results['total'] > 0 else "Failed: 0")
    print()
    print("Failure breakdown:")
    print(f"  - No Image:        {results['no_image']}")
    print(f"  - Other Error:     {results['error']}")
    print()
    print(f"Elapsed time:        {elapsed_time:.2f} seconds")
    print(f"Average per instance: {elapsed_time / results['total']:.2f} seconds" if results['total'] > 0 else "Average: N/A")
    print()
    print(f"Detailed results saved to: {result_file}")
    print(f"{'='*80}")

    return 0 if results['failed'] == 0 else 1


if __name__ == '__main__':
    exit(main())
