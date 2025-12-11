#!/usr/bin/env python3
"""
Evaluate launch instances using Docker images.
Runs two-stage tests:
  Stage 1: Apply test_patch only (expected to fail)
  Stage 2: Apply fix_patch + test_patch (expected to pass)
"""

import argparse
import docker
import io
import json
import os
import re
import signal
import tarfile
import threading
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
    Write patch content to container using Docker put_archive API.

    This method avoids "argument list too long" errors that occur when
    using heredoc with very large patches.

    Args:
        container: Docker container
        patch_content: Patch content
        dest_path: Destination path in container (e.g., /tmp/test.patch)
    """
    # Create tar archive in memory
    tar_stream = io.BytesIO()
    tar = tarfile.TarFile(fileobj=tar_stream, mode='w')

    # Add patch content to tar
    patch_bytes = patch_content.encode('utf-8')
    tarinfo = tarfile.TarInfo(name=os.path.basename(dest_path))
    tarinfo.size = len(patch_bytes)
    tarinfo.mtime = time.time()
    tar.addfile(tarinfo, io.BytesIO(patch_bytes))
    tar.close()

    # Upload tar to container
    tar_stream.seek(0)
    dest_dir = os.path.dirname(dest_path)
    if not dest_dir:
        dest_dir = '/'

    success = container.put_archive(dest_dir, tar_stream)
    if not success:
        raise RuntimeError(f"Failed to write patch to {dest_path}")


def install_pytest_in_container(container, timeout_seconds: int = 300) -> tuple:
    """
    Install pytest in container if not already installed.

    Args:
        container: Docker container
        timeout_seconds: Timeout for installation

    Returns:
        Tuple of (success: bool, message: str)
    """
    # Check if pytest is already installed
    check_cmd = ["bash", "-c", "python -m pytest --version 2>/dev/null || python3 -m pytest --version 2>/dev/null"]
    check_result = container.exec_run(check_cmd, workdir="/testbed")

    if check_result.exit_code == 0:
        return (True, f"pytest already installed: {check_result.output.decode().strip()}")

    # Try to install pytest
    install_cmd = ["bash", "-c", "pip install pytest 2>&1 || pip3 install pytest 2>&1"]

    try:
        install_result = exec_run_with_timeout(
            container,
            install_cmd,
            timeout_seconds=timeout_seconds,
            workdir="/testbed"
        )

        if install_result.exit_code == 0:
            # Verify installation
            verify_result = container.exec_run(check_cmd, workdir="/testbed")
            if verify_result.exit_code == 0:
                return (True, f"pytest installed successfully: {verify_result.output.decode().strip()}")
            else:
                return (False, "pytest installation verification failed")
        else:
            output = install_result.output.decode() if install_result.output else "No output"
            return (False, f"pytest installation failed: {output}")

    except TimeoutError:
        return (False, f"pytest installation timed out after {timeout_seconds}s")
    except Exception as e:
        return (False, f"pytest installation error: {str(e)}")


def check_test_results(exit_code: int) -> bool:
    """
    Check if all tests passed based on exit code.

    Args:
        exit_code: Exit code from pytest

    Returns:
        True if all tests passed (exit code 0), False otherwise
    """
    return exit_code == 0


def exec_run_with_timeout(container, command, timeout_seconds, **kwargs):
    """
    Execute command in container with timeout.

    Args:
        container: Docker container
        command: Command to execute
        timeout_seconds: Timeout in seconds
        **kwargs: Additional arguments for exec_run

    Returns:
        Tuple of (exit_code, output, timed_out)

    Raises:
        TimeoutError: If command execution exceeds timeout
    """
    result_container = {'exit_code': None, 'output': None, 'exception': None}

    def run_command():
        try:
            result = container.exec_run(command, **kwargs)
            result_container['exit_code'] = result.exit_code
            result_container['output'] = result.output
        except Exception as e:
            result_container['exception'] = e

    thread = threading.Thread(target=run_command)
    thread.daemon = True
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        # Timeout occurred
        raise TimeoutError(f"Command execution exceeded {timeout_seconds} seconds")

    if result_container['exception']:
        raise result_container['exception']

    # Create a mock result object similar to docker exec_run result
    class ExecResult:
        def __init__(self, exit_code, output):
            self.exit_code = exit_code
            self.output = output

    return ExecResult(result_container['exit_code'], result_container['output'])


def evaluate_single_instance(
    instance_id: str,
    output_dir: str,
    namespace: str = "starryzhang",
    arch: str = "x86_64",
    tag: str = "latest",
    timeout: int = 600,
    install_pytest: bool = False,
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
        install_pytest: Install pytest before running tests

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

        # Install pytest if requested
        if install_pytest:
            pytest_success, pytest_message = install_pytest_in_container(container, timeout_seconds=300)
            if not pytest_success:
                result['status'] = 'pytest_install_failed'
                result['message'] = f'Failed to install pytest: {pytest_message}'
                with open(test_only_log_path, 'w') as f:
                    f.write("=== Failed to install pytest ===\n")
                    f.write(pytest_message)
                return result

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
        try:
            test_result = exec_run_with_timeout(
                container,
                ["bash", "-c", test_cmd],
                timeout_seconds=timeout,
                workdir="/testbed"
            )
            test_only_output = test_result.output.decode()
            test_only_exit_code = test_result.exit_code
        except TimeoutError as e:
            result['status'] = 'test_only_timeout'
            result['message'] = f'Stage 1 test execution timed out after {timeout}s'
            test_only_output = f"Test execution timed out after {timeout} seconds"
            test_only_exit_code = -1

            # Save timeout log
            with open(test_only_log_path, 'w') as f:
                f.write("=== Stage 1: Test with only test_patch ===\n\n")
                f.write(f"=== Image ===\n{image_name}\n\n")
                f.write("=== Test Files ===\n")
                for tf in test_files:
                    f.write(f"  - {tf}\n")
                f.write("\n=== Test Command ===\n")
                f.write(f"{test_cmd}\n\n")
                f.write("=== TIMEOUT ===\n")
                f.write(f"Test execution exceeded timeout of {timeout} seconds\n")
            return result

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

        # Install pytest if requested
        if install_pytest:
            pytest_success, pytest_message = install_pytest_in_container(container, timeout_seconds=300)
            if not pytest_success:
                result['status'] = 'pytest_install_failed_stage2'
                result['message'] = f'Failed to install pytest in stage 2: {pytest_message}'
                with open(both_patches_log_path, 'w') as f:
                    f.write("=== Failed to install pytest (stage 2) ===\n")
                    f.write(pytest_message)
                return result

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
        try:
            test_result = exec_run_with_timeout(
                container,
                ["bash", "-c", test_cmd],
                timeout_seconds=timeout,
                workdir="/testbed"
            )
            both_patches_output = test_result.output.decode()
            both_patches_exit_code = test_result.exit_code
        except TimeoutError as e:
            result['status'] = 'both_patches_timeout'
            result['message'] = f'Stage 2 test execution timed out after {timeout}s'
            both_patches_output = f"Test execution timed out after {timeout} seconds"
            both_patches_exit_code = -1

            # Save timeout log
            with open(both_patches_log_path, 'w') as f:
                f.write("=== Stage 2: Test with both fix_patch and test_patch ===\n\n")
                f.write(f"=== Image ===\n{image_name}\n\n")
                f.write("=== Test Files ===\n")
                for tf in test_files:
                    f.write(f"  - {tf}\n")
                f.write("\n=== Test Command ===\n")
                f.write(f"{test_cmd}\n\n")
                f.write("=== TIMEOUT ===\n")
                f.write(f"Test execution exceeded timeout of {timeout} seconds\n")
            return result

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
    parser.add_argument(
        '--install-pytest',
        action='store_true',
        help='Install pytest in containers before running tests (default: False)'
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
    print(f"Install pytest:   {args.install_pytest}")
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
        (inst_id, output_dir, args.namespace, args.arch, args.tag, args.timeout, args.install_pytest)
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

        for idx, (inst_id, output_dir, namespace, arch, tag, timeout, install_pytest) in enumerate(eval_args, 1):
            print(f"[{idx}/{len(instances_to_eval)}] Evaluating: {inst_id}")

            result = evaluate_single_instance(inst_id, output_dir, namespace, arch, tag, timeout, install_pytest)
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
