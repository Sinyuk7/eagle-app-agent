## ADDED Requirements

### Requirement: Both profiles return a strict title suggestion
The system SHALL require `suggest_title` as a string in both `default` and `editorial` analysis responses. An empty string SHALL mean that the existing name is meaningful enough to preserve; a non-empty value SHALL be a concise, searchable replacement title without a file extension. Missing or non-string values SHALL fail normal schema or response validation.

#### Scenario: Existing name is meaningful
- **WHEN** the original name already provides useful identification or search context
- **THEN** the model returns `suggest_title` as an empty string

#### Scenario: Existing name is generic or meaningless
- **WHEN** the original name is generic, temporary, or meaningless and image content supports a useful title
- **THEN** the model returns a non-empty concise title without an extension

#### Scenario: Suggestion field is missing or has the wrong type
- **WHEN** an analysis response omits `suggest_title` or returns a non-string value
- **THEN** response validation fails rather than silently defaulting the field

### Requirement: Title suggestions stay out of annotation text
The system SHALL use `suggest_title` only for conditional item renaming and SHALL NOT serialize it, the original name, or the source URL into the Eagle annotation.

#### Scenario: Build annotation with a title suggestion
- **WHEN** a normalized analysis contains a non-empty `suggest_title`
- **THEN** the generated annotation retains the existing annotation-field contract and contains no title suggestion or input metadata

### Requirement: Rename safely during the existing write operation
When writing analysis results, the system SHALL include a valid non-empty suggested title as the Eagle item's `name` while preserving the item's original extension. The system SHALL apply the rename only if the latest item name still matches the name analyzed. It SHALL omit `name` from the update when the suggestion is empty, invalid, or the latest name has changed. Tags and annotation SHALL continue through the existing write flow.

#### Scenario: Write a valid title suggestion
- **WHEN** write mode is enabled, the suggestion is valid and non-empty, and the latest name matches the analyzed name
- **THEN** one Eagle V2 item update includes the suggested name with the original extension together with the normal tags and annotation

#### Scenario: Preserve an item renamed after analysis
- **WHEN** the latest Eagle name differs from the analyzed item's original name
- **THEN** the update omits `name` and continues writing valid tags and annotation

#### Scenario: No rename is suggested or suggestion is invalid
- **WHEN** the suggestion is empty or fails title validation
- **THEN** the update omits `name` and continues writing valid tags and annotation

#### Scenario: Dry run
- **WHEN** write mode is not enabled
- **THEN** the system does not modify the Eagle item's name, tags, or annotation

### Requirement: Eagle metadata writes use the V2 update endpoint
The system SHALL write item metadata through `/api/v2/item/update`, including only fields that are to be changed. This change SHALL NOT migrate unrelated Eagle endpoints.

#### Scenario: Update tags and annotation without renaming
- **WHEN** an analysis write has no applicable title suggestion
- **THEN** the V2 update request includes the item ID, tags, and annotation and omits `name`

#### Scenario: Update name with other analysis metadata
- **WHEN** an analysis write has an applicable title suggestion
- **THEN** the V2 update request includes `name`, tags, and annotation in the same request
