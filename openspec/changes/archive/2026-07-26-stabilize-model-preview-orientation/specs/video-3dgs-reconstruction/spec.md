## ADDED Requirements

### Requirement: Video preview orientation SHALL require verified video provenance
The video reconstruction pipeline SHALL record a normalized Y-front preview-orientation hint with successful video model metadata, and Viewer SHALL apply video orientation only when an explicit hint, trusted video source metadata, or the existing conservative legacy recovery verifies that provenance.

#### Scenario: New video reconstruction completes
- **WHEN** a video reconstruction successfully produces a model
- **THEN** its sidecar and model-asset projection SHALL identify the model as video-derived
- **AND** they SHALL expose the Y-front preview-orientation hint used by Viewer

#### Scenario: Verified video model opens in Viewer
- **WHEN** a verified video model is opened from any model-asset entry point
- **THEN** Viewer SHALL retain the existing hidden model-side Y-front correction
- **AND** camera reset MUST NOT move the initial orbit to a polar singularity to reproduce the front view

#### Scenario: Legacy video has no explicit orientation hint
- **WHEN** a legacy generated model lacks an orientation hint but the existing safe backfill verifies a unique source video
- **THEN** the system SHALL treat it as a video model for preview orientation

#### Scenario: Legacy source remains ambiguous
- **WHEN** a generated model has neither trusted image/video metadata nor a unique safe legacy match
- **THEN** the system MUST use the unknown/default preview policy
- **AND** bounding-box shape MUST NOT promote it to video orientation

#### Scenario: Image bounds resemble a video model
- **WHEN** an image-generated model satisfies any former video-like AABB depth ratio
- **THEN** Viewer MUST preserve image orientation
- **AND** video compatibility behavior MUST NOT alter the image model's initial preview
