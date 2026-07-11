#!/usr/bin/env bash
# ============================================================================
# Zer0Fit MCP — Interactive Installer
# ============================================================================
# Detects the host architecture and GPU type, configures the Docker build
# with the correct CUDA base image and PyTorch wheel index, builds and
# launches the Zer0Fit container, then downloads model weights to disk
# cache and loads them into VRAM so the user doesn't experience delays
# on first use.
#
# Usage:
#   ./install.sh              # interactive (menu-driven configuration)
#   ./install.sh --non-interactive   # no prompts, use defaults
#
# The script creates a .env file with the detected configuration so
# subsequent `docker compose up` runs don't need the env vars on the
# command line.
# ============================================================================

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Banner ────────────────────────────────────────────────────────────────
cat << 'BANNER'
  ╔══════════════════════════════════════════════════════════╗
  ║         Zer0Fit MCP — Zero-Shot Inference Server          ║
  ║     TimesFM 2.5  +  TabFM v1.0.0  via  MCP / SSE          ║
  ╚══════════════════════════════════════════════════════════╝
BANNER

# ── Pre-flight checks ─────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

info "Working directory: $SCRIPT_DIR"

# Check OS — Zer0Fit requires Linux with NVIDIA CUDA (not macOS)
OS_NAME="$(uname -s)"
if [[ "$OS_NAME" == "Darwin" ]]; then
    error "macOS is not supported. Zer0Fit requires NVIDIA CUDA (Linux/x86_64 or Linux/ARM64).\n  Deploy on an Ubuntu 24.04 server with an NVIDIA GPU."
fi
if [[ "$OS_NAME" != "Linux" ]]; then
    error "Unsupported OS: $OS_NAME. Zer0Fit requires Linux with NVIDIA CUDA."
fi
ok "Operating system: $OS_NAME"

# Check Docker
if ! command -v docker &>/dev/null; then
    error "Docker is not installed. Please install Docker first:\n  https://docs.docker.com/engine/install/"
fi

# Check Docker Compose
if docker compose version &>/dev/null; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
else
    error "Docker Compose is not installed. Please install Docker Compose v2+."
fi
ok "Docker: $(docker --version)"
ok "Compose: $($COMPOSE_CMD version 2>/dev/null | head -1)"

# Check NVIDIA Container Toolkit
if ! command -v nvidia-ctk &>/dev/null && ! docker info 2>/dev/null | grep -q "nvidia"; then
    error "NVIDIA Container Toolkit not detected. Zer0Fit requires an NVIDIA GPU.\n  Install it: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
fi
ok "NVIDIA Container Toolkit detected"

# Verify a CUDA device is actually present
if ! command -v nvidia-smi &>/dev/null; then
    error "nvidia-smi not found. No NVIDIA GPU detected on this host.\n  Zer0Fit requires an NVIDIA GPU with at least 16GB VRAM."
fi
GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || echo "")
if [[ -z "$GPU_NAME" ]]; then
    error "nvidia-smi did not return a GPU. No NVIDIA GPU detected.\n  Zer0Fit requires an NVIDIA GPU with at least 16GB VRAM."
fi
ok "GPU: $GPU_NAME"

# ── Architecture detection ────────────────────────────────────────────────
ARCH=$(uname -m)
info "Detected architecture: $ARCH"

case "$ARCH" in
    x86_64|amd64)
        BUILDARCH="amd64"
        BASE_IMAGE="nvidia/cuda:12.4.1-base-ubuntu24.04"
        TORCH_INDEX="https://download.pytorch.org/whl/cu124"
        ARCH_LABEL="x86_64 (CUDA 12.4)"
        ;;
    aarch64|arm64)
        BUILDARCH="arm64"
        BASE_IMAGE="nvidia/cuda:13.2.0-base-ubuntu24.04"
        TORCH_INDEX="https://download.pytorch.org/whl/nightly/cu130"
        ARCH_LABEL="ARM64 (CUDA 13.2 / Blackwell)"
        ;;
    *)
        warn "Unknown architecture: $ARCH. Defaulting to x86_64."
        BUILDARCH="amd64"
        BASE_IMAGE="nvidia/cuda:12.4.1-base-ubuntu24.04"
        TORCH_INDEX="https://download.pytorch.org/whl/cu124"
        ARCH_LABEL="x86_64 (CUDA 12.4) [fallback]"
        ;;
