## ADDED Requirements

### Requirement: Resolve selected Eagle items
Moodtag SHALL support a `selected` scope that reads Eagle's current selection once at task start and resolves it into a stable item snapshot.

#### Scenario: Non-empty selection
- **WHEN** Eagle reports selected items at task start
- **THEN** Moodtag SHALL analyze only that initial selection even if the user changes the Eagle selection later

#### Scenario: Empty selection
- **WHEN** Eagle reports no selected items
- **THEN** Moodtag SHALL report an empty scope and SHALL NOT initialize a model or call AI analysis

### Requirement: Resolve folder and supported filters
Moodtag SHALL preserve existing Folder scope behavior and SHALL support server-side or explicitly validated filtering by existing Eagle tags, with Rating and Shape exposed only when the target Eagle API semantics are confirmed.

#### Scenario: Folder and tag intersection
- **WHEN** a Folder scope and one or more `--tag` filters are supplied
- **THEN** the resolved scope SHALL contain only items in the folder that match all repeated tag filters

#### Scenario: Manual filter tag outside taxonomy
- **WHEN** a `--tag` filter names an existing Eagle tag absent from the active Moodtag taxonomy
- **THEN** the filter SHALL still be accepted and applied as an Eagle metadata query

### Requirement: Return a stable metadata-bearing scope snapshot
The resolver SHALL return a deduplicated, stably ordered collection of `EagleItem` metadata sufficient for counting, annotation-state inspection, media support checks, preview, and analysis.

#### Scenario: Duplicate item across recursive folders
- **WHEN** recursive folder queries return the same item more than once
- **THEN** the resolved scope SHALL contain that item once using a stable ordering

#### Scenario: Unsupported media in scope
- **WHEN** the resolved scope contains unsupported media
- **THEN** Moodtag SHALL skip and count it using existing media handling without changing the selected scope

### Requirement: Complete pagination and surface unsupported queries
Scope resolution SHALL read all pages required by Eagle's response metadata and SHALL fail clearly when a requested filter cannot be applied or when the API cannot provide a complete result.

#### Scenario: More than one page
- **WHEN** Eagle reports more items than one page can return
- **THEN** Moodtag SHALL request subsequent pages until the complete result is collected without omission or duplication

#### Scenario: Unsupported V2 filter
- **WHEN** Eagle cannot apply a requested selected, tag, rating, or shape filter
- **THEN** Moodtag SHALL report the unsupported capability and SHALL NOT silently run an unfiltered analysis

### Requirement: Empty resolved scope stops before model setup
Moodtag SHALL finish cleanly when filters produce no items and SHALL avoid model configuration and AI requests.

#### Scenario: Filters match nothing
- **WHEN** the resolved scope is empty after all filters are applied
- **THEN** Moodtag SHALL report zero candidates and exit without initializing a provider
