## Context

Sharp GUI currently has three materially different installations: a developer/source Git clone, a generic GitHub Release snapshot that later creates `venv/`, and multi-gigabyte Windows portable bundles with package-local Python/CUDA/model/video runtimes. The 2026-07-16 audit found that all three v1.3.0 portable variants contain `update.bat` and `tools/update.py`, but contain neither `venv\Scripts\python.exe`, system-independent Git, nor `version.txt`; consequently the shipped entry point cannot use `python\python.exe`, reports an unknown version when forced, and overlays the small generic Release archive onto an unchanged portable runtime. The overlay is non-transactional, leaves deleted files behind, disables TLS validation on fallback, has no integrity/compatibility check, and cannot reach `main` (currently `v1.3.0 + 17 commits`).

The desired model is the proven “large fixed runtime plus small managed source updates” pattern: stable resolves to a formal release tag, latest resolves to the default-branch head, and the installed identity combines the most recent release tag with the commit distance and abbreviated SHA. Git for Windows explicitly positions MinGit as the non-interactive distribution for third-party applications; the selected x64 artifact is small relative to the portable bundles and already contains its license inventory.

Constraints include a tracked `frontend/dist` because portable users do not have Node, project-root user/runtime directories that must never be reset, owner-only mutation over the LAN security boundary, Flask import paths that must not start networking or worker threads, and Windows file/process behavior that requires update work to continue outside the serving process.

## Goals / Non-Goals

**Goals:**

- Give every installation a structured, localized current-version identity and give the React Settings UI an understandable stable/latest Update Center.
- Make compatible Windows portable hotfixes independent of system Python and Git while preserving all large runtime and user data directories.
- Apply exact Git revisions so additions, modifications, deletions, and renames converge to the target commit.
- Refuse incompatible runtime transitions, active generation tasks, concurrent operations, untrusted targets, and dirty managed files before mutation.
- Persist progress across the expected server outage, verify the new revision, restart automatically, and roll back to the previous commit after a failed verification.
- Keep `update.bat` / `update.sh` useful as CLI equivalents and retain the next full portable package as the bootstrap/fallback path.

**Non-Goals:**

- Silently install updates in the background or update without an owner confirmation.
- Patch PyTorch, CUDA, the embedded Python runtime, the model cache, COLMAP, ffmpeg, or `.video-reconstruction-env` across a runtime compatibility revision.
- Guarantee arbitrary historical packages can self-bootstrap; packages produced before this feature require one final full-package download.
- Update the Legacy frontend or provide an update UI outside React Settings.
- Preserve arbitrary edits to tracked application source automatically; source developers retain normal Git workflows.
- Replace external hosting for the multi-gigabyte Windows portable archives.

## Decisions

### 1. Use a two-part version identity and a tracked compatibility manifest

`version.txt` remains the formal release baseline. Runtime status adds the exact installed Git SHA, nearest compatible release tag, number of commits ahead, channel, installation kind, and dirty/capability flags. Stable displays `vX.Y.Z`; latest displays `vX.Y.Z + N commits (abcdefg)`. A tracked root manifest declares schema version, portable runtime revision, update protocol revision, expected default branch, minimum Git version, supported package targets, and the requirement for built `frontend/dist` assets.

**Why:** a release number alone cannot describe post-release hotfix commits, while a SHA alone is unfriendly. An explicit runtime revision makes the environment boundary testable instead of assuming every source commit works with every old CUDA/Python bundle.

**Alternatives considered:** rewriting `version.txt` to a synthetic version would mix release and working-revision semantics and be overwritten by checkout; inferring compatibility only from changed filenames would be brittle and could miss transitive dependency changes.

### 2. Define stable/latest entirely from canonical Git refs

Stable resolves the highest canonical tag matching the formal release contract `vX.Y.Z`; prerelease-shaped tags are excluded. Latest resolves `refs/heads/main`. The updater fetches only the canonical repository's trusted refspecs, pins the resulting exact SHA, reads `update-manifest.json` and `frontend/dist` from that commit, and stores the checked candidate by channel. Apply accepts only a recently stored channel candidate and re-resolves the same ref before mutation; it never accepts a client-supplied URL, repository, ref, tag, SHA, or command.

