# syntax=docker/dockerfile:1.6
# Multi-arch build for x86_64 (CUDA 12.4) and ARM64 (CUDA 13.2 Blackwell).
ARG BASE_IMAGE=nvidia/cuda:12.4.1-base-ubuntu24.04
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    ZER0FIT_VRAM_TTL=300

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-pip python3-dev git curl build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# TabFM is not on PyPI — clone and checkout a pinned commit for reproducible
# builds, then install (no deps so it never clobbers the carefully selected
# torch wheel). We then manually install TabFM's non-torch deps.
# To update: change TABFM_REF to a newer commit SHA after verifying compatibility.
ARG TABFM_REF=d8678b6895f1428a468d4cc299c1ff4cf704e726
RUN git clone https://github.com/google-research/tabfm.git /opt/tabfm && \
    cd /opt/tabfm && git checkout ${TABFM_REF} && \
    pip3 install --no-deps -e /opt/tabfm[pytorch] && \
    pip3 install --no-cache-dir \
        "jaxtyping<0.3" "typeguard<3" flit_core scipy einops
# Remove JAX packages — they're pulled in by TabFM's transitive deps
# (chex, optax, orbax-checkpoint) but we use the PyTorch backend, not
# JAX.  JAX v0.10+ requires numpy 2.0+ (StringDType), conflicting with
# our numpy <2.0.0 pin for TimesFM compatibility.
RUN pip3 uninstall -y jax jaxlib 2>/dev/null || true

# Architecture routing matrix — the TORCH_INDEX build arg is passed by
# docker-compose from the .env file (written by install.sh).
# Falls back to architecture-based detection if TORCH_INDEX is not set.
ARG TARGETARCH
ARG TORCH_INDEX=""
RUN if [ -n "$TORCH_INDEX" ]; then \
        echo "Installing torch from $TORCH_INDEX ..." && \
        if [ "$TARGETARCH" = "arm64" ]; then \
            pip3 install --pre --no-cache-dir torch torchvision --index-url "$TORCH_INDEX" ; \
        else \
            pip3 install --no-cache-dir torch torchvision --index-url "$TORCH_INDEX" ; \
        fi ; \
    elif [ "$TARGETARCH" = "amd64" ]; then \
        echo "Installing torch for x86_64 (CUDA 12.4)..." && \
        pip3 install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu124 ; \
    elif [ "$TARGETARCH" = "arm64" ]; then \
        echo "Installing torch for ARM64 (CUDA 13.2 / cu130 wheels / Blackwell)..." && \
        pip3 install --pre --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/nightly/cu130 ; \
    else \
        echo "Fallback: CPU/default torch..." && \
        pip3 install --no-cache-dir torch torchvision ; \
    fi

# Python-level deps (now torch is already present so pip won't upgrade it).
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY model_manager.py pipelines.py server.py ./
COPY data/ ./data/
RUN mkdir -p /app/data/uploads /app/uploads /app/.cache/huggingface && \
    useradd -m -s /bin/bash zer0fit && \
    chown -R zer0fit:zer0fit /app

ENV HF_HOME=/app/.cache/huggingface
USER zer0fit

EXPOSE 8002
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8002/health || exit 1

CMD ["python3", "server.py"]