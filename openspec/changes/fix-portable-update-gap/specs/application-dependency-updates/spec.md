## ADDED Requirements

### Requirement: Application dependencies MUST have a complete trusted lock

An update target using separately managed application dependencies MUST declare an immutable dependency set with exact distribution versions, supported Python constraints, trusted artifact sources, integrity digests, and all transitive dependencies. The initial supported dependency type SHALL be pure Python wheels. Dependency resolution MUST NOT choose unspecified versions or build source distributions during an update.

#### Scenario: Target adds the workbench progress dependency
- **WHEN** an accepted target requires `websocket-client` and the installed portable environment does not contain it
- **THEN** the updater SHALL prepare the exact locked dependency automatically as part of the requested update
- **AND** successful installation SHALL provide the workbench WebSocket progress capability without a manual package installation

#### Scenario: A dependency is not fully locked
- **WHEN** a target contains an unlocked dependency, unknown artifact digest, unsupported Python constraint, or untrusted source
- **THEN** the updater MUST reject dependency preparation with an actionable reason
- **AND** it MUST NOT stop the working application or change its dependency selection

#### Scenario: Target requests a native or source distribution
- **WHEN** an application dependency requires a native extension, source build, or install-time executable hook
- **THEN** this update path MUST reject the artifact before installation
- **AND** it MUST NOT invoke a compiler or arbitrary setup code

### Requirement: Dependency preparation MUST preserve the base environment

The system SHALL prepare application dependencies in an isolated installation-local set, verify artifact integrity and safe contents, and make only complete verified sets available for loading. It MUST leave bundled Python, base site-packages, Torch/CUDA, native tools, user files, and system environments unchanged. It MUST NOT permit application dependency sets to override protected base or standard-library modules.

#### Scenario: Download fails or integrity does not match
- **WHEN** a dependency download times out, fails TLS verification, or has an incorrect digest
- **THEN** preparation MUST fail without changing the running application's code or dependency set
- **AND** a partial artifact MUST NOT become importable

#### Scenario: Archive attempts to escape the dependency set
- **WHEN** an artifact contains path traversal, external absolute paths, links, executable startup hooks, or protected import roots
- **THEN** the system MUST reject it
- **AND** files outside the preparation directory MUST remain unchanged

#### Scenario: A verified dependency set is already available
- **WHEN** the exact target lock and all corresponding verified local contents are present
- **THEN** the updater SHALL reuse that set without resolving newer package versions
- **AND** reuse MUST still verify that it matches the requested target

### Requirement: Dependency loading MUST follow the application revision

Application processes and health verification SHALL select only the dependency set declared by the checked-out application revision. Selection SHALL occur before business modules are imported and SHALL work without system Python, system pip, or user-defined import paths. Importing the application or requesting update status MUST NOT download or install dependencies.

#### Scenario: Application restarts after a dependency update
- **WHEN** the verified target instance starts
- **THEN** its imported application dependency versions SHALL match the target lock
- **AND** the update MUST NOT be reported successful merely because the port is reachable

#### Scenario: Application starts while a dependency set is incomplete
- **WHEN** the requested dependency set is missing or not fully verified
- **THEN** the process MUST report a dependency-not-ready result suitable for recovery
- **AND** it MUST NOT silently use an incompatible bundled or system package or install packages during import

#### Scenario: Update is downgraded to a historical application
- **WHEN** the owner applies an accepted historical target that has no isolated dependency declaration
- **THEN** the restarted process SHALL use that target's original dependency loading behavior
- **AND** no newer dependency overlay SHALL leak through inherited process state

### Requirement: Dependency changes MUST participate in recovery and maintenance

The updater SHALL retain the previous working dependency selection until the new application passes verification and SHALL recover the previous application and dependency combination after failure or interruption. Dependency maintenance MUST preserve sets referenced by an active transaction, current revision, or retained recovery point.

#### Scenario: New dependency imports but the application fails health verification
- **WHEN** the target fails import or restart verification after code mutation
- **THEN** the updater SHALL restore the previous application revision and its dependency selection
- **AND** the restored process SHALL successfully use its previous locked versions

#### Scenario: Process stops between code and dependency activation
- **WHEN** the updater is interrupted at any persisted transaction stage
- **THEN** recovery SHALL select a matching code and dependency combination before declaring the installation usable
- **AND** it MUST NOT declare success with mixed previous and target components

#### Scenario: A later target removes an application dependency
- **WHEN** version B removes or replaces a dependency used in version A
- **THEN** B SHALL load only the set declared for B
- **AND** recovery to A SHALL still have access to A's verified set

### Requirement: All installation paths SHALL consume the same dependency contract

Source installation, future portable construction, regular updates, and the legacy bootstrap tool SHALL use the same application dependency lock and integrity rules. A clean source installation MUST have an explicit preparation command that does not rely on the maintainer's existing Python packages.

#### Scenario: New installation and updated installation reach the same revision
- **WHEN** a newly installed instance and an updated portable instance run the same supported application revision
- **THEN** their separately managed application dependency versions SHALL match the same lock
