## Why

The early `update.sh` / `update.bat` flow only overlays a complete GitHub Release archive and no longer matches the project's deployment reality: the Windows portable bundle ships the script but cannot reliably run it with its bundled Python, has no commit channel, performs no compatibility or rollback checks, and gives the React UI no version or update state. Large portable users therefore need a safe, self-contained way to receive code-only hotfixes without repeatedly downloading multi-gigabyte runtimes.

## What Changes

- Add a localized Update Center to React Settings that shows the installed release plus commit revision, checks updates on demand, offers **Stable** (latest published release) and **Latest** (current `main` commit) channels, explains channel risk, and applies or rolls back an update with visible progress across the server restart.
- Add owner-only update APIs and a backend update service that expose sanitized version/capability state, resolve trusted GitHub targets, reject active-task or locally modified installations, run updates outside the serving process, verify the result, restart the service, and automatically restore the previous revision after a failed verification.
- Replace the legacy full-ZIP overlay implementation in `tools/update.py` while keeping `update.sh` / `update.bat` as supported command-line entry points and retaining backward-compatible check/pre-release arguments where practical.
- Make every newly built Windows portable package update-capable without system prerequisites by bundling a pinned, checksum-verified official MinGit runtime and a managed shallow Sharp GUI worktree. Record the source commit, release base, runtime compatibility revision, package target, and bundled Git version in package metadata.
- Introduce a tracked update compatibility manifest. Code-only updates are allowed only when the target supports the installed portable runtime revision and contains a built React frontend; incompatible Python/CUDA/video-reconstruction runtime changes require a new complete portable package instead of attempting an unsafe partial environment mutation.
- Preserve workspace data, configuration, model caches, Python/CUDA environments, video-reconstruction environments, and package-local tools during commit updates; add integration coverage proving tracked code changes while ignored/untracked user and runtime data survive.
- Update bilingual user documentation and release/portable packaging guidance to describe the bootstrap-version boundary, channel semantics, bundled Git, compatibility gate, rollback behavior, and CLI equivalents.

Scope includes manual version checking and one-click owner-triggered updates for the React application, source/release installations with Git available, and self-contained Windows portable packages built after this change. Scope excludes unattended background installation, mutation of the Legacy frontend, automatic cross-revision replacement of large Python/CUDA/video runtimes, and moving the existing multi-gigabyte portable ZIPs onto GitHub Release storage.

## Capabilities

### New Capabilities

- `application-self-update`: Defines commit-aware version reporting, stable/latest update channels, owner-only check/apply/rollback workflows, compatibility gates, progress/restart behavior, failure recovery, data preservation, and CLI parity.

### Modified Capabilities

- `windows-portable-release-packages`: Requires portable packages to include a verified non-interactive Git runtime, managed source revision metadata, and a clean update baseline that can receive compatible commit updates without system Git or Python.

## Impact

- Backend: new update route/service modules under `backend/routes/` and `backend/services/`, route registration, centralized access-control classification, server lifecycle coordination, and pytest coverage under `tests/`.
- Frontend: a new Settings child component under `frontend/src/components/layout/`, new `frontend/src/api/` and `frontend/src/types/` contracts, reusable icons/dialogs, Settings integration, CSS Modules, and synchronized `en.json` / `zh.json` text.
- Updater and metadata: `tools/update.py`, `update.bat`, `update.sh`, a root compatibility manifest, and project-root update state/tool directories covered by `.gitignore` and architecture documentation.
- Packaging/release: `tools/build_portable_package.ps1`, `tools/build_portable_release.ps1`, portable package metadata/notes, GitHub Release packaging inputs, and clean-room portable validation.
- Documentation/specification: `README.md`, `README.en.md`, Agent runtime-directory guidance, and the existing Windows portable release specification.