**Why:** both supported installation types already require Git, and portable packages bundle MinGit. Reusing Git removes the separate GitHub REST client, ETag/body cache, rate-limit model, raw-content fetches, compare API, and short-lived client token without weakening exact-SHA trust.

**Alternatives considered:** GitHub REST provides richer metadata but duplicates transport and cache behavior that the product does not need. Formal release publication remains responsible for creating only final `vX.Y.Z` tags; if that release discipline changes, a dedicated stable ref can be introduced later.

### 3. Manage only application code with Git; keep runtimes and user data untracked

New Windows portable packages contain a real shallow Sharp GUI worktree at the package root and an official pinned MinGit under `.sharp-gui-tools/git`. The builder seeds the worktree at the exact source revision, pins canonical origin, configures a package-local exclude list, writes source/runtime/tool metadata to `portable-package.json`, and verifies a clean tracked baseline. Package-local Python, model cache, `ml-sharp`, optional reconstruction environment, updater state/tools, configuration, certificates, logs, and every workspace directory remain ignored or untracked and therefore survive checkout/reset.

**Why:** Git provides exact deletion/rename semantics, ancestry checks, compact incremental transfer, and commit rollback. Keeping the current flat package layout avoids a disruptive `app/` relocation while still separating managed and unmanaged paths through the index.

**Alternatives considered:** full Release ZIP overlays cannot remove stale files or provide cheap commit updates; custom binary patches add a new publishing system; relocating all code under `app/` would improve physical separation but would break paths and greatly expand this change.

### 4. Bundle standard x64 MinGit and preserve its complete license inventory

The portable builder downloads a pinned official standard x64 MinGit asset, verifies its fixed SHA256 before extraction, caches it for repeat builds, copies the full distribution (including `LICENSE.txt` and component licenses), and records version/hash/source in package metadata and third-party documentation. Update commands call its absolute `cmd\git.exe` with non-interactive environment settings and never modify global PATH/configuration. The current pin is Git for Windows `v2.55.0.windows.3`, asset `MinGit-2.55.0.3-64-bit.zip`, SHA256 `f48e2d2dc74a24454adc6d8fd0ac25bf9c2386f19cfb06202b9465aaad4f9f05`.

**Why:** MinGit is designed for embedded non-interactive Git and its roughly 37 MiB compressed cost is negligible next to a 6–11 GiB package. A fixed digest makes builds reproducible and prevents an updater tool substitution.

**Alternatives considered:** system Git contradicts portable self-containment; bundled `pygit2` is smaller but introduces a native Python dependency/backend lifecycle to maintain; BusyBox MinGit remains an experimental variant.

### 5. Separate checking from a transactional external apply helper

The Flask service owns sanitized status, checked candidates, locking, preconditions, and spawning. Apply launches `tools/update.py` with a fixed persisted operation identifier, then schedules the normal server supervisor to stop/restart. The already-loaded helper waits for the serving process boundary, records the previous commit, re-fetches the exact trusted target, re-checks manifest compatibility, resets tracked code, performs health checks, and atomically writes phase/status. A failed checkout or verification resets to the previous commit, verifies the rollback, records a stable error code, and restarts the old version. A successful update starts the updated server; the previous commit is retained only for transaction recovery and automatic failure rollback, not as a separate manual product workflow.

**Why:** the server must not replace code beneath active request threads, and the browser needs a durable status after disconnect/restart. Git commit rollback is smaller and more reliable than copying the entire portable directory.

**Alternatives considered:** updating inside the Flask process risks partial imports and locked files; downloading a second full portable tree doubles disk use; relying only on manual restart leaves users uncertain whether the operation finished.

The restart health probe reads `GET /api/updates/status` over loopback. Because that route is Unlocked, an installation that enables the access code *and* disables `allow_localhost_bypass` answers the probe with a structured auth error, which would otherwise be misread as a dead service and roll back a verified update. That configuration is currently unreachable through the UI and also removes owner status entirely, so no apply can start and the misread cannot happen today; the probe is hardened anyway because the same configuration is already documented as the supported way to force the access code behind a reverse proxy, and any future owner-definition or settings change would make the path live. A `401`/`403` carrying `AUTH_REQUIRED`, `ACCESS_SETUP_REQUIRED`, or `OWNER_REQUIRED` still proves the updated Flask application imported, registered routes, and is serving, so it counts as healthy; any other status, body, or unparsable payload keeps waiting. Two deliberate exceptions are recorded here rather than hidden in code: the probe uses an unverified TLS context because Sharp GUI normally serves a self-signed local certificate, and its trust comes from the exact commit the helper itself just checked out; and a foreign process squatting the port can at most delay the probe, because a non-matching commit or unrecognized body never counts as healthy.

