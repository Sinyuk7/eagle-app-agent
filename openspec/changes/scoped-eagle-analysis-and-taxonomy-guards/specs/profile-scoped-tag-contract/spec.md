## ADDED Requirements

### Requirement: Generated tags use the active profile taxonomy
Moodtag SHALL combine model-provided tags and tags derived from accepted `use_intents`, then reconcile the combined candidates against the active Profile Taxonomy before constructing `MoodtagAnalysis.tags`.

#### Scenario: Derived tag is allowed by the active profile
- **WHEN** the model returns a valid use intent whose mapped tag exists in the active taxonomy
- **THEN** the mapped canonical tag MAY appear in `MoodtagAnalysis.tags` and SHALL be subject to the same deduplication and maximum count as direct model tags

#### Scenario: Derived tag is absent from the active profile
- **WHEN** a valid use intent maps to a tag absent from the active taxonomy
- **THEN** the mapped tag SHALL NOT appear in `MoodtagAnalysis.tags`, while the accepted use intent remains available in `MoodtagAnalysis.use_intents`

#### Scenario: Final maximum tag count
- **WHEN** direct tags and derived tags together exceed `max_tags`
- **THEN** the combined canonical result SHALL contain no more than `max_tags` tags

### Requirement: Reconciliation reports unknown tags without misclassifying duplicates
The reconciliation SHALL canonicalize case-insensitive matches, accept the first occurrence of a valid tag, ignore later valid duplicates, and report only non-empty unknown values as rejected tags.

#### Scenario: Repeated valid tag
- **WHEN** the candidate list contains `Fashion` and `fashion` and `fashion` is allowed
- **THEN** the result SHALL contain one canonical tag and SHALL NOT list the repeated value in `rejected_tags`

#### Scenario: Unknown tag
- **WHEN** a candidate does not exist in the active taxonomy
- **THEN** the candidate SHALL be excluded from canonical tags and SHALL appear once in `rejected_tags`

### Requirement: Taxonomy does not filter existing Eagle tags
Moodtag SHALL apply the active taxonomy only to tags generated during the current analysis and SHALL preserve existing Eagle tags during safe writeback regardless of whether they occur in the taxonomy.

#### Scenario: Existing manual tag outside taxonomy
- **WHEN** an Eagle item has an existing manual tag `CELINE` and the active taxonomy does not contain `CELINE`
- **THEN** writeback SHALL preserve `CELINE` and SHALL append only reconciled generated tags

### Requirement: Tag groups derive from final canonical tags
`tag_groups` SHALL be computed from the final reconciled canonical tags and the active profile taxonomy.

#### Scenario: Profile-specific grouping
- **WHEN** the same label exists in one profile taxonomy but not another
- **THEN** each analysis SHALL group only tags accepted by its own active profile
