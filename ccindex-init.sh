#!/usr/bin/env bash
# ccindex-init.sh
#
# Wrapper for `ccindex init` that works in airgapped / Docker environments.
#
# Sets CC_MODELS_DIR and HF_HUB_OFFLINE so the Python embedder skips the
# network download, fails fast with a NoSuchFile error, reads the expected
# snapshot path from that error, copies from CC_MODELS_DIR, and retries.
#
# Local model files are expected at:
#   <repo-root>/models/jina-embeddings-v2-base-code/
#
# Usage:
#   ./ccindex-init.sh [ccindex init options]
#
# To override the local model directory:
#   CC_MODELS_DIR=/some/other/path ./ccindex-init.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default CC_MODELS_DIR to <repo-root>/models if present and not already set
if [[ -z "${CC_MODELS_DIR:-}" && -d "$SCRIPT_DIR/models" ]]; then
    CC_MODELS_DIR="$SCRIPT_DIR/models"
fi

if [[ -n "${CC_MODELS_DIR:-}" ]]; then
    export CC_MODELS_DIR
    # Skip the slow HF download; embedder seeds from CC_MODELS_DIR on NoSuchFile
    export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
    echo ">>> Offline mode: CC_MODELS_DIR=$CC_MODELS_DIR"
else
    echo "WARNING: models/ not found and CC_MODELS_DIR is not set — will attempt download."
    echo "         Place model files under models/jina-embeddings-v2-base-code/ to avoid this."
fi

exec ccindex init "$@"