Reconciliation of an interrupted operation runs inside a status request, so it uses a shallow verification that only checks HEAD, required files, the frontend entrypoint, manifest compatibility, and a clean worktree. Bytecode compilation and the import subprocess stay exclusively in the updater helper. Otherwise a read-only endpoint reachable by any Unlocked client could trigger a full `compileall` plus interpreter spawn, and it would do so exactly during the restart window when both the browser and the probe are polling.

Stopping the serving process for an update uses `os._exit`, which skips `atexit` and the `run_server` cleanup block. The updated instance can still acquire the workspace lock only because `WorkspaceInstanceLock` uses an OS advisory lock that the kernel releases on process death. This is a load-bearing assumption: replacing it with a PID or marker file lock would break every self-update restart.

### 6. Use a project-root update state directory and a dedicated manager

`.sharp-gui-update/` is installation-level state, not workspace data. It contains atomic `state.json`, the latest checked candidate for each channel, an operation lock, and bounded diagnostic output without secrets, arbitrary commands, or absolute paths in API responses. A dedicated update manager is attached to the Flask app but its constructor only reads local state; it performs no network call and starts no thread during `create_app()` or import. Update operations remain separate from the model `TaskManager`, although apply consults that manager to reject pending/running/processing generation work.

**Why:** update state must survive both workspace switching and server replacement while maintaining the project's import-without-workers contract.

**Alternatives considered:** Zustand/localStorage cannot coordinate the stopped server or CLI; storing in the active workspace would make installation state change when the user switches model workspaces; reusing `TaskManager` mixes incompatible lifecycles.

### 7. Add explicit update API permissions and a local-state React component

`GET /api/updates/status` is Unlocked and returns only sanitized identity/capability/operation data. `POST /api/updates/check` and `POST /api/updates/apply` are explicitly Owner in the centralized matrix and re-check `g.is_owner` in routes. The Settings child component owns its view state, checks only when opened or requested, polls only during an operation, treats restart disconnects as expected, and reloads after the new instance/current SHA is observed. It uses a compact single-column glass card with current version, two channels, target result, blocker list, one confirmation, and one progress region; internal transaction details and manual rollback controls are not exposed.

**Why:** updates mutate executable code and stop the service, so remote generation permission is insufficient. Component-local state avoids expanding the already large global store for a Settings-only workflow.

**Alternatives considered:** putting updates into `/api/settings` obscures permissions and responsibilities; a global loading overlay hides the very progress/recovery information the user needs; a new Zustand store violates the project's single-store rule.

### 8. Keep CLI parity and deployment-specific capability reporting

`update.bat` first selects `python\python.exe`, then `venv\Scripts\python.exe`, then system Python; `update.sh` selects the virtual environment or system Python. Both invoke the same updater service/CLI with only `--channel stable|latest`, `--check`, and confirmation options. Portable packages prefer bundled MinGit. A clean source clone may use system Git but automatic apply is disabled on non-default branches or tracked modifications. A generic Release snapshot never creates `.git` in place; status explains that it needs a normal Git clone or a new complete package.

**Why:** one implementation prevents the UI and scripts from disagreeing, while capability reporting is more honest than pretending every legacy layout can update safely.

**Alternatives considered:** preserving the old archive updater alongside the new service would duplicate version/rollback behavior and retain its security flaws; forcing UI updates on developer branches could destroy intentional work.

## Risks / Trade-offs

