## ADDED Requirements

### Requirement: Model asset opening SHALL preserve preview orientation context
The model asset service and frontend opening flow SHALL preserve a generated asset's trusted source media classification and normalized preview-orientation hint through list, recent, detail, open, reload, and companion-format selection paths. Imported assets without trusted orientation metadata SHALL be represented as unknown rather than guessed.

#### Scenario: User opens a generated image asset
- **WHEN** an asset is backed by image-generation metadata
- **THEN** the asset opening context SHALL identify the default image orientation
- **AND** the Viewer handoff SHALL retain that context

#### Scenario: User opens a generated video asset
- **WHEN** an asset is backed by video-reconstruction metadata
- **THEN** the asset opening context SHALL identify the video source and Y-front orientation
- **AND** opening from the recent sidebar, library grid, toolbar, or details panel SHALL produce the same context

#### Scenario: User opens an imported asset
- **WHEN** an imported model has no recognized preview-orientation metadata
- **THEN** the asset opening context SHALL mark its orientation as unknown
- **AND** the frontend MUST NOT replace that unknown value with a geometry-derived guess

#### Scenario: Asset exposes companion formats
- **WHEN** one stable asset exposes PLY and SPZ or another supported companion format
- **THEN** every file choice SHALL use the same asset-level source and orientation context
- **AND** changing the preferred open format SHALL preserve the stable asset identity

#### Scenario: Legacy video metadata is backfilled
- **WHEN** the existing conservative legacy-video recovery identifies exactly one trusted source for a generated asset
- **THEN** the refreshed asset summary SHALL expose video source and orientation context
- **AND** ordinary warm pagination MUST NOT repeatedly rescan source media to make that decision
