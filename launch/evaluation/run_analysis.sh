#!/bin/bash
# Script to analyze both evaluation results and costs

cd "$(dirname "$0")/.."

OUTPUT_DIR="playground/benchmark_python_v3.0"

echo "==================================="
echo "Comprehensive Analysis"
echo "==================================="
echo ""

# 1. Analyze evaluation results
echo "1. Analyzing evaluation results..."
RESULT_FILE="playground/evaluation_results_$(basename $OUTPUT_DIR).json"

if [ -f "$RESULT_FILE" ]; then
    python3 evaluation/analyze_results.py \
        --result_file "$RESULT_FILE" \
        --performance
    echo ""
else
    echo "   Warning: $RESULT_FILE not found"
    echo ""
fi

# 2. Analyze costs
echo "2. Analyzing token usage and costs..."
python3 evaluation/analyze_cost.py \
    --base_dir "$OUTPUT_DIR" \
    --verbose

echo ""

# 3. Export both to JSON
echo "3. Exporting results to JSON..."

if [ -f "$RESULT_FILE" ]; then
    python3 evaluation/analyze_results.py \
        --result_file "$RESULT_FILE" \
        --export_csv "playground/evaluation_results_$(basename $OUTPUT_DIR).csv"
fi

python3 evaluation/analyze_cost.py \
    --base_dir "$OUTPUT_DIR" \
    --export_json "playground/cost_analysis_$(basename $OUTPUT_DIR).json"

echo ""
echo "==================================="
echo "Analysis Complete!"
echo "==================================="
echo ""
echo "Files generated:"
if [ -f "$RESULT_FILE" ]; then
    echo "  - playground/evaluation_results_$(basename $OUTPUT_DIR).csv"
fi
echo "  - playground/cost_analysis_$(basename $OUTPUT_DIR).json"
echo ""
