## ADDED Requirements

### Requirement: Managed legacy portable packages SHALL have a persistent bootstrap path

The project SHALL provide a small versioned migration tool through the canonical release distribution for supported legacy portable packages whose updater rejects the new target before it can obtain the new update logic. The tool SHALL work without downloading a replacement complete portable environment and SHALL remain obtainable after newer releases supersede the initial migration release.

#### Scenario: Old updater rejects a compatible newer application
- **WHEN** a verified supported runtime 4 or runtime 6 package cannot reach a newer target because of its original equality gate
- **THEN** the owner SHALL be able to run the lightweight tool to enter the new update mechanism
- **AND** successful migration SHALL not require editing runtime metadata or installing a temporary intermediate Stable tag

#### Scenario: Legacy user skips several releases
- **WHEN** a supported user first migrates after later Stable tags and main commits have been published
- **THEN** an obtainable supported migration tool SHALL resolve the requested trusted channel and validate a path to it
- **AND** migration MUST NOT depend on the initial bridge tag remaining the highest Stable tag or main head

#### Scenario: Installation has no managed Git baseline
- **WHEN** the tool finds a historical snapshot without the required managed worktree or bundled update tools
- **THEN** it MUST leave that installation unchanged and explain the required installation path
- **AND** it MUST NOT claim that every old portable archive supports this migration

### Requirement: Bootstrap execution MUST use trusted content and portable tools

The bootstrap entry point SHALL use the existing package's Python and MinGit, operate locally under the same ownership constraints as the update CLI, and obtain the version-pinned migration helper from the canonical verified source. It MUST resolve exact trusted targets and MUST NOT accept arbitrary repository URLs, commands, branches, or SHAs. Its initial execution MUST NOT require newly introduced application dependencies.

#### Scenario: Computer has no system Python or Git
- **WHEN** the owner runs the tool from a supported clean-extracted portable package with system Python and Git unavailable
- **THEN** identification, dependency preparation, migration, and restart SHALL use package-local tools

#### Scenario: Bootstrap content cannot be verified
- **WHEN** helper provenance, artifact integrity, canonical Git target, or TLS verification fails
- **THEN** the tool MUST stop before modifying the existing application
- **AND** it MUST NOT disable transport verification or execute an unverified fallback

#### Scenario: Existing application cannot import the new dependency
- **WHEN** the old package does not contain the new application's progress dependency
- **THEN** the tool SHALL be able to prepare the dependency using its supported bootstrap logic
- **AND** it MUST NOT import the new business application before preparation succeeds

### Requirement: Bootstrap migration SHALL share update safety and recovery

The migration tool SHALL enforce dirty-worktree, active-work, target-compatibility, concurrent-operation, and exact-revision checks and SHALL use the same code/dependency transaction and recovery rules as regular updates. It MUST preserve package provenance, user data, and the base runtime. Running generation work MUST NOT be interrupted to perform migration.

#### Scenario: Local modifications or active work are present
- **WHEN** the old installation has modified tracked files, active application work, or an update lock
- **THEN** migration MUST refuse with an actionable reason before mutation or stopping the service

#### Scenario: Migration succeeds
- **WHEN** dependency preparation, target application verification, and restarted service checks all pass
- **THEN** the tool SHALL report the installed exact revision and completion
- **AND** workspace, models, configuration, certificates, base runtime, bundled tools, and original package metadata SHALL remain preserved

#### Scenario: Migration fails after mutation
- **WHEN** the new application fails verification or restart
- **THEN** the tool SHALL restore and restart the previous working application and dependency selection
- **AND** it SHALL report failure and successful recovery separately from migration success

### Requirement: Bootstrap compatibility claims MUST have published-package evidence

Compatibility declarations SHALL be limited to package targets and historical baselines with recorded clean-extraction verification. The initial release gate SHALL cover the actual runtime 4 and runtime 6 packages for each of the three supported Windows targets or explicitly withhold an unverified baseline from supported claims. Release instructions and tool feedback SHALL have synchronized Chinese and English text.

#### Scenario: A candidate baseline has only source-diff evidence
- **WHEN** maintainers find no new base dependency in the source history but have not verified the corresponding real archive
- **THEN** that evidence alone MUST NOT be described as completed package compatibility validation

#### Scenario: Verified old package completes migration and subsequent updates
- **WHEN** the clean-extracted baseline passes bootstrap, later application/dependency updates, downgrade, and failure recovery checks
- **THEN** the published support record SHALL identify its target, original package digest, original baseline, migrated revision, and verification outcome
