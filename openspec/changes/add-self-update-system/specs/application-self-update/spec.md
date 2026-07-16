## ADDED Requirements

### Requirement: The system SHALL report a commit-aware installed version

The system SHALL expose a structured installed identity containing the formal release baseline when known, exact application commit when known, abbreviated commit, commits ahead of the baseline when known, selected channel, installation kind, and a localized-display-ready version label without exposing server filesystem paths.

#### Scenario: Installation is at a formal release
- **WHEN** the installed commit matches the current formal release tag
- **THEN** the system SHALL report the formal `vX.Y.Z` version as current
- **AND** the commits-ahead value SHALL be zero

#### Scenario: Installation is ahead of a formal release
- **WHEN** the installed commit is a descendant of `vX.Y.Z` by one or more commits
- **THEN** the system SHALL report the base version, commit distance, and abbreviated SHA
- **AND** the UI SHALL be able to render `vX.Y.Z + N commits (abcdefg)` or its localized equivalent

#### Scenario: Revision metadata is incomplete
- **WHEN** the installation predates managed update metadata or Git identity is unavailable
- **THEN** the system SHALL report a limited capability with an explicit stable reason code
- **AND** the system MUST NOT fabricate a commit distance or claim that the installation is current

### Requirement: The system SHALL provide stable and latest update channels

The system SHALL define Stable as the latest published non-prerelease GitHub Release tag and Latest as the canonical `main` branch head, and SHALL return the exact resolved target revision, user-facing version identity, relationship to the installed revision, and channel risk/availability state.

#### Scenario: Owner checks Stable
- **WHEN** the owner requests a Stable channel check
- **THEN** the system SHALL resolve the latest published formal Release tag and its commit
- **AND** draft or prerelease releases MUST NOT be selected

#### Scenario: Owner checks Latest
- **WHEN** the owner requests a Latest channel check
- **THEN** the system SHALL resolve the canonical `main` head
- **AND** it SHALL report the formal release baseline and commits-ahead count when that relationship is known

#### Scenario: Check service is unavailable or rate-limited
- **WHEN** the trusted update source cannot be reached or reports a rate limit
- **THEN** the system SHALL return a stable localized error state and any explicitly marked cached result
- **AND** it MUST NOT report that the installation is up to date solely because the check failed

### Requirement: Update mutation SHALL be restricted to the localhost owner

The system MUST explicitly classify checking, applying, switching channels, and rollback as Owner operations in the centralized access-control matrix. Read-only sanitized current update status MAY be available to Unlocked clients, but no remote session or client-controlled forwarding header may authorize executable-code mutation or restart.

#### Scenario: Local owner checks or applies an update
- **WHEN** a real localhost owner submits a valid check, apply, or rollback request
- **THEN** the system SHALL process the request subject to update preconditions

#### Scenario: Authenticated remote client attempts an update
- **WHEN** an authenticated non-local client submits check, apply, or rollback
- **THEN** the system MUST reject the request as owner-only
- **AND** it MUST NOT fetch an apply target, alter files, or stop the server

#### Scenario: Remote client spoofs forwarding headers
- **WHEN** a remote request supplies `X-Forwarded-For`, `Forwarded`, `X-Real-IP`, or equivalent localhost values
- **THEN** the system MUST NOT grant update ownership from those headers

### Requirement: The system MUST gate code updates by runtime compatibility

Every automatically applicable target MUST provide recognized update metadata declaring its update protocol, portable runtime revision, supported package targets, minimum Git capability, and built frontend requirement. The system MUST compare target metadata with the installed package before mutating tracked code.

#### Scenario: Target is compatible with installed portable runtime
- **WHEN** target metadata is recognized, the runtime revision matches, the package target is supported, the updater/Git capabilities satisfy the minimums, and built frontend assets are present
- **THEN** the system SHALL allow the owner to apply the code-only update

#### Scenario: Target requires a different portable runtime
- **WHEN** target metadata declares a runtime revision different from the installed portable package
- **THEN** the system MUST refuse code-only apply with a stable full-package-required reason
- **AND** the UI SHALL explain that a new complete portable package is required

#### Scenario: Target metadata is missing or invalid
- **WHEN** a portable installation checks a target without valid recognized compatibility metadata
- **THEN** the system MUST treat the target as incompatible
- **AND** it MUST NOT infer safety from the changed file list alone

### Requirement: Update apply SHALL be transactional and recoverable

The system SHALL apply an exact trusted Git revision outside the serving process, persist progress across restart, verify the target before reporting success, and automatically restore the previously installed commit when checkout or verification fails.

#### Scenario: Compatible update succeeds
- **WHEN** all preconditions pass and the exact trusted target is fetched, applied, and verified
- **THEN** tracked application files SHALL match the target revision, including deletions and renames
- **AND** the system SHALL record previous/current revisions, restart the service, and report completion after the new instance is reachable

