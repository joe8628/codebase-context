#!/usr/bin/env bash
# ccindex-init.sh
#
# Runs `ccindex init`, and if fastembed fails to find the ONNX model
# (network unavailable), copies the local model files into the expected
# fastembed cache path and retries automatically.
#
# Local model files are expected at:
#   <repo-root>/models/jina-embeddings-v2-base-code/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_MODEL_DIR="$SCRIPT_DIR/models/jina-embeddings-v2-base-code"

run_init() {
    ccindex init "$@" 2>&1
}

copy_model_to_cache() {
    local target_dir="$1"

    if [[ ! -d "$LOCAL_MODEL_DIR" ]]; then
        echo "ERROR: Local model not found at $LOCAL_MODEL_DIR"
        echo "       Download it first with:"
        echo "         mkdir -p models/jina-embeddings-v2-base-code/onnx"
        echo "         BASE=https://huggingface.co/jinaai/jina-embeddings-v2-base-code/resolve/main"
        echo "         wget -P models/jina-embeddings-v2-base-code/onnx  \$BASE/onnx/model.onnx"
        echo "         wget -P models/jina-embeddings-v2-base-code       \$BASE/config.json \$BASE/tokenizer.json \$BASE/tokenizer_config.json \$BASE/special_tokens_map.json"
        exit 1
    fi

    echo ">>> Copying local model files to fastembed cache..."
    mkdir -p "$target_dir/onnx"
    cp "$LOCAL_MODEL_DIR/onnx/model.onnx"          "$target_dir/onnx/model.onnx"
    cp "$LOCAL_MODEL_DIR/config.json"               "$target_dir/config.json"
    cp "$LOCAL_MODEL_DIR/tokenizer.json"            "$target_dir/tokenizer.json"
    cp "$LOCAL_MODEL_DIR/tokenizer_config.json"     "$target_dir/tokenizer_config.json"
    cp "$LOCAL_MODEL_DIR/special_tokens_map.json"   "$target_dir/special_tokens_map.json"
    echo ">>> Model copied successfully."
}

echo ">>> Running ccindex init..."
output=$(run_init "$@") || true
echo "$output"

# Check if the failure is a fastembed NoSuchFile error
if echo "$output" | grep -q "NoSuchFile" && echo "$output" | grep -q "fastembed"; then
    # Extract the expected model directory from the error message
    # Error line looks like: Load model from /path/to/.../onnx/model.onnx failed
    model_onnx_path=$(echo "$output" | grep -oP '(?<=Load model from )[^ ]+(?= failed)' | head -1)

    if [[ -z "$model_onnx_path" ]]; then
        echo "ERROR: Could not parse model path from error output."
        exit 1
    fi

    # The snapshot dir is two levels up from model.onnx (onnx/model.onnx)
    snapshot_dir="$(dirname "$(dirname "$model_onnx_path")")"

    echo ">>> fastembed model not found at: $snapshot_dir"
    copy_model_to_cache "$snapshot_dir"

    echo ">>> Retrying ccindex init..."
    ccindex init "$@"
elif echo "$output" | grep -q "Error\|error\|Traceback"; then
    # Some other error — don't swallow it
    exit 1
fi
