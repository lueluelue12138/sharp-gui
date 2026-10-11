## ADDED Requirements

### Requirement: Stable source association
The system SHALL associate generated image/video models and edited copies with a stable source identity. Companion formats SHALL count as one model, and overwriting SHALL preserve the model identity. Filename similarity alone MUST NOT establish an association.

#### Scenario: Repeated generation and editing
- **WHEN** a source is reconstructed twice and one result is saved as an edited copy
- **THEN** the source SHALL expose three models, including the edited parent relation
- **AND** overwriting any result SHALL not increase that count

#### Scenario: Same filename with different contents
- **WHEN** two albums contain different media with the same filename
- **THEN** the associated model lists SHALL remain distinct

### Requirement: Gallery model and task entry points
The gallery grid and full media preview SHALL display completed model counts and queued/running/failed task states. Available models SHALL remain accessible during a subsequent reconstruction. Completed media SHALL offer model viewing as its primary action and regeneration as a secondary action.

#### Scenario: Multiple results
- **WHEN** media has multiple models without a selected default
- **THEN** the viewing entry SHALL show a model chooser with names, covers, dates and reconstruction/edit information

#### Scenario: Default selection
- **WHEN** an authorized user selects a default model belonging to a source
- **THEN** the primary viewing action SHALL open that model and SHALL retain an entry to all associated results

### Requirement: Model source system album
The system SHALL provide a fixed, localized Model Sources album before configured albums. It SHALL list each source once across successful models, include image/video filters, and reuse controlled original media for previews and downloads without duplicating source videos.

#### Scenario: Automatic update
- **WHEN** generation completes, an edit is saved, or a model is deleted
- **THEN** gallery counts, the chooser and the system album SHALL update without a page reload
- **AND** deleting the last associated model SHALL remove the source from the system album

#### Scenario: Existing album thumbnail
- **WHEN** a source has an explicitly associated or content-verified album entry with a cached photo thumbnail or video poster
- **THEN** the system album SHALL reuse those cached image bytes
- **AND** missing caches SHALL fall back to existing model covers without regenerating thumbnails or reading source media

#### Scenario: Model ordering after provenance repair
- **WHEN** background work fills in historical source metadata
- **THEN** the model creation and modification dates SHALL remain unchanged
- **AND** the recent-model sidebar and model library default SHALL order by creation time with newest first

#### Scenario: Historical image after its album is removed
- **WHEN** an image model has missing or empty historical source media type and its former album is removed
- **THEN** the system album SHALL classify the source as an image for thumbnails, previews, counts and filters
- **AND** its existing model cover SHALL remain displayable without generating a new thumbnail or changing the content identity

### Requirement: Safe source availability and migration
Source access SHALL preserve existing path and permission checks. Source unavailability SHALL NOT prevent opening an available model. Historical associations SHALL be recovered only through explicit provenance or verified identical contents, outside synchronous startup and warm pagination.

#### Scenario: Offline video album
- **WHEN** a source video disk is disconnected
- **THEN** the system album SHALL retain its model entry and indicate unavailable source media
- **AND** the associated model SHALL remain viewable

#### Scenario: Replaced media
- **WHEN** a file at an indexed source path has changed contents
- **THEN** the current file SHALL NOT silently inherit associations from a different source version

### Requirement: Integrated visual and language behavior
The new controls SHALL reuse existing glass surfaces, icons, shared tooltips, light/dark theme tokens and bilingual locale resources. Keyboard and touch users SHALL be able to reach model selection actions.

#### Scenario: Preview and return
- **WHEN** a user opens a model from a photo preview and returns to the gallery
- **THEN** the selected album and loaded media context SHALL be retained