esac
ok "Target: $ARCH_LABEL"

# ── Configuration ─────────────────────────────────────────────────────────
INTERACTIVE=true
if [[ "${1:-}" == "--non-interactive" ]]; then
    INTERACTIVE=false
fi

# Default values
ZER0FIT_VRAM_TTL="${ZER0FIT_VRAM_TTL:-300}"
ZER0FIT_PORT="${ZER0FIT_PORT:-8002}"
ZER0FIT_UPLOAD_TTL_HOURS="${ZER0FIT_UPLOAD_TTL_HOURS:-6}"
ZER0FIT_MAX_UPLOAD_MB="${ZER0FIT_MAX_UPLOAD_MB:-50}"
TABFM_REF="${TABFM_REF:-d8678b6895f1428a468d4cc299c1ff4cf704e726}"

if $INTERACTIVE; then
    echo ""
    echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD} Configuration${NC}"
    echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  Current settings:"
    echo ""
    echo "  1) MCP server port:            $ZER0FIT_PORT"
    echo "  2) VRAM idle TTL (seconds):    $ZER0FIT_VRAM_TTL  (auto-unload model after this many idle seconds)"
    echo "  3) Upload file TTL (hours):    $ZER0FIT_UPLOAD_TTL_HOURS  (auto-delete uploaded files after this many hours)"
    echo "  4) Max upload size (MB):       $ZER0FIT_MAX_UPLOAD_MB"
    echo ""
    echo -e "  ${BOLD}Press ENTER to accept all defaults and continue.${NC}"
    echo "  Or type a number (1-4) to change that setting."
    echo ""

    while true; do
        read -rp "  Choice [ENTER=continue | 1-4]: " choice

        if [[ -z "$choice" ]]; then
            # Empty input — accept defaults and continue
            break
        fi

        case "$choice" in
            1)
                read -rp "  Enter new MCP server port (1024-65535) [$ZER0FIT_PORT]: " new_port
                if [[ -n "$new_port" ]]; then
                    if [[ "$new_port" =~ ^[0-9]+$ ]] && [[ "$new_port" -ge 1024 ]] && [[ "$new_port" -le 65535 ]]; then
                        ZER0FIT_PORT="$new_port"
                        echo -e "  ${GREEN}✓${NC} MCP port set to $ZER0FIT_PORT"
                    else
                        echo -e "  ${RED}Invalid port. Must be 1024-65535.${NC}"
                    fi
                fi
                ;;
            2)
                read -rp "  Enter VRAM idle TTL in seconds (60-3600) [$ZER0FIT_VRAM_TTL]: " new_ttl
                if [[ -n "$new_ttl" ]]; then
                    if [[ "$new_ttl" =~ ^[0-9]+$ ]] && [[ "$new_ttl" -ge 60 ]] && [[ "$new_ttl" -le 3600 ]]; then
                        ZER0FIT_VRAM_TTL="$new_ttl"
                        echo -e "  ${GREEN}✓${NC} VRAM TTL set to ${ZER0FIT_VRAM_TTL}s"
                    else
                        echo -e "  ${RED}Invalid TTL. Must be 60-3600.${NC}"
                    fi
                fi
                ;;
            3)
                read -rp "  Enter upload file TTL in hours (1-168) [$ZER0FIT_UPLOAD_TTL_HOURS]: " new_upload_ttl
                if [[ -n "$new_upload_ttl" ]]; then
                    if [[ "$new_upload_ttl" =~ ^[0-9]+$ ]] && [[ "$new_upload_ttl" -ge 1 ]] && [[ "$new_upload_ttl" -le 168 ]]; then
                        ZER0FIT_UPLOAD_TTL_HOURS="$new_upload_ttl"
                        echo -e "  ${GREEN}✓${NC} Upload TTL set to ${ZER0FIT_UPLOAD_TTL_HOURS}h"
                    else
                        echo -e "  ${RED}Invalid TTL. Must be 1-168.${NC}"
                    fi
                fi
                ;;
            4)
                read -rp "  Enter max upload size in MB (10-500) [$ZER0FIT_MAX_UPLOAD_MB]: " new_max
                if [[ -n "$new_max" ]]; then
                    if [[ "$new_max" =~ ^[0-9]+$ ]] && [[ "$new_max" -ge 10 ]] && [[ "$new_max" -le 500 ]]; then
                        ZER0FIT_MAX_UPLOAD_MB="$new_max"
                        echo -e "  ${GREEN}✓${NC} Max upload size set to ${ZER0FIT_MAX_UPLOAD_MB}MB"
                    else
                        echo -e "  ${RED}Invalid size. Must be 10-500.${NC}"
                    fi
                fi
                ;;
            *)
                echo -e "  ${RED}Invalid choice. Press ENTER to continue or type 1-4.${NC}"
                ;;
        esac

        # Re-display updated settings
        echo ""
        echo "  Updated settings:"
        echo "  1) MCP server port:            $ZER0FIT_PORT"
        echo "  2) VRAM idle TTL (seconds):    $ZER0FIT_VRAM_TTL"
        echo "  3) Upload file TTL (hours):    $ZER0FIT_UPLOAD_TTL_HOURS"
        echo "  4) Max upload size (MB):       $ZER0FIT_MAX_UPLOAD_MB"
        echo ""
        echo -e "  ${BOLD}Press ENTER to continue, or type another number (1-4).${NC}"
        echo ""
    done
