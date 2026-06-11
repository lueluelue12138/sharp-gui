# syntax=docker/dockerfile:1.7

ARG RUNTIME_BASE=python:3.12-slim-bookworm
ARG NODE_BASE=node:20-bookworm-slim

FROM ${NODE_BASE} AS frontend-builder

WORKDIR /src/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM ${RUNTIME_BASE} AS runtime

ARG TARGET_VARIANT=cpu
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG ML_SHARP_REF=1eaa046834b81852261262b41b0919f5c1efdd2e
ARG ML_SHARP_ARCHIVE_URL=

LABEL org.opencontainers.image.title="Sharp GUI"
LABEL org.opencontainers.image.description="Browser UI for Apple ml-sharp 3D Gaussian Splatting inference"
LABEL org.opencontainers.image.source="https://github.com/lueluelue12138/sharp-gui"
LABEL org.opencontainers.image.licenses="MIT"

ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1
ENV PYTHONUTF8=1
ENV PYTHONIOENCODING=utf-8
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV SHARP_FRONTEND_MODE=react
ENV SHARP_BIND_HOST=0.0.0.0
ENV SHARP_DATA_DIR=/data
ENV SHARP_DOCKER_VARIANT=${TARGET_VARIANT}
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility

WORKDIR /app

RUN set -eux; \
    apt-get -o Acquire::Retries=5 update; \
    packages="ca-certificates libgl1 libglib2.0-0"; \
    if ! command -v python >/dev/null 2>&1; then \
        packages="${packages} build-essential python3 python3-dev python3-venv"; \
    fi; \
    apt-get install -y --no-install-recommends ${packages}; \
    rm -rf /var/lib/apt/lists/*; \
    if ! command -v python >/dev/null 2>&1; then ln -s "$(command -v python3)" /usr/local/bin/python; fi; \
    python -m venv "${VIRTUAL_ENV}"; \
    python -m pip install --upgrade pip setuptools wheel

RUN python - <<'PY'
import os
import shutil
import tarfile
import tempfile
import urllib.request

ref = os.environ["ML_SHARP_REF"]
archive_url = os.environ.get("ML_SHARP_ARCHIVE_URL") or (
    f"https://github.com/apple/ml-sharp/archive/{ref}.tar.gz"
)

with tempfile.TemporaryDirectory() as tmp_dir:
    archive_path = os.path.join(tmp_dir, "ml-sharp.tar.gz")
    print(f"Downloading ml-sharp from {archive_url}")
    urllib.request.urlretrieve(archive_url, archive_path)

    with tarfile.open(archive_path, "r:gz") as tar_file:
        tar_file.extractall(tmp_dir)

    extracted_dirs = [
        os.path.join(tmp_dir, name)
        for name in os.listdir(tmp_dir)
        if os.path.isdir(os.path.join(tmp_dir, name))
    ]
    if len(extracted_dirs) != 1:
        raise RuntimeError(f"Expected one extracted ml-sharp directory, got: {extracted_dirs}")

    shutil.move(extracted_dirs[0], "/opt/ml-sharp")
PY

WORKDIR /opt/ml-sharp

RUN python -m pip install --no-cache-dir \
        "torch==2.8.0" \
        "torchvision==0.23.0" \
        --index-url "${TORCH_INDEX_URL}" \
    && awk ' \
        /^-e[[:space:]]+\.$/ { next } \
        /^torch==/ { next } \
        /^torchvision==/ { next } \
        /^nvidia-/ { next } \
        /^triton==/ { next } \
        { print } \
    ' requirements.txt > /tmp/ml-sharp-runtime-requirements.txt \
    && python -m pip install --no-cache-dir -r /tmp/ml-sharp-runtime-requirements.txt \
    && python -m pip install --no-cache-dir --no-deps -e . \
    && python -m pip install --no-cache-dir flask \
    && python -m pip cache purge

WORKDIR /app

COPY app.py ./
COPY backend/ ./backend/
COPY tools/ ./tools/
COPY templates/ ./templates/
COPY static/ ./static/
COPY --from=frontend-builder /src/frontend/dist ./frontend/dist
COPY docker/entrypoint.sh /usr/local/bin/sharp-gui-entrypoint

RUN mkdir -p /data /app/inputs /app/outputs \
    && chmod +x /usr/local/bin/sharp-gui-entrypoint

EXPOSE 5050

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5050/', timeout=3).read(1)" || exit 1

ENTRYPOINT ["sharp-gui-entrypoint"]
CMD ["python", "/app/app.py"]
