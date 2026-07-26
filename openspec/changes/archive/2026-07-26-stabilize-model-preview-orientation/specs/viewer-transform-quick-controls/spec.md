## ADDED Requirements

### Requirement: Source orientation and user transforms SHALL remain layered
The system SHALL keep the model's resolved source-orientation correction separate from the user-editable Quick Controls transform. The effective model transform SHALL compose them in a stable order, while per-model persistence SHALL store only the user-editable transform and existing interaction/quality values.

#### Scenario: User adjusts a video model
- **WHEN** a Y-front video model has a hidden source correction and the user changes rotation, position, or scale
- **THEN** the user transform SHALL compose with the source correction without replacing it
- **AND** saving the override MUST NOT serialize the hidden source correction as a user rotation

#### Scenario: User reopens the same model in another format
- **WHEN** a saved per-model override exists and the user reopens the stable asset through a companion PLY or SPZ file
- **THEN** the system SHALL restore the same user transform
- **AND** it SHALL resolve and apply the source orientation exactly once

#### Scenario: User resets the camera
- **WHEN** the user invokes camera reset
- **THEN** the system SHALL reset framing and OrbitControls target only
- **AND** it MUST NOT clear, rewrite, or re-resolve the saved user transform

#### Scenario: User resets orientation
- **WHEN** the user selects the default orientation preset or resets orientation controls
- **THEN** the editable rotation values SHALL return to the current preview baseline
- **AND** any required source-orientation correction SHALL remain separately active

#### Scenario: User resets all overrides
- **WHEN** the user resets all Quick Controls values for the active model
- **THEN** the system SHALL clear the persisted override for that stable model ID
- **AND** the model SHALL return to its source-derived preview baseline without accumulating orientation corrections