fi

info "Configuration:"
info "  Architecture:    $ARCH_LABEL"
info "  Base image:      $BASE_IMAGE"
info "  VRAM TTL:        ${ZER0FIT_VRAM_TTL}s"
info "  Port:            $ZER0FIT_PORT"
info "  Upload TTL:      ${ZER0FIT_UPLOAD_TTL_HOURS}h"
info "  Max upload:      ${ZER0FIT_MAX_UPLOAD_MB}MB"
info "  TabFM git ref:   $TABFM_REF"

# ── Write .env file ────────────────────────────────────────────────────────
ENV_FILE="$SCRIPT_DIR/.env"
cat > "$ENV_FILE" << EOF
# Zer0Fit configuration — auto-generated by install.sh
# Architecture: $ARCH_LABEL
# Generated: $(date -u +\"%Y-%m-%dT%H:%M:%SZ\")

BUILDARCH=$BUILDARCH
BASE_IMAGE=$BASE_IMAGE
TORCH_INDEX=$TORCH_INDEX
ZER0FIT_VRAM_TTL=$ZER0FIT_VRAM_TTL
ZER0FIT_PORT=$ZER0FIT_PORT
ZER0FIT_UPLOAD_TTL_HOURS=$ZER0FIT_UPLOAD_TTL_HOURS
ZER0FIT_MAX_UPLOAD_MB=$ZER0FIT_MAX_UPLOAD_MB
ZER0FIT_WEBUI_DIR=/app/webui_data/uploads
ZER0FIT_DEBUG=false
TABFM_REF=$TABFM_REF
EOF
ok ".env file written to $ENV_FILE"

# ── Create data directory if it doesn't exist ─────────────────────────────
mkdir -p "$SCRIPT_DIR/data"
ok "Data directory ready: $SCRIPT_DIR/data/"

# ── Summary before build ──────────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD} Ready to build and deploy:${NC}"
echo -e "  • CUDA base image: $BASE_IMAGE"
echo -e "  • PyTorch (pre-built, $ARCH_LABEL)"
echo -e "  • TimesFM 2.5 (200M params) — weights downloaded to cache after build"
echo -e "  • TabFM v1.0.0 — weights downloaded to cache after build"
echo -e "  • MCP server on port $ZER0FIT_PORT"
echo ""
echo -e " Build takes 5-10 minutes (downloading torch + deps)."
echo -e " After build, model weights are downloaded to disk cache and"
echo -e " loaded into GPU VRAM (takes 1-3 min per model)."
echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
echo ""

