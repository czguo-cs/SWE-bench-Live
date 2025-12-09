# Launch Image Evaluation

This directory contains scripts to evaluate launch instances using Docker images.

## Overview

The evaluation uses Docker images to run two-stage tests:

1. **Stage 1 (Test Only)**: Apply only `test_patch` and run tests
   - Expected: Tests should fail (showing the bug exists)

2. **Stage 2 (Both Patches)**: Apply `fix_patch` + `test_patch` and run tests
   - Expected: All tests should pass (showing the bug is fixed)

## Success Criteria

- **F2P Pass**: Stage 1 failed AND Stage 2 passed ✓✓ (完美)
- **Env Pass**: Stage 2 passed (Stage 1 也通过了) ✓ (环境正确但缺少测试)
- **Failed**: Stage 2 failed ✗ (环境配置失败)

## Image Naming Convention

Images are named using the pattern:
```
{namespace}/sweb.eval.{arch}.{instance_id.lower()}:{tag}
```

Where `__` in instance_id is replaced with `_1776_`.

**Examples:**
```python
# Instance ID: alteryx__featuretools-1018
# Image name:  starryzhang/sweb.eval.x86_64.alteryx_1776_featuretools-1018:latest

# Instance ID: pydicom__pydicom-955
# Image name:  starryzhang/sweb.eval.x86_64.pydicom_1776_pydicom-955:latest
```

## Tools

### 1. `evaluate_images.py` (Main Evaluation Script)

Evaluates instances using Docker images.

**Usage:**

```bash
# Evaluate all instances
python3 evaluation/evaluate_images.py \
  --output_dir playground/benchmark_python_v3.0

# Evaluate specific instances
python3 evaluation/evaluate_images.py \
  --output_dir playground/benchmark_python_v3.0 \
  --instances alteryx__featuretools-1018 pydicom__pydicom-955

# Use custom namespace and parallel execution
python3 evaluation/evaluate_images.py \
  --output_dir playground/benchmark_python_v3.0 \
  --namespace starryzhang \
  --arch x86_64 \
  --tag latest \
  --parallel 4 \
  --timeout 600

# Limit number of instances
python3 evaluation/evaluate_images.py \
  --output_dir playground/benchmark_python_v3.0 \
  --max_instances 10
```

**Parameters:**
- `--output_dir`: Directory containing instance subdirectories (required)
- `--namespace`: Docker registry namespace (default: starryzhang)
- `--arch`: Architecture - x86_64 or arm64 (default: x86_64)
- `--tag`: Image tag (default: latest)
- `--instances`: Specific instance IDs to evaluate (optional)
- `--parallel`: Number of parallel workers (default: 1)
- `--timeout`: Timeout in seconds per instance (default: 600)
- `--max_instances`: Maximum number of instances to evaluate (optional)

**Output:**
- Creates `evaluation_logs/` in each instance directory
  - `test_only.log`: Stage 1 test output
  - `both_patches.log`: Stage 2 test output
  - `error.log`: Error details (if any)
- Generates `evaluation_results_{output_dir_name}.json` with detailed results

### 2. `analyze_results.py` (Results Analysis)

Analyze and summarize evaluation results (same as before).

**Usage:**

```bash
# Show statistics and list all instances by status
python3 evaluation/analyze_results.py \
  --result_file evaluation_results_benchmark_python_v3.0.json

# List only failed instances
python3 evaluation/analyze_results.py \
  --result_file evaluation_results_benchmark_python_v3.0.json \
  --list_failed

# Export to CSV with performance stats
python3 evaluation/analyze_results.py \
  --result_file evaluation_results_benchmark_python_v3.0.json \
  --export_csv results.csv \
  --performance
```

## Quick Start

```bash
cd /path/to/launch

# 1. Run evaluation (4 parallel workers)
python3 evaluation/evaluate_images.py \
  --output_dir playground/benchmark_python_v3.0 \
  --namespace starryzhang \
  --parallel 4

# 2. Analyze results
python3 evaluation/analyze_results.py \
  --result_file playground/evaluation_results_benchmark_python_v3.0.json \
  --list_failed \
  --performance

# 3. Export to CSV
python3 evaluation/analyze_results.py \
  --result_file playground/evaluation_results_benchmark_python_v3.0.json \
  --export_csv results.csv
```

