# model-preview-orientation Specification

## Purpose

Define deterministic model preview orientation, framing independence, load isolation, and diagnostics across generated, imported, temporary, and legacy model sources.

## Requirements

### Requirement: Viewer SHALL resolve model orientation from explicit preview context
The system SHALL resolve an active model's initial orientation from a recognized orientation hint or trusted source metadata, and MUST use the conservative default orientation when the context is missing, unknown, or invalid. Model bounds MUST NOT independently select a model orientation.

#### Scenario: ML-SHARP image model has image context
- **WHEN** the user opens a generated image model whose preview context identifies it as an image or default-orientation model
- **THEN** Viewer SHALL use the existing default image orientation
- **AND** Viewer MUST NOT apply Y-front orientation because of the model's bounding-box proportions

#### Scenario: Video reconstruction has Y-front context
- **WHEN** the user opens a generated video model whose preview context identifies it as Y-front
- **THEN** Viewer SHALL apply the existing hidden model-side Y-front correction
- **AND** the initial camera SHALL remain Y-up, looking along the normal Viewer axis, with an orbit polar angle away from either pole

#### Scenario: Imported or temporary model has no trusted orientation
- **WHEN** the user opens an imported asset or temporary Blob preview without a recognized orientation hint
- **THEN** Viewer SHALL use the deterministic default orientation
- **AND** Viewer MUST NOT infer a front axis from AABB proportions, PCA, filename, or model format
- **AND** existing manual orientation presets SHALL remain available

#### Scenario: Legacy model context is recovered safely
- **WHEN** a legacy generated model lacks an explicit orientation hint but trusted source metadata or the existing conservative backfill identifies it as a video reconstruction
- **THEN** the system SHALL resolve it as Y-front
- **AND** an unverified legacy model SHALL remain on the conservative default orientation

### Requirement: Model orientation and camera framing SHALL be independent
The system SHALL decide model orientation before calculating world-space bounds, and camera reset SHALL use bounds only for target, centering, and fit distance without changing the resolved model orientation. Independence means bounds and framing MUST NOT infer or mutate orientation; an already-resolved Y-front model MAY retain the existing bounds-centered framing policy.

#### Scenario: Flat image bounds are available
- **WHEN** a confirmed image model has a shallow or planar bounding box
- **THEN** camera reset MAY use that box to calculate target and distance
- **AND** camera reset MUST NOT rotate the model or change its orientation mode

#### Scenario: Video bounds are available after orientation
- **WHEN** a confirmed Y-front video model has loaded and its corrected world-space bounds are available
- **THEN** camera reset SHALL frame the corrected bounds
- **AND** the initial OrbitControls target SHALL remain aligned with the framed subject rather than an orbit pole workaround

#### Scenario: Model bounds are unavailable
- **WHEN** Spark cannot safely provide model bounds
- **THEN** Viewer SHALL retain the already resolved model orientation
- **AND** camera reset SHALL use the existing fallback framing behavior

#### Scenario: Camera is reset repeatedly
- **WHEN** the user invokes camera reset multiple times for the same loaded model
- **THEN** the model orientation SHALL remain unchanged between resets
- **AND** no hidden correction SHALL accumulate

### Requirement: Preview orientation SHALL be stable across formats and model switches
The system SHALL scope resolved orientation to the active stable model identity rather than its file URL or extension, and SHALL prevent orientation state from leaking between model loads.

#### Scenario: User switches between companion PLY and SPZ files
- **WHEN** the user changes the open format for the same model asset
- **THEN** the resolved orientation and per-model user transform SHALL remain equivalent
- **AND** the format reload SHALL NOT create a second orientation override

#### Scenario: User switches between image and video models
- **WHEN** the user opens an image, then a video, then the image again
- **THEN** each load SHALL resolve orientation from that model's own preview context
- **AND** the previous model's orientation SHALL NOT affect the next model

#### Scenario: An earlier model load is cancelled
- **WHEN** a pending load is superseded by a different model
- **THEN** completion or cancellation of the earlier load MUST NOT mutate the active model's orientation or framing state

### Requirement: Orientation diagnostics SHALL be explicit and localized
Viewer diagnostics SHALL report model orientation mode and decision reason separately from camera framing mode, and all user-visible diagnostic labels MUST be maintained in both English and Chinese locale resources.

#### Scenario: User inspects debug readings
- **WHEN** an active model is loaded and debug readings are visible or copied
- **THEN** the readings SHALL identify the effective orientation and its source or fallback reason
- **AND** the readings SHALL independently identify bounds-centered, default, or unavailable framing