#### Scenario: Verification fails after mutation
- **WHEN** target compile, import, frontend, manifest, or package health verification fails
- **THEN** the updater MUST restore the previous revision and verify the restored application
- **AND** the operation SHALL report a stable rolled-back failure rather than success

#### Scenario: Update process is interrupted
- **WHEN** the service or updater starts with an operation recorded in a non-terminal phase
- **THEN** the system SHALL reconcile the actual installed revision with the recorded previous/target revisions
- **AND** it MUST recover or offer rollback before allowing another apply

#### Scenario: Owner requests rollback
- **WHEN** a previous successful revision remains available and the owner confirms rollback
- **THEN** the system SHALL apply and verify that recorded revision using the same transactional lifecycle

### Requirement: Update preconditions MUST protect active work and local modifications

The system MUST serialize update operations and reject apply or rollback while generation tasks are active, another update owns the operation lock, the checked target is stale/untrusted, or tracked application files contain local modifications.

#### Scenario: Generation task is active
- **WHEN** any image or video generation task is pending, running, or processing
- **THEN** apply/rollback MUST be rejected with an active-task reason
- **AND** the generation task MUST NOT be interrupted by the updater

#### Scenario: Managed worktree is dirty
- **WHEN** a tracked application file differs from the installed commit
- **THEN** automatic apply/rollback MUST be rejected without resetting the modification
- **AND** the user SHALL receive a safe localized explanation

#### Scenario: Concurrent update is requested
- **WHEN** an update operation already owns the installation update lock
- **THEN** a second mutation request MUST be rejected with a conflict response

### Requirement: Code updates MUST preserve user and package runtime state

Automatic code update and rollback MUST leave project configuration, certificates, logs, workspace inputs/outputs/model assets/indexes/caches, model cache, embedded Python/CUDA dependencies, bundled Git, package metadata, and optional video-reconstruction runtime outside the managed checkout and unchanged.

#### Scenario: Portable user has workspace and runtime data
- **WHEN** a compatible update changes, deletes, and renames tracked application files
- **THEN** all untracked/ignored workspace and package runtime markers SHALL remain byte-for-byte available
- **AND** deleted tracked files SHALL not remain as stale application code

#### Scenario: Runtime change is required
- **WHEN** the requested target cannot run on the preserved embedded runtime revision
- **THEN** the system MUST stop before checkout and direct the user to a complete package

### Requirement: The Update Center SHALL provide localized, accessible progress and confirmation

React Settings SHALL present current version, installed/target channel, check time, update availability, compatibility, and operation stages using synchronized English and Chinese resources. Apply, stable downgrade, and rollback MUST require confirmation; active operations MUST expose semantic status/progress, survive expected reconnect failures, and prevent duplicate actions.

#### Scenario: User opens Settings
- **WHEN** Settings opens on an authorized device
- **THEN** the Update Center SHALL load the persisted server update status without triggering an automatic apply
- **AND** owner-only actions SHALL be hidden or clearly disabled for non-owner access

#### Scenario: Update restarts the service
- **WHEN** an accepted update enters apply or restart phases
- **THEN** the UI SHALL continue showing the last known stage during expected temporary connection failures
- **AND** it SHALL reload the application after the new server instance reports the target revision

#### Scenario: User prefers reduced motion or keyboard navigation
- **WHEN** the Update Center is used with reduced motion, keyboard focus, or a narrow touch viewport
- **THEN** controls, focus states, progress, status, and confirmations SHALL remain perceivable and operable without motion-only or hover-only meaning

### Requirement: Command-line update entry points SHALL use the same safety model

`update.sh` and `update.bat` SHALL support Stable and Latest checks/applies through the same version, compatibility, target validation, transaction, and rollback rules as the UI. The Windows entry point SHALL prefer package-local portable Python before virtual-environment or system Python.

#### Scenario: Portable user runs update.bat without system tools
- **WHEN** a new Windows portable package user runs `update.bat` on a machine without system Python or Git
- **THEN** the script SHALL use bundled Python and bundled Git
- **AND** it SHALL be able to check/apply compatible Stable or Latest targets

#### Scenario: Source developer runs the updater on a feature branch
- **WHEN** the CLI detects a non-default branch or tracked modifications in a source checkout
- **THEN** automatic mutation SHALL be disabled with guidance to use the normal Git workflow

### Requirement: Update source transport MUST remain verified and constrained

The system MUST use certificate-verified HTTPS and/or Git transport to the canonical Sharp GUI repository, MUST use exact resolved commit IDs for mutation, and MUST NOT disable TLS verification, execute client-supplied commands, or apply an unverified archive as a fallback.

#### Scenario: TLS validation fails
- **WHEN** certificate or hostname validation for update metadata or content fails
- **THEN** the system MUST fail the check/apply safely
- **AND** it MUST NOT retry with certificate verification disabled

#### Scenario: Client submits an arbitrary target
- **WHEN** an apply request contains a URL, repository, command, branch, tag, or SHA not matching the server's trusted checked target
- **THEN** the system MUST reject it before spawning the updater
