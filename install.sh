#!/usr/bin/env bash
# ============================================================================
# Zer0Fit MCP — Interactive Installer
# ============================================================================
# Detects the host architecture and GPU type, configures the Docker build
# with the correct CUDA base image and PyTorch wheel index, then builds
# and launches the Zer0Fit container.
#
# Usage:
#   ./install.sh              # interactive (prompts for ZER0FIT_SSE_URL)
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

# ── Configuration prompts ─────────────────────────────────────────────────
INTERACTIVE=true
if [[ "${1:-}" == "--non-interactive" ]]; then
    INTERACTIVE=false
fi

# Default values
ZER0FIT_VRAM_TTL="${ZER0FIT_VRAM_TTL:-300}"
ZER0FIT_PORT="${ZER0FIT_PORT:-8002}"
ZER0FIT_UPLOAD_TTL_HOURS="${ZER0FIT_UPLOAD_TTL_HOURS:-6}"
TABFM_REF="${TABFM_REF:-d8678b6895f1428a468d4cc299c1ff4cf704e726}"

if $INTERACTIVE; then
    echo ""
    echo -e "${BOLD}Configuration:${NC}"
    echo "  VRAM TTL (seconds): $ZER0FIT_VRAM_TTL"
    echo "  Port:               $ZER0FIT_PORT"
    echo "  TabFM git ref:      $TABFM_REF"
    echo ""

    read -rp "Press ENTER to accept defaults, or enter new values: " user_input
    if [ -n "$user_input" ]; then
        # Parse simple "key=value" inputs
        for pair in $user_input; do
            case "$pair" in
                ttl=*)    ZER0FIT_VRAM_TTL="${pair#ttl=}" ;;
                port=*)   ZER0FIT_PORT="${pair#port=}" ;;
                ref=*)    TABFM_REF="${pair#ref=}" ;;
            esac
        done
    fi
fi

info "Configuration:"
info "  Architecture:    $ARCH_LABEL"
info "  Base image:      $BASE_IMAGE"
info "  VRAM TTL:        ${ZER0FIT_VRAM_TTL}s"
info "  Port:            $ZER0FIT_PORT"
info "  TabFM git ref:   $TABFM_REF"

# ── Write .env file ────────────────────────────────────────────────────────
ENV_FILE="$SCRIPT_DIR/.env"
cat > "$ENV_FILE" << EOF
# Zer0Fit configuration — auto-generated by install.sh
# Architecture: $ARCH_LABEL
# Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")

BUILDARCH=$BUILDARCH
BASE_IMAGE=$BASE_IMAGE
TORCH_INDEX=$TORCH_INDEX
ZER0FIT_VRAM_TTL=$ZER0FIT_VRAM_TTL
ZER0FIT_PORT=$ZER0FIT_PORT
ZER0FIT_UPLOAD_TTL_HOURS=$ZER0FIT_UPLOAD_TTL_HOURS
TABFM_REF=$TABFM_REF
EOF
ok ".env file written to $ENV_FILE"

# ── Create data directory if it doesn't exist ─────────────────────────────
mkdir -p "$SCRIPT_DIR/data"
ok "Data directory ready: $SCRIPT_DIR/data/"

# ── Summary before build ──────────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD} Ready to build. The Docker image will include:${NC}"
echo -e "  • CUDA base image: $BASE_IMAGE"
echo -e "  • PyTorch (pre-built, $ARCH_LABEL)"
echo -e "  • TimesFM 2.5 (200M params, auto-downloads on first use)"
echo -e "  • TabFM v1.0.0 (auto-downloads on first use)"
echo -e "  • MCP SSE server on port $ZER0FIT_PORT"
echo ""
echo -e " First build takes 5-10 minutes (downloading torch + deps)."
echo -e " Model weights download on first inference call (~60s each)."
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

# ── Verify ────────────────────────────────────────────────────────────────
echo ""
info "Verifying deployment..."
sleep 5

HEALTH_URL="http://127.0.0.1:$ZER0FIT_PORT/health"
if curl -sf "$HEALTH_URL" &>/dev/null; then
    HEALTH=$(curl -s "$HEALTH_URL")
    ok "Zer0Fit is live: $HEALTH"
    ok "Health endpoint: $HEALTH_URL"
    ok "SSE endpoint:    http://127.0.0.1:$ZER0FIT_PORT/sse"
    echo ""
    echo -e "${GREEN}${BOLD}  ══════════════════════════════════════════════${NC}"
    echo -e "${GREEN}${BOLD}  Zer0Fit MCP server deployed successfully!${NC}"
    echo -e "${GREEN}${BOLD}  ══════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${BOLD}  Next steps:${NC}"
    echo "  1. Upload CSV files to: $SCRIPT_DIR/data/"
    echo "  2. Connect Open WebUI to the SSE endpoint (see docs/DEPLOYMENT_GUIDE.md)"
    echo "  3. Or install the Open WebUI tool from: openwebui/"
    echo ""
    echo -e "${BOLD}  Useful commands:${NC}"
    echo "  $COMPOSE_CMD --profile gpu logs -f     # View logs"
    echo "  $COMPOSE_CMD --profile gpu down         # Stop server"
    echo "  $COMPOSE_CMD --profile gpu up -d        # Start (detached)"
    echo "  curl $HEALTH_URL                         # Health check"
else
    warn "Server did not respond at $HEALTH_URL"
    warn "Check logs: $COMPOSE_CMD --profile gpu logs"
    warn "The container may need more time to start — wait 30s and retry."
fi