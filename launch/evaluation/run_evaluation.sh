#!/bin/bash
# Quick evaluation script using Docker images

cd "$(dirname "$0")/.."

echo "==================================="
echo "Launch Image Evaluation"
echo "==================================="
echo ""

# Configuration
OUTPUT_DIR="playground/benchmark_python_v3.0"
NAMESPACE="guochuanzhe"
ARCH="x86_64"
TAG="latest"
PARALLEL=20
TIMEOUT=600
INSTALL_PYTEST=true  # Set to true to install pytest in containers before tests

# Check if output directory exists
if [ ! -d "$OUTPUT_DIR" ]; then
    echo "Error: Output directory not found: $OUTPUT_DIR"
    exit 1
fi

# Count available images
# echo "Checking Docker images..."
# IMAGE_COUNT=$(docker images | grep "${NAMESPACE}/sweb.eval" | wc -l)
# echo "Found $IMAGE_COUNT images in namespace: $NAMESPACE"
# echo ""

if [ "$IMAGE_COUNT" -eq 0 ]; then
    echo "Warning: No images found in namespace: $NAMESPACE"
    echo "Please ensure images are created before evaluation."
    echo ""
    echo "To create images, uncomment the commit code in launch/workflow.py"
    exit 1
fi

# Run evaluation
echo "Running evaluation..."
echo "  Output dir:   $OUTPUT_DIR"
echo "  Namespace:    $NAMESPACE"
echo "  Architecture: $ARCH"
echo "  Tag:          $TAG"
echo "  Parallel:     $PARALLEL workers"
echo "  Timeout:      ${TIMEOUT}s"
echo "  Install pytest: $INSTALL_PYTEST"
echo ""

# Build command with optional --install-pytest flag
CMD="python3 evaluation/evaluate_images.py \
  --output_dir \"$OUTPUT_DIR\" \
  --namespace \"$NAMESPACE\" \
  --arch \"$ARCH\" \
  --tag \"$TAG\" \
  --parallel \"$PARALLEL\" \
  --timeout \"$TIMEOUT\""

if [ "$INSTALL_PYTEST" = true ]; then
    CMD="$CMD --install-pytest"
fi

eval $CMD

# Check if evaluation succeeded
if [ $? -ne 0 ]; then
    echo ""
    echo "Evaluation failed!"
    exit 1
fi

echo ""
echo "Evaluation completed successfully!"
echo ""

# Analyze results
RESULT_FILE="playground/evaluation_results_$(basename $OUTPUT_DIR).json"

echo "==================================="
echo "Analysis Results"
echo "==================================="
echo ""

python3 evaluation/analyze_results.py \
  --result_file "$RESULT_FILE" \
  --performance

# List failed instances
echo ""
echo "==================================="
echo "Failed Instances"
echo "==================================="
echo ""

python3 evaluation/analyze_results.py \
  --result_file "$RESULT_FILE" \
  --list_failed

# Export CSV
echo ""
echo "Exporting results to CSV..."
CSV_FILE="playground/evaluation_results_$(basename $OUTPUT_DIR).csv"
python3 evaluation/analyze_results.py \
  --result_file "$RESULT_FILE" \
  --export_csv "$CSV_FILE"

echo ""
echo "==================================="
echo "Done!"
echo "==================================="
echo ""
echo "Results saved to:"
echo "  - $RESULT_FILE"
echo "  - $CSV_FILE"
echo ""
