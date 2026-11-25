## MODIFIED Requirements

### Requirement: The system MUST gate code updates by runtime compatibility

Every automatically applicable target MUST provide recognized update metadata declaring its update protocol, supported portable targets, minimum Git capability, built frontend requirement, base-runtime compatibility, and any managed application dependency contract. The system MUST compare the target with the installed environment before changing application files. Different package layout or historical runtime revision numbers alone MUST NOT imply incompatibility when the target explicitly supports and verifies that installed baseline.

#### Scenario: Target is compatible with installed portable runtime
- **WHEN** target metadata is recognized, the installed base runtime is explicitly supported and satisfies required capabilities, the package target is supported, the updater/Git capabilities satisfy the minimums, and built frontend assets are present
- **THEN** the system SHALL allow the owner to request an update including any declared application dependency preparation

#### Scenario: Target requires an incompatible base runtime
- **WHEN** the installed environment is outside the target's verified base compatibility or cannot satisfy required Python or native capabilities
- **THEN** the system MUST refuse apply before code mutation with a stable base-environment or full-package-required reason
- **AND** the UI SHALL explain the actual required recovery path

#### Scenario: Target metadata is missing or invalid
- **WHEN** a portable installation checks a target without valid recognized compatibility metadata
- **THEN** the system MUST treat the target as incompatible
- **AND** it MUST NOT infer safety from the changed file list alone

#### Scenario: Target uses only the historical manifest contract
- **WHEN** an accepted historical target does not declare the newer compatibility or application dependency fields
- **THEN** the updater SHALL interpret it using the historical compatibility contract
- **AND** it MUST NOT assume undeclared cross-runtime compatibility

#### Scenario: A small dependency is missing from an otherwise supported base
- **WHEN** a compatible target declares a supported locked application dependency absent from the package
- **THEN** the updater SHALL classify it as dependency preparation rather than a complete-package requirement

### Requirement: CI SHALL guard portable runtime revision discipline

CI SHALL classify application dependencies, base-runtime inputs, and portable layout changes and require evidence appropriate to each class. Ordinary tracked application source and built-frontend changes SHALL remain eligible without a base-runtime change. Unclassified runtime-sensitive changes MUST fail safely with the triggering paths and corrective guidance.

#### Scenario: Application files are added, removed, renamed, or refactored
- **WHEN** a change only modifies tracked backend source, frontend source, or built frontend assets
- **THEN** the compatibility guard SHALL pass without requiring a portable base-runtime revision bump

#### Scenario: A managed application dependency changes
- **WHEN** a change adds, upgrades, or removes a dependency through the supported isolated application dependency contract
- **THEN** CI SHALL require an exact complete lock and relevant preparation, transition, and recovery tests
- **AND** it MUST NOT require a new complete portable package solely for that dependency change

#### Scenario: A base-runtime input changes
- **WHEN** a change affects Python, Torch/CUDA, required native tools, or another base-runtime capability
- **THEN** CI MUST require an explicit compatibility or migration declaration and corresponding validation
- **AND** unsupported existing environments MUST remain blocked with accurate upgrade instructions

#### Scenario: Only package layout or compression changes
- **WHEN** a builder change alters compression or removes verified unused content while preserving application-required base capabilities
- **THEN** CI SHALL require layout and retained-capability evidence
- **AND** it MUST NOT automatically invalidate application updates for otherwise supported older layouts

### Requirement: Update apply SHALL be transactional and recoverable

The system SHALL apply an exact trusted Git revision outside the serving process, prepare any declared application dependencies before stopping the working service or mutating application files, persist the previous and target code/dependency combinations across restart, and verify the target before reporting success. After mutation failures it SHALL restore the previously working combination.

#### Scenario: Compatible update succeeds
- **WHEN** all preconditions pass and the exact trusted target and required dependencies are prepared, applied, and verified
- **THEN** tracked application files SHALL match the target revision, including deletions and renames
- **AND** the system SHALL record the previous/current revisions and dependency selections, restart the service, and report completion only after the new instance is verified

#### Scenario: Dependency preparation fails before mutation
- **WHEN** required dependency preparation fails
- **THEN** the working application revision and its dependencies SHALL remain unchanged and usable
- **AND** the updater MUST NOT report a completed application update

#### Scenario: Verification fails after mutation
- **WHEN** target compile, import, dependency, frontend, manifest, or package health verification fails
- **THEN** the updater MUST restore the previous revision and dependency selection and verify the restored application
- **AND** the operation SHALL report a stable recovered failure rather than success

#### Scenario: Update process is interrupted
- **WHEN** the service or updater starts with an operation recorded in a non-terminal phase
- **THEN** the system SHALL reconcile actual installed code and dependency state with recorded previous/target combinations
- **AND** it MUST reconcile or recover before allowing another apply
- **AND** request-path reconciliation MUST NOT compile bytecode, install packages, or spawn an interpreter, because that work belongs to the external helper

#### Scenario: Restarted instance requires authentication
- **WHEN** the restarted service refuses the updater's loopback status probe with a structured authentication error instead of a status payload
- **THEN** the refusal SHALL count as evidence that the restarted service is running under the existing health contract
- **AND** the system MUST NOT roll back a separately verified code/dependency target solely because the probe was not authorized

#### Scenario: Target tracks protected runtime or user paths
- **WHEN** a checked target tracks configuration, certificates, logs, workspace data, model caches, embedded runtimes, package-local tools, or prepared dependency state
- **THEN** the check SHALL report the target as incompatible before any apply is offered
- **AND** the updater MUST repeat the same refusal before mutating tracked code