## Evaluation Flow

```
┌─────────────────────────────────────────┐
│ 1. Load instance.json                   │
│    - Get test_patch and fix_patch       │
│    - Extract test file paths            │
└───────────────┬─────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────┐
│ 2. Get Docker image                     │
│    Format: {namespace}/sweb.eval.       │
│           {arch}.{instance_id}:{tag}    │
│    Check if image exists                │
└───────────────┬─────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────┐
│ 3. Stage 1: Test Only                   │
│    - Start container from image         │
│    - Apply test_patch                   │
│    - Run pytest on test files           │
│    - Check: Should FAIL (exit code ≠ 0) │
│    - Stop and remove container          │
└───────────────┬─────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────┐
│ 4. Stage 2: Both Patches                │
│    - Start new container from image     │
│    - Apply fix_patch                    │
│    - Apply test_patch                   │
│    - Run pytest on test files           │
│    - Check: Should PASS (exit code = 0) │
│    - Stop and remove container          │
└───────────────┬─────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────┐
│ 5. Determine Result                     │
│    - F2P Pass: Stage1 fail & Stage2 pass│
│    - Env Pass: Stage2 pass only         │
│    - Failed: Stage2 fail                │
└─────────────────────────────────────────┘
```

## Output Files

### evaluation_results_{output_dir_name}.json

```json
{
  "timestamp": "2025-12-09T17:00:00.123456",
  "output_dir": "/path/to/playground/benchmark_python_v3.0",
  "namespace": "starryzhang",
  "arch": "x86_64",
  "tag": "latest",
  "elapsed_seconds": 1234.56,
  "statistics": {
    "total": 100,
    "f2p_passed": 75,
    "env_passed": 10,
    "failed": 15,
    "f2p_pass_rate": "75.00%",
    "env_pass_rate": "10.00%",
    "failure_breakdown": {
      "no_image": 5,
      "error": 10
    }
  },
  "details": [
    {
      "instance_id": "alteryx__featuretools-1018",
      "image_name": "starryzhang/sweb.eval.x86_64.alteryx_1776_featuretools-1018:latest",
      "status": "f2p_passed",
      "f2p_pass": true,
      "env_pass": true,
      "test_only_passed": false,
      "both_patches_passed": true,
      "test_only_time": 12.34,
      "both_patches_time": 13.45,
      "message": "F2P passed: test_only failed, both_patches passed"
    }
  ]
}
```

### Per-Instance Logs

For each instance, logs are saved in `{instance_dir}/evaluation_logs/`:

- **test_only.log**: Stage 1 details (test_patch only)
- **both_patches.log**: Stage 2 details (fix_patch + test_patch)
- **error.log**: Error details (if any)

## Status Types

- `f2p_passed`: F2P verification passed ✓✓
- `env_passed`: Environment passed ✓
- `failed`: Tests failed ✗
- `no_image`: Docker image not found
- `no_instance_dir`: Instance directory missing
- `no_instance_json`: instance.json not found
- `no_test_patch`: test_patch is empty
- `no_test_files`: No test files in test_patch
- `test_patch_apply_failed`: Failed to apply test_patch
- `fix_patch_apply_failed`: Failed to apply fix_patch
- `error`: Unexpected error

## Comparison with Other Methods

| Aspect | Repo2Run | SWE-bench | Launch (This) |
|--------|----------|-----------|---------------|
| Input | Dockerfile | Pre-built images | Launch images |
| Build | `docker build` | Pre-built | Pre-built |
| Test Approach | 2-stage F2P | 2-stage F2P | 2-stage F2P |
| Result Check | Detailed P2P/F2P | Detailed P2P/F2P | Simple pass/fail |
| Container | Temporary | Temporary | Temporary |
| Cleanup | Auto | Auto | Auto |

## Notes

