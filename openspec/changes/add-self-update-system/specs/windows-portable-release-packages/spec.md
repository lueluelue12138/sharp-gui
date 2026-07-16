## ADDED Requirements

### Requirement: Windows portable packages MUST include a self-contained code update baseline

Every Windows portable package produced after the self-update bootstrap release MUST contain a verified non-interactive Git runtime, an exact managed Sharp GUI source revision, and sufficient package metadata to check, apply, verify, and roll back compatible code updates without system Python, system Git, Node, npm, or a complete package redownload.

#### Scenario: Maintainer builds a portable package
- **WHEN** the Windows portable builder prepares a package staging tree
- **THEN** it MUST acquire a pinned official standard x64 MinGit artifact and verify its configured SHA256 before extraction
- **AND** the package MUST preserve the distribution's included license and notice files

#### Scenario: Package records update provenance
- **WHEN** portable package metadata is written
- **THEN** it SHALL include the exact Sharp GUI source commit, formal release baseline, canonical repository, package target, portable runtime revision, update protocol revision, bundled Git version, bundled Git digest, and relative executable location
- **AND** it MUST NOT contain maintainer credentials or machine-specific absolute paths

#### Scenario: Package seeds managed source
- **WHEN** the package staging tree is finalized
- **THEN** tracked application files and the Git index SHALL match the recorded source commit cleanly
- **AND** package runtime/user paths SHALL remain ignored or untracked so future checkout cannot delete them

#### Scenario: Portable update tools are invoked
- **WHEN** the UI or `update.bat` checks or applies an update
- **THEN** the package SHALL call its own embedded Python and MinGit by package-relative location
- **AND** the operation MUST NOT depend on similarly named executables on the user's PATH

### Requirement: Portable package validation MUST cover self-update isolation

The Windows portable build verification SHALL prove that the bundled updater is executable without system Git/Python, that the managed baseline is clean, and that a compatible commit update preserves package/runtime/workspace state while converging tracked files exactly.

#### Scenario: Package plan is inspected
- **WHEN** the maintainer runs the one-click portable release plan
- **THEN** the plan SHALL report the configured MinGit version, source asset, expected SHA256, source commit, and runtime compatibility revision for every non-skipped target

#### Scenario: Clean extracted package checks update tools
- **WHEN** a package is extracted into a clean test directory with system Git and Python excluded from PATH
- **THEN** bundled Git SHALL report the pinned version and the update CLI SHALL report the package's current version/revision
- **AND** the managed tracked worktree SHALL be clean before update

#### Scenario: Compatible test commit is applied
- **WHEN** verification applies a compatible target containing tracked additions, modifications, deletions, and renames
- **THEN** the resulting managed files SHALL exactly match the target commit
- **AND** markers in config, workspace data, model/runtime caches, embedded Python, optional reconstruction environment, package metadata, and bundled Git SHALL remain present

#### Scenario: Target runtime revision is incompatible
- **WHEN** the verification target declares a different portable runtime revision
- **THEN** the updater MUST refuse before changing the managed commit
- **AND** the clean package SHALL remain launchable at its previous revision

### Requirement: Portable release documentation MUST disclose updater tooling and compatibility boundaries

Portable package notes and bilingual project documentation SHALL identify the full-package bootstrap boundary, Stable and Latest channel meanings, bundled MinGit version/source/license location, code-only compatibility gate, preserved data/runtime paths, automatic failure recovery, and conditions that require a new complete package.

#### Scenario: User reads portable package notes
- **WHEN** a user considers applying a Latest commit update
- **THEN** the notes SHALL explain that latest is less tested than Stable and only compatible code changes are installed
- **AND** they SHALL explain that Python/CUDA/video-runtime revision changes require a new complete package

#### Scenario: Maintainer publishes a portable release
- **WHEN** a bootstrap-or-later portable ZIP is released through external storage
- **THEN** its release documentation SHALL record the bundled Git provenance and preserve the existing package ZIP SHA256 guidance
