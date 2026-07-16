## 1. Update foundation and version model

- [x] 1.1 Add the tracked update compatibility manifest and project-root ignored update/tool state directories with documented lifecycle boundaries.
- [x] 1.2 Implement pure version, deployment, Git executable, managed-worktree, manifest compatibility, and sanitized persisted-state helpers in a dedicated backend service.
- [x] 1.3 Implement trusted Stable/Latest target resolution from canonical Git refs with commit-aware labels and exact target validation.
- [x] 1.4 Add focused pytest coverage for version parsing, deployment detection, channel resolution, check failures, manifest compatibility, dirty state, and response sanitization.

## 2. Transactional updater and CLI

- [x] 2.1 Replace `tools/update.py` with the shared safe check/apply CLI and external helper while retaining `--check`.
- [x] 2.2 Implement the external update transaction: exclusive lock, active/dirty/stale checks, exact fetch/checkout, persisted phases, health verification, automatic commit rollback, and restart handoff.
- [x] 2.3 Update `update.bat` and `update.sh` to select package-local/venv/system Python correctly, propagate exit codes, and document Stable/Latest CLI usage.
- [x] 2.4 Add a temporary-local-remote integration test proving exact additions/modifications/deletions/renames, user/runtime marker preservation, incompatibility refusal, and automatic failure recovery.

## 3. Backend API and security integration

- [x] 3.1 Add a side-effect-free update manager to app creation and expose sanitized status plus owner-only check/apply routes.
- [x] 3.2 Register the update routes and explicitly classify read versus mutation paths in the centralized access-control matrix with route-level owner defense.
- [x] 3.3 Reject mutation for active generation tasks, concurrent operations, non-default developer branches, dirty tracked files, or expired/untrusted checked targets using stable error codes.
- [x] 3.4 Extend route-map, API-contract, import-side-effect, localhost/remote, forwarding-header, and mutation-no-side-effect pytest coverage.

## 4. React Update Center

- [x] 4.1 Add typed update API contracts and client functions for status, Stable/Latest checks, apply, and reconnect-safe polling.
- [x] 4.2 Build the three-file `UpdateSettingsSection` component with commit-aware version rows, channel selection, compatibility/risk states, confirmation, progress, retry, and owner-disabled behavior.
- [x] 4.3 Integrate the update section as the final Settings content block without coupling it to Settings save or the global loading/store state.
- [x] 4.4 Add synchronized English/Chinese `update*` resources for all labels, stages, confirmations, compatibility reasons, and stable backend error codes.
- [x] 4.5 Verify responsive light/dark, keyboard/focus, reduced-motion, and expected server-disconnect behavior through frontend lint/build and browser smoke testing.
- [x] 4.6 Replace generic update-unavailable messaging with a localized, accessible blocker list that names the current branch, selected channel, missing manifest, and recovery actions.

## 5. Self-contained Windows portable packaging

- [x] 5.1 Add pinned official x64 MinGit acquisition, SHA256 verification, reusable cache, complete license preservation, and plan output to the portable builder.
- [x] 5.2 Seed each package with a clean shallow managed Sharp GUI worktree at the exact source revision and a package-local exclude configuration that preserves all runtime/user paths.
- [x] 5.3 Extend `portable-package.json`, package notes, release template, and build validation with source/runtime/update/Git provenance and compatibility information.
- [x] 5.4 Add packaging/integration checks that use bundled Python and MinGit with system tools hidden and verify a compatible code update plus an incompatible-runtime refusal.

## 6. Documentation and project guidance

- [x] 6.1 Update `README.md` and `README.en.md` with current-version UI, Stable/Latest semantics, CLI commands, bootstrap boundary, automatic failure recovery, preservation guarantees, and full-package-required cases.
- [x] 6.2 Update Agent project/backend/testing guidance for update state/tool directories, owner-only endpoints, runtime revision discipline, MinGit licensing, and the portable self-update smoke matrix.
- [x] 6.3 Add bundled MinGit third-party provenance/source/license notice guidance without removing the existing Sharp model license boundary.
- [x] 6.4 Keep the bilingual README user-oriented and consolidate manifest, blocker, transaction, CI, packaging, testing, and release details in a dedicated Chinese developer rule.

## 7. End-to-end verification

- [x] 7.1 Run all backend pytest suites and targeted updater integration tests; fix every regression.
- [x] 7.2 Run frontend lint, TypeScript/Vite production build, i18n key parity checks, and confirm committed `frontend/dist` matches the new UI.
- [x] 7.3 Run strict OpenSpec validation, portable release `-PlanOnly`, MinGit checksum/version/license checks, and ZIP/staging integrity checks proportional to the package build.
- [x] 7.4 Perform a clean extracted Windows portable smoke test with system Git/Python excluded, verify app/API startup and user markers after update/failure recovery, and run the existing video-runtime command gate when the enhanced bundle is exercised.
- [x] 7.5 Add and test a pull-request CI guard that requires a `portableRuntimeRevision` increase only for runtime-sensitive dependency, installer, or portable-builder changes.

## 8. Lean v1 scope refinement

- [x] 8.1 Revise proposal, design, and application spec to retain safe one-click updates while dropping generic Release snapshot bootstrap, GitHub REST/cache metadata, client target tokens, manual rollback, and legacy CLI compatibility.
- [x] 8.2 Resolve Stable/Latest exclusively through canonical Git refs, persist only recent checked candidates, and keep exact-SHA manifest/frontend compatibility verification.
- [x] 8.3 Remove manual rollback and legacy Release bootstrap from backend routes, manager, transaction helper, CLI, access-control classification, and typed API contracts while preserving automatic failure rollback and interrupted-operation reconciliation.
- [x] 8.4 Replace the oversized Update Center with a compact localized current/target/channel/blocker/apply/progress component that still survives the expected restart disconnect.
- [x] 8.5 Consolidate portable build update helpers and duplicate recovery tests without weakening MinGit provenance, managed-worktree isolation, runtime revision CI, or transaction coverage.
- [x] 8.6 Align bilingual README, developer rules, package notes, and generated frontend assets with the lean scope and removal of manual rollback.
- [x] 8.7 Run targeted/full pytest, frontend lint/build, i18n parity, strict OpenSpec validation, compatibility guard tests, portable `-PlanOnly`, and final diff/line-count review.
