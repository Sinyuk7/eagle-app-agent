## ADDED Requirements

### Requirement: Image metadata is supplied as per-item user context
The system SHALL include the Eagle item's original name and, when present, its source URL in the user prompt for that item's single image analysis. The system SHALL treat both values as unverified supplemental context, SHALL prioritize image content when context conflicts with pixels, and SHALL NOT fetch or visit the URL.

#### Scenario: Analyze an item with name and source URL
- **WHEN** an item has a name and source URL and is submitted for analysis
- **THEN** the provider's user input contains the original name, source URL, and image for that item

#### Scenario: Analyze an item without a source URL
- **WHEN** an item has a name but no source URL
- **THEN** the user input includes the name, omits the absent URL, and analysis proceeds

#### Scenario: Metadata conflicts with visible content
- **WHEN** the supplied title or URL context conflicts with the attached image
- **THEN** visual analysis prioritizes the image and does not present contextual claims as visible text or brand evidence

### Requirement: Context-sensitive fields retain evidence boundaries
The system SHALL permit title and source context to inform interpretation of brief, use, key, and probable commercial format. `visible_text` and `brand_evidence` SHALL remain grounded in readable or visible image evidence, and `confirmed` commercial-format confidence SHALL require clear visual evidence.

#### Scenario: Context supports probable format interpretation
- **WHEN** title context identifies a format and the image is consistent with that context but lacks conclusive format evidence
- **THEN** the model may use `probable` confidence but does not mark the format `confirmed` based on metadata alone

#### Scenario: Metadata names a brand not visible in the image
- **WHEN** the title or URL names a brand that is not visibly evidenced in the image
- **THEN** the model does not claim that the brand appears in `visible_text` or `brand_evidence`