### Requirement: Code updates MUST preserve user and package runtime state

Automatic update and failure recovery MUST leave project configuration, certificates, logs, workspace inputs/outputs/model assets/indexes/caches, model cache, embedded Python/CUDA dependencies, bundled Git, original package metadata, and optional video-reconstruction runtime outside the managed checkout and unchanged. Separately managed application dependencies SHALL change only through the declared isolated dependency transaction and MUST NOT overwrite the base environment.

#### Scenario: Portable user has workspace and runtime data
- **WHEN** a compatible update changes, deletes, and renames tracked application files or switches isolated application dependencies
- **THEN** all existing workspace and base-runtime markers SHALL remain byte-for-byte available
- **AND** deleted tracked files SHALL not remain as stale application code

#### Scenario: Base-runtime change is required
- **WHEN** the requested target cannot run on the preserved embedded base environment
- **THEN** the system MUST stop before checkout and direct the user to the required environment migration or complete package

### Requirement: The Update Center SHALL provide localized, accessible progress and confirmation

React Settings SHALL present current version, installed/target channel, check time, update availability, compatibility, application dependency readiness, and operation stages using synchronized English and Chinese resources. Apply and stable downgrade MUST require confirmation; active operations MUST expose semantic status/progress, survive expected reconnect failures, and prevent duplicate actions.

#### Scenario: User opens Settings
- **WHEN** Settings opens on an authorized device
- **THEN** the Update Center SHALL load persisted server update status without triggering automatic apply, dependency downloads, or installation
- **AND** owner-only actions SHALL be hidden or clearly disabled for non-owner access

#### Scenario: Update prepares dependencies and restarts the service
- **WHEN** an accepted update enters preparation, apply, or restart phases
- **THEN** the UI SHALL show the corresponding phase and retain the last known stage during expected temporary connection failures
- **AND** it SHALL reload after the new server instance and verified target combination are confirmed

#### Scenario: User prefers reduced motion or keyboard navigation
- **WHEN** the Update Center is used with reduced motion, keyboard focus, or a narrow touch viewport
- **THEN** controls, focus states, progress, status, and confirmations SHALL remain perceivable and operable without motion-only or hover-only meaning

#### Scenario: Multiple conditions block an update
- **WHEN** the current installation and the selected target each have an unmet update condition
- **THEN** the UI SHALL list every blocker separately and identify whether it belongs to the current installation, target, or check operation
- **AND** the status response SHALL expose every unmet installation condition as an ordered list rather than only the primary one
- **AND** developer-branch and missing-manifest blockers SHALL name the current/default branch, selected channel, required `update-manifest.json` file, and an actionable recovery path without exposing server filesystem paths

#### Scenario: Source installation requires a managed application dependency
- **WHEN** a supported source installation requests a target with a valid managed application dependency contract
- **THEN** applying the update SHALL prepare and verify those dependencies under the same transaction rules as portable installations
- **AND** it MUST NOT rely solely on a post-failure instruction to rerun the installer

#### Scenario: Source target requires a different base environment
- **WHEN** a source target declares incompatible base requirements outside managed application dependencies
- **THEN** the system SHALL explain the source-environment preparation needed before apply
- **AND** it MUST NOT present missing base requirements as a successfully prepared application dependency set

#### Scenario: A legacy updater requires the lightweight migration tool
- **WHEN** a supported installed updater cannot perform the required protocol or compatibility transition
- **THEN** the available migration UI or tool SHALL distinguish this case from an incompatible base environment
- **AND** it SHALL provide the canonical lightweight migration instructions without promising that an unmodified old UI understands new metadata

### Requirement: Command-line update entry points SHALL use the same safety model

`update.sh` and `update.bat` SHALL support Stable and Latest checks/applies through the same version, compatibility, dependency preparation, target validation, transaction, and automatic failure recovery rules as the UI. The Windows entry point SHALL prefer package-local portable Python before virtual-environment or system Python.

#### Scenario: Portable user runs update.bat without system tools
- **WHEN** a supported Windows portable package user runs `update.bat` on a machine without system Python or Git
- **THEN** the script SHALL use bundled Python and bundled Git
- **AND** a capable updater SHALL check/apply compatible Stable or Latest targets including locked application dependencies

#### Scenario: Source developer runs the updater on a feature branch
- **WHEN** the CLI detects a non-default branch or tracked modifications in a source checkout
- **THEN** automatic mutation SHALL be disabled with guidance to use the normal Git workflow

## ADDED Requirements

### Requirement: Releases MUST demonstrate continued update reachability

A release claiming the repaired update capability SHALL include verification of supported legacy bootstrap and at least two subsequent application update transitions with changed dependency sets, stable downgrade, and failure recovery. Future changes to the update protocol or supported base environment MUST declare how currently supported clients reach the replacement mechanism, and MUST NOT rely solely on logic that those clients cannot obtain.

#### Scenario: A repaired release is prepared
- **WHEN** maintainers propose a release that advertises lightweight dependency updates
- **THEN** release checks SHALL require recorded supported-old-package bootstrap, version A to B updates with dependency changes, downgrade, and recovery outcomes
- **AND** evidence MUST distinguish actual package validation from synthetic transaction tests

#### Scenario: A future target needs a new updater capability
- **WHEN** a future release changes the updater protocol beyond a currently supported client's capabilities
- **THEN** release preparation MUST provide and verify a reachable persistent migration tool or another explicit supported transition
- **AND** an inaccessible new updater implementation alone MUST NOT satisfy the release gate