1. **Image Must Exist**: Images must be built before evaluation
2. **Test Files Auto-Detected**: Automatically extracted from test_patch
3. **Simple Pass/Fail**: Only checks exit code (0=pass, non-zero=fail)
4. **Stateless Containers**: Each stage uses a fresh container
5. **Automatic Cleanup**: Containers are removed after each stage

## Troubleshooting

### Image Not Found

If images don't exist, check:

```bash
# List all images in namespace
docker images | grep "starryzhang/sweb.eval"

# Check specific instance image
docker images | grep "alteryx_1776_featuretools-1018"
```

To build images, uncomment the commit code in `launch/workflow.py:118-122`:

```python
if state.get("success", False):
    key = f"sweb.eval.{ARCH}.{instance_id.lower()}"
    key = f"{NAMESPACE}/{key}".replace("__", "_1776_")
    session.commit(image_name=key, push=False)
```

### Patch Application Failed

Check logs for details:

```bash
cat playground/benchmark_python_v3.0/{instance_id}/evaluation_logs/test_only.log
```

Common issues:
- Patch conflicts with existing code
- File paths don't match repository structure
- Git working directory is dirty

### Performance

Use parallel execution for better performance:

```bash
# Use 4 workers (adjust based on available resources)
python3 evaluation/evaluate_images.py \
  --output_dir playground/benchmark_python_v3.0 \
  --parallel 4
```

**Resource Requirements:**
- Each worker runs 2 containers per instance (stages 1 & 2)
- Containers are short-lived (only during testing)
- Memory: ~2GB per instance image

## Example Workflows

### Basic Evaluation

```bash
# Evaluate all instances with default settings
python3 evaluation/evaluate_images.py \
  --output_dir playground/benchmark_python_v3.0

# View results
python3 evaluation/analyze_results.py \
  --result_file playground/evaluation_results_benchmark_python_v3.0.json
```

### Custom Namespace

```bash
# Use different namespace (e.g., for different model runs)
python3 evaluation/evaluate_images.py \
  --output_dir playground/benchmark_python_v3.0 \
  --namespace my_namespace \
  --tag v1.0
```

### Parallel Evaluation

```bash
# Fast evaluation with 8 workers
python3 evaluation/evaluate_images.py \
  --output_dir playground/benchmark_python_v3.0 \
  --parallel 8 \
  --timeout 300

# Analyze with full details
python3 evaluation/analyze_results.py \
  --result_file playground/evaluation_results_benchmark_python_v3.0.json \
  --list_failed \
  --performance \
  --export_csv full_results.csv
```

### Debug Single Instance

```bash
# Evaluate one instance for debugging
python3 evaluation/evaluate_images.py \
  --output_dir playground/benchmark_python_v3.0 \
  --instances alteryx__featuretools-1018 \
  --timeout 1800

# Check logs
cat playground/benchmark_python_v3.0/alteryx__featuretools-1018/evaluation_logs/test_only.log
cat playground/benchmark_python_v3.0/alteryx__featuretools-1018/evaluation_logs/both_patches.log
```

## Integration with Launch Workflow

To enable automatic image creation during launch, modify `launch/workflow.py`:

```python
# In save_result function (around line 109-122)
if state.get("success", False):
    logger.info("Setup completed successfully, now commit into swebench image.")

    ARCH = "x86_64"
    NAMESPACE = "starryzhang"  # Change to your namespace

    key = f"sweb.eval.{ARCH}.{instance_id.lower()}"
    key = f"{NAMESPACE}/{key}".replace("__", "_1776_")

    try:
        session.commit(image_name=key, push=False)  # Uncomment this line
        logger.info(f"Image {key} committed successfully.")
    except Exception as e:
        logger.error(f"Failed to commit image: {e}")
```

Then run launch followed by evaluation:

```bash
# 1. Run launch to setup environments and create images
python3 launch.py --config config.json

# 2. Evaluate the created images
python3 evaluation/evaluate_images.py \
  --output_dir playground/benchmark_python_v3.0 \
  --namespace starryzhang \
  --parallel 4

# 3. Analyze results
python3 evaluation/analyze_results.py \
  --result_file playground/evaluation_results_benchmark_python_v3.0.json
```
