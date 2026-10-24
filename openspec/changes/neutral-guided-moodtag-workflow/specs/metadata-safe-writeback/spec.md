## ADDED Requirements

### Requirement: Moodtag processing status is three-state
The system SHALL classify an item as missing, valid, or malformed based on a reliably identified complete Moodtag annotation block.

#### Scenario: Item has only manual metadata
- **WHEN** an item has manual tags, manual annotation, or both but no complete Moodtag block
- **THEN** its status SHALL be missing and skip-existing SHALL select it for processing

#### Scenario: Item has a complete Moodtag block
- **WHEN** an item contains a complete and reliably bounded Moodtag annotation
- **THEN** its status SHALL be valid and skip-existing SHALL skip it

#### Scenario: Item has an incomplete or ambiguous block
- **WHEN** an item has missing fields, duplicate fields, or an annotation boundary that cannot be reliably identified
- **THEN** its status SHALL be malformed, SHALL be reported separately, and SHALL NOT be silently overwritten

### Requirement: Generated tags preserve existing tags
A Moodtag write SHALL merge generated tags with existing Eagle tags using stable de-duplication.

#### Scenario: Item has manual tags
- **WHEN** analysis produces AI tags for an item that already has Eagle tags
- **THEN** the update SHALL preserve all existing tags and append only non-duplicate generated tags

#### Scenario: User regenerates an existing analysis
- **WHEN** overwrite or regenerate policy produces new AI tags
- **THEN** the update SHALL preserve and merge existing tags, even if older AI tags cannot be distinguished from manual tags, and user-facing text SHALL NOT claim complete tag replacement

### Requirement: Generated annotation replaces only Moodtag content
A Moodtag write SHALL replace an existing reliably bounded Moodtag annotation region while preserving unrelated user annotation content.

#### Scenario: Item has manual notes and an existing Moodtag block
- **WHEN** analysis produces a new annotation block
- **THEN** the update SHALL preserve manual notes and replace only the existing Moodtag block

#### Scenario: Item has manual notes without a Moodtag block
- **WHEN** analysis produces the first Moodtag annotation
- **THEN** the update SHALL append the generated block without deleting manual notes

#### Scenario: Legacy annotation boundary is ambiguous
- **WHEN** an old-format annotation cannot be safely bounded
- **THEN** the update SHALL preserve the original annotation and report malformed status for explicit handling

### Requirement: Eagle updates support partial fields and latest metadata
The Eagle adapter SHALL allow an update containing tags, annotation, or both, and writeback SHALL refresh current item metadata immediately before composing the update.

#### Scenario: User edits an item during analysis
- **WHEN** AI analysis completes after the user changed tags or annotation in Eagle
- **THEN** writeback SHALL fetch the latest item metadata, merge against that snapshot, and omit fields not intended to change

#### Scenario: Skip policy sees a newly completed item
- **WHEN** skip-existing was selected but a fresh metadata read finds a valid Moodtag block
- **THEN** writeback SHALL skip the item instead of overwriting the newer result

#### Scenario: Reset removes Moodtag annotation
- **WHEN** reset removes Moodtag content from an item
- **THEN** the adapter SHALL update annotation only and SHALL NOT send an empty tags list

### Requirement: Reset is safe for user metadata
The ordinary reset operation SHALL remove Moodtag-owned annotation content and SHALL preserve all tags and unrelated annotation content.

#### Scenario: Item contains manual tags
- **WHEN** a user runs reset
- **THEN** manual tags SHALL remain unchanged

#### Scenario: Item has no identifiable Moodtag tag ownership
- **WHEN** reset encounters tags whose origin cannot be proven
- **THEN** reset SHALL leave those tags untouched
