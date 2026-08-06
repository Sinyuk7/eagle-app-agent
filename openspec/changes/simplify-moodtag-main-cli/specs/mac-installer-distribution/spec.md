## ADDED Requirements

### Requirement: macOS user installer
The system MUST provide a primary macOS installation path that does not require the user to install developer tooling first.

#### Scenario: Install from package
- **WHEN** a macOS user installs the product from the primary distribution package
- **THEN** the user SHALL be able to use the main CLI without installing Python, uv, or npm first

### Requirement: Clear install guidance
The system MUST document the primary install path separately from developer-oriented install paths.

#### Scenario: Distinguish paths
- **WHEN** a user reads installation instructions
- **THEN** the instructions SHALL distinguish the primary macOS path from advanced developer installation paths

### Requirement: Preserve developer install path
The system MUST continue to document developer-oriented installation methods for maintainers and contributors.

#### Scenario: Advanced install available
- **WHEN** a maintainer needs a local development install
- **THEN** the documentation SHALL still provide a developer-oriented installation path
