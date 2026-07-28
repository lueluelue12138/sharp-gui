# viewer-transform-quick-controls Specification

## Purpose
TBD - created by archiving change add-viewer-transform-quick-controls. Update Purpose after archive.
## Requirements

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

### Requirement: Quick Controls Entry and Panel Lifecycle
The system SHALL provide a floating quick-controls trigger in the viewer overlay at the bottom-right region, and SHALL open/close a parameter panel without leaving the preview context.

#### Scenario: Trigger position and popup direction
- **WHEN** the viewer overlay is rendered together with the bottom controls bar
- **THEN** the quick-controls trigger SHALL be anchored above the controls-bar top boundary, and the panel SHALL expand upward from the trigger position

#### Scenario: Trigger size consistency with help button
- **WHEN** quick-controls trigger and help trigger are both visible
- **THEN** the quick-controls trigger SHALL use the same visual size as the help trigger

#### Scenario: User opens and closes quick controls
- **WHEN** the user clicks or taps the quick-controls trigger
- **THEN** the system SHALL toggle the panel visibility with the configured viewer overlay animation

#### Scenario: Layout remains operable on small screens
- **WHEN** the quick-controls panel is opened on a narrow or coarse-pointer device
- **THEN** the system SHALL keep all primary controls reachable and SHALL avoid overlap that blocks essential actions (reset/fullscreen/help)

### Requirement: Active Model Transform Adjustment
The system SHALL allow users to adjust active model transform parameters including position (X/Y/Z), rotation (X/Y/Z), and uniform scale, and SHALL apply changes to the active SplatMesh in real time.

#### Scenario: Position/rotation values are applied
- **WHEN** the user updates any transform control value in the quick-controls panel
- **THEN** the active model preview SHALL update immediately to reflect the new transform

#### Scenario: Uniform scale is enforced
- **WHEN** the user changes model scale from quick controls
- **THEN** the system SHALL apply scale using a uniform scalar value so all model axes remain proportionally scaled

### Requirement: Orientation Presets for Common Coordinate Mismatch
The system SHALL provide orientation presets for common model coordinate mismatches, including an upside-down correction preset, and SHALL allow resetting orientation to default.

#### Scenario: Upside-down correction preset
- **WHEN** the user selects the upside-down correction preset
- **THEN** the system SHALL rotate the active model around Z-axis by 180 degrees and display the corrected orientation immediately

#### Scenario: Z-Up correction preset
- **WHEN** the user selects the Z-Up preset
- **THEN** the system SHALL apply the configured X-axis corrective transform (X=-90° baseline mapping) and display the corrected orientation immediately

#### Scenario: Default preset baseline
- **WHEN** the user selects the default preset
- **THEN** the system SHALL restore orientation-related values to the current preview baseline mapping

#### Scenario: Reset orientation
- **WHEN** the user clicks reset orientation
- **THEN** the system SHALL restore orientation-related values to the default preview baseline

### Requirement: Interaction Direction Reversal
The system SHALL provide toggles to reverse pointer-based interaction directions (rotation/scroll and slide/swipe) and SHALL apply them to viewer interaction controls.

#### Scenario: Reverse pointer rotation direction
- **WHEN** the user enables reverse rotation direction
- **THEN** pointer drag and related scroll rotation behavior SHALL be inverted in subsequent interactions

#### Scenario: Reverse pointer slide direction
- **WHEN** the user enables reverse slide direction
- **THEN** pointer slide/swipe translation behavior SHALL be inverted in subsequent interactions

### Requirement: Quick Controls Scope Boundary
The system SHALL scope quick-controls panel to transform and interaction controls only, and SHALL keep quality tuning in existing settings surfaces.

#### Scenario: Quality controls are not shown in quick-controls panel
- **WHEN** the user opens quick-controls panel
- **THEN** quality-specific controls SHALL NOT be displayed in the panel

### Requirement: Per-Model Override Persistence and Reset
The system SHALL store quick-controls overrides per model ID on the client and SHALL restore saved values when the same model is opened again.

#### Scenario: Restore per-model settings
- **WHEN** the user switches away from a model and later reopens that same model
- **THEN** the system SHALL restore previously saved quick-controls values for that model

#### Scenario: Reset all quick-controls overrides
- **WHEN** the user selects reset-all for the active model
- **THEN** the system SHALL clear active model overrides and return to default viewer settings

### Requirement: Internationalization and Accessibility Compliance
The system MUST provide localized labels/tooltips/help text for all quick-controls UI text and MUST provide keyboard/focus-accessible interactions.

#### Scenario: Localized UI text is available
- **WHEN** the application language is switched between supported locales
- **THEN** all quick-controls visible text SHALL render from i18n resources for the selected locale

#### Scenario: Keyboard and focus accessibility
- **WHEN** a keyboard-only user navigates to the quick-controls trigger and panel controls
- **THEN** the user SHALL be able to open/close the panel and operate controls with visible focus indicators and semantic labels

