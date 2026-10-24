## ADDED Requirements

### Requirement: README is a user getting-started document
README SHALL explain installation, opening Eagle, selecting a folder, choosing a processing policy, selecting a model source, and handling existing metadata.

#### Scenario: New user reads README
- **WHEN** a new user follows the README
- **THEN** the user SHALL be able to start a folder task without first learning internal flags, endpoint paths, sampling parameters, or moodboard layout commands

### Requirement: Model trade-offs are accurate and neutral
User-facing model documentation SHALL explain that local inference avoids remote API call fees but uses local resources, while remote inference avoids local model installation but may charge fees and uploads images to a service.

#### Scenario: User compares model sources
- **WHEN** a user reads the model source section
- **THEN** neither source SHALL be described as preferred, fallback, inherently faster, or universally better

### Requirement: Technical details live in focused documents
Sampling parameters, endpoint details, Ollama cloud controls, benchmark measurements, architecture notes, CLI flags, and moodboard layout instructions SHALL live in linked technical documents rather than the ordinary README.

#### Scenario: Maintainer needs advanced details
- **WHEN** a maintainer needs CLI, model, benchmark, architecture, or moodboard information
- **THEN** the README SHALL link to the corresponding focused document

### Requirement: Installation guidance reflects distribution state
Installation documentation SHALL distinguish signed/notarized release packages, confirmed PyPI releases, and developer source installation.

#### Scenario: macOS Gatekeeper blocks a package
- **WHEN** macOS prevents opening an untrusted package
- **THEN** the documentation SHALL direct the user to System Settings, Privacy & Security, and the approved “Open Anyway” path