- [A `main` commit changes dependencies without increasing the runtime revision] -> Require the manifest in every target, document the release discipline, verify the installed/target revision and built frontend before mutation, and block when metadata is absent or inconsistent.
- [Git reset could overwrite intentional tracked edits] -> Refuse a dirty managed worktree by default, report the exact category without exposing paths remotely, and leave source developers on manual Git workflows.
- [Updater/server is interrupted after code mutation] -> Persist each phase atomically, retain the previous commit locally, reconcile an incomplete operation on startup, verify current HEAD, and offer/perform rollback before reporting readiness.
- [The canonical Git remote is unavailable] -> Never make boot depend on the network; checks use bounded non-interactive Git commands and return an explicit error without claiming the app is current.
- [Bundled MinGit introduces size and license obligations] -> Pin and verify the standard artifact, keep its license tree intact, record source/tag/hash, add third-party notice text, and review the pin during portable releases.
- [Shallow history cannot compute ancestry or commit distance] -> Fetch the stable tag and a bounded `main` history; show the exact target SHA even when distance remains unknown, and never treat an unknown relationship as proof of safety.
- [The server stops while a generation is running] -> Reject apply whenever model tasks are active and require the owner to finish or cancel them first.
- [A successful code update cannot run on the package runtime] -> Run compile/import/frontend and package-specific smoke checks before success; automatically reset the previous commit and restart it on failure.
- [Stable is older than the currently installed latest commit] -> Present this as an explicit channel switch/downgrade in the confirmation and retain the current revision as rollback target.
- [Existing portable packages cannot gain bundled Git/UI retroactively] -> Publish the next complete bundle as the explicit bootstrap version and keep the old script assessment/documentation clear.
- [A locked installation makes the restart probe look unhealthy and rolls back a good update] -> Accept structured loopback auth refusals as proof the service is serving, and cover the route response and the probe classifier together in tests. Unreachable today because the same configuration removes owner status and blocks apply, but retained as defense in depth for the documented reverse-proxy configuration.
- [The restarted instance has no console, so a bad restart leaves no evidence] -> Send the relaunched application's output to a bounded `restart.log` under the update state directory instead of discarding it.
- [A target that tracks runtime/user state is only detected after the server stops] -> Run the protected-path scan during check as well, and keep the pre-mutation scan in the helper as defense in depth.
- [Protected-path matching is broad enough to block unrelated files] -> Match the ignored user-data families (`inputs*`, `outputs*`, `model-assets*`) only when the path has a directory component, so an ordinary tracked root file such as `outputs-format.md` cannot block every update.
- [A source install updates into a commit that needs new dependencies] -> Portable packages stay hard-blocked by the runtime revision gate; source installs receive the same signal as a non-blocking advisory, since it is the only reliable predictor of a post-update import failure.
- [Concurrent checks from the UI and the CLI race in the same repository] -> Checking takes the same installation operation lock as applying, so a second check or a running transaction is refused with the in-progress code instead of colliding on Git ref locks.
- [Only one blocker is reported while several conditions are unmet] -> Capabilities return an ordered `reason_codes` list, and the UI groups every blocker by whether it belongs to the current installation, the selected target, or the last update operation.

## Migration Plan

1. Land the compatibility manifest, backend/CLI update engine, APIs, React Update Center, tests, and documentation together; built `frontend/dist` must be committed with the source change.
2. Update the portable builder to acquire/verify MinGit, seed a clean shallow worktree at the exact package source SHA, write update metadata, preserve licenses, and test both bundled Git and dirty-state assumptions.
3. Produce the next portable release as the bootstrap package. Existing v1.3.0 and older portable users perform one normal full download; no attempt is made to mutate those historical packages in place.
4. Validate stable/latest/no-op/latest-to-stable and automatic failure rollback flows using a local Git remote, then a clean extracted Windows package with system Python/Git hidden. Verify user markers, tracked deletions, restart recovery, CUDA start, and the video-reconstruction command matrix.
5. If rollout issues occur before a user updates, withdraw/replace the bootstrap package. If an installed code update fails, the helper resets the recorded previous SHA and restarts it. If the runtime itself is suspect, users retain the documented full-package extraction fallback with their workspace/config copied or pointed at separately.

## Open Questions

- The exact first public bootstrap version is intentionally assigned by the next release process rather than hard-coded in source; documentation can render it from package metadata once released.
- Future MinGit pin updates and portable runtime revision increments remain explicit maintainer release tasks. Neither question blocks this implementation.
