## GitHub Issue #8 Reply Draft

Yes. Docker image support has been added to the release workflow.

Images will be published to GHCR under:

```text
ghcr.io/lueluelue12138/sharp-gui
```

Available variants:

- CPU: `ghcr.io/lueluelue12138/sharp-gui:cpu`
- NVIDIA CUDA 12.8: `ghcr.io/lueluelue12138/sharp-gui:cuda12.8`
- Version-pinned tags: `vX.Y.Z-cpu` and `vX.Y.Z-cuda12.8`

Example:

```bash
docker run --rm -it \
  --name sharp-gui \
  -p 5050:5050 \
  -v sharp-gui-data:/data \
  ghcr.io/lueluelue12138/sharp-gui:cpu
```

For NVIDIA GPU:

```bash
docker run --rm -it \
  --name sharp-gui \
  --gpus all \
  -p 5050:5050 \
  -v sharp-gui-data:/data \
  ghcr.io/lueluelue12138/sharp-gui:cuda12.8
```

The CUDA image still requires a compatible host NVIDIA driver and NVIDIA Container Toolkit. The default images do not bundle the Sharp checkpoint; the first run may download it into the mounted `/data` volume, so it is reused across container upgrades.