if $INTERACTIVE; then
    read -rp "Proceed with build? [Y/n] " proceed
    if [[ "${proceed,,}" == "n" ]]; then
        info "Aborted. Run ./install.sh again when ready."
        exit 0
    fi
fi

# ── Build and launch ──────────────────────────────────────────────────────
info "Building Docker image (this may take 5-10 minutes on first run)..."
echo ""

# Build first, then start detached so the script can verify health.
$COMPOSE_CMD --profile gpu build 2>&1 | while IFS= read -r line; do
    if [[ "$line" =~ ^#[0-9]+\ [0-9]+\. ]] || \
       [[ "$line" =~ \ Built\ $ ]] || \
       [[ "$line" =~ (Building|Downloading|Installing) ]]; then
        echo "  $line"
    else
        echo "$line" >&2
    fi
done

info "Starting container (detached)..."
$COMPOSE_CMD --profile gpu up -d 2>&1

# ── Verify server is running ──────────────────────────────────────────────
echo ""
info "Verifying server is running..."
sleep 5

HEALTH_URL="http://127.0.0.1:$ZER0FIT_PORT/health"

# Wait up to 30 seconds for the server to come up
for i in $(seq 1 6); do
    if curl -sf "$HEALTH_URL" &>/dev/null; then
        break
    fi
    info "Waiting for server to start... ($i/6)"
    sleep 5
done

if ! curl -sf "$HEALTH_URL" &>/dev/null; then
    warn "Server did not respond at $HEALTH_URL after 30 seconds."
    warn "Check logs: $COMPOSE_CMD --profile gpu logs"
    warn "You can re-run the model download later with: ./install.sh --preload"
    exit 1
fi

HEALTH=$(curl -s "$HEALTH_URL")
ok "Server is live: $HEALTH"

# ── Pre-download and load models ──────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD} Downloading model weights and loading into VRAM${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "  This downloads model weights from Hugging Face Hub (~1.5GB total)"
echo "  to the container's disk cache, then loads them into GPU VRAM."
echo "  Weights are cached on disk — subsequent restarts load from cache"
echo "  (no re-download). VRAM residency is cleared after 5 min idle."
echo "  This takes 1-3 minutes per model (depending on network speed)."
echo ""

# ── Pre-load TimesFM ──────────────────────────────────────────────────────
echo -e "${BLUE}[1/2]${NC} Downloading TimesFM 2.5 weights (200M params)..."
echo "    Downloading from huggingface.co → disk cache, then loading into VRAM..."
# The preload endpoint triggers the download + VRAM load.
# We also tail the container logs so the user sees download progress.
PRELOAD_URL="http://127.0.0.1:$ZER0FIT_PORT/preload"

# Stream container logs in background so user sees download progress
$COMPOSE_CMD --profile gpu logs -f --since 0s 2>&1 \
    | grep -i -E "(timesfm|download|loading|huggingface|model)" &
LOG_PID=$!

TIMESFM_RESULT=$(curl -s -X POST "$PRELOAD_URL" \
    -H "Content-Type: application/json" \
    -d '{"model": "timesfm"}' \
    --max-time 300 2>&1) || true

# Stop log streaming
kill "$LOG_PID" 2>/dev/null || true
wait "$LOG_PID" 2>/dev/null || true

if echo "$TIMESFM_RESULT" | grep -q '"timesfm": "loaded"'; then
    ok "TimesFM 2.5 weights cached on disk and loaded into VRAM ✅"
else
    warn "TimesFM pre-load result: $TIMESFM_RESULT"
    warn "TimesFM will be downloaded on first forecast call instead."
fi

# ── Pre-load TabFM ────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}[2/2]${NC} Downloading TabFM v1.0.0 weights..."
echo "    Downloading from huggingface.co → disk cache, then loading into VRAM..."

# Stream logs again for TabFM download
$COMPOSE_CMD --profile gpu logs -f --since 0s 2>&1 \
    | grep -i -E "(tabfm|download|loading|huggingface|model)" &
LOG_PID=$!

TABFM_RESULT=$(curl -s -X POST "$PRELOAD_URL" \
    -H "Content-Type: application/json" \
    -d '{"model": "tabfm"}' \
    --max-time 300 2>&1) || true

# Stop log streaming
kill "$LOG_PID" 2>/dev/null || true
wait "$LOG_PID" 2>/dev/null || true

if echo "$TABFM_RESULT" | grep -q '"tabfm": "loaded"'; then
    ok "TabFM v1.0.0 weights cached on disk and loaded into VRAM ✅"
else
    warn "TabFM pre-load result: $TABFM_RESULT"
    warn "TabFM will be downloaded on first tabular call instead."
fi

# ── Model health check ────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD} Model Health Check${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Check if HuggingFace cache has the model weights
echo "Checking Hugging Face model cache..."
HF_CACHE=$(docker exec zer0fit_mcp_server ls /root/.cache/huggingface/hub/ 2>/dev/null || echo "")

if echo "$HF_CACHE" | grep -q "timesfm"; then
    ok "TimesFM weights cached ✅"
else
    warn "TimesFM weights not found in cache"
fi

if echo "$HF_CACHE" | grep -q "tabfm"; then
    ok "TabFM weights cached ✅"
else
    warn "TabFM weights not found in cache"
fi

# Check final health state
echo ""
info "Final health check..."
FINAL_HEALTH=$(curl -s "$HEALTH_URL" 2>/dev/null || echo "{}")
FINAL_STATE=$(echo "$FINAL_HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state','unknown'))" 2>/dev/null || echo "unknown")
ACTIVE_MODEL=$(echo "$FINAL_HEALTH" | python3 -c "import sys,json; m=json.load(sys.stdin).get('active_model'); print(m if m else 'none')" 2>/dev/null || echo "unknown")

echo ""
echo -e "  Server state:     ${BOLD}$FINAL_STATE${NC}"
echo -e "  Active model:     ${BOLD}$ACTIVE_MODEL${NC}"
echo ""

# ── Final summary ─────────────────────────────────────────────────────────
echo -e "${GREEN}${BOLD}  ══════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  Zer0Fit MCP server deployed successfully!${NC}"
echo -e "${GREEN}${BOLD}  ══════════════════════════════════════════════${NC}"
echo ""
echo -e "${BOLD}  Server endpoints:${NC}"
echo "  MCP (HTTP):  http://YOUR-SERVER-IP:$ZER0FIT_PORT/mcp  ← use this for Open WebUI"
echo "  MCP (SSE):   http://YOUR-SERVER-IP:$ZER0FIT_PORT/sse  ← legacy fallback"
echo "  Health:      http://YOUR-SERVER-IP:$ZER0FIT_PORT/health"
echo "  Preload:     http://YOUR-SERVER-IP:$ZER0FIT_PORT/preload (POST)"
echo ""
echo -e "${BOLD}  Health check:${NC}"
echo "  curl $HEALTH_URL"
echo "  Shows: status, state (IDLE/HOT_CACHED), active model, all endpoints"
echo ""
echo -e "${BOLD}  Next steps:${NC}"
echo "  1. Upload CSV files to: $SCRIPT_DIR/data/"
echo "  2. Connect Open WebUI to the MCP endpoint (see docs/DEPLOYMENT_GUIDE.md)"
echo "  3. Install the Zer0Fit skill from: openwebui/skill_content.md"
echo ""
echo -e "${BOLD}  Useful commands:${NC}"
echo "  $COMPOSE_CMD --profile gpu logs -f     # View logs"
echo "  $COMPOSE_CMD --profile gpu down         # Stop server"
echo "  $COMPOSE_CMD --profile gpu up -d        # Start (detached)"
echo "  curl $HEALTH_URL                         # Health check"
echo "  curl -X POST $PRELOAD_URL                # Re-download/cache model weights"
echo ""
if [[ "$FINAL_STATE" == "HOT_CACHED" ]]; then
    ok "Models are loaded in VRAM and ready for predictions."
else
    warn "Models will load on first inference call (may take ~60s)."
fi