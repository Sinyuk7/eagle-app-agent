## ADDED Requirements

### Requirement: Remote retries are bounded and provider aware

Remote retries SHALL remain within the current task and SHALL be limited to transient rate-limit or server failures. Authentication, quota/billing, permanent validation, strict-schema incompatibility, and other permanent failures SHALL NOT be retried.

#### Scenario: Rate-limited response with Retry-After

- **WHEN** a Remote request receives HTTP 429 with a valid Retry-After value
- **THEN** the next attempt SHALL wait according to that value within the configured retry limit

#### Scenario: Transient server response without Retry-After

- **WHEN** a Remote request receives a retryable 5xx response without a valid Retry-After value
- **THEN** the client SHALL use bounded exponential backoff with jitter

#### Scenario: Permanent request error

- **WHEN** a Remote request receives an authentication, quota/billing, schema incompatibility, or permanent validation error
- **THEN** the client SHALL fail without issuing another attempt

#### Scenario: Unknown submission

- **WHEN** a POST response is lost and submission state is `unknown`
- **THEN** the client SHALL retain the diagnostic and SHALL NOT blindly replay the request

### Requirement: Remote concurrency defaults to ten workers

Remote batch analysis SHALL use a default maximum concurrency of 10 while preserving the existing bounded `ThreadPoolExecutor` scheduling and CLI `--concurrency` override.

#### Scenario: Default Remote concurrency

- **WHEN** no concurrency override is supplied for Remote analysis
- **THEN** no more than 10 Remote analysis tasks SHALL execute concurrently

#### Scenario: User override

- **WHEN** the user supplies `--concurrency`
- **THEN** the supplied value SHALL control Remote worker concurrency within existing validation rules

#### Scenario: Ollama concurrency independence

- **WHEN** Ollama analysis is selected
- **THEN** changing the Remote default to 10 SHALL NOT change Ollama’s existing default concurrency behavior

### Requirement: First-item validation remains serial and bounded

The batch workflow SHALL continue validating one real item before starting the remaining Remote worker tasks, and SHALL avoid pre-encoding or submitting the entire scope at once.

#### Scenario: First item succeeds

- **WHEN** the first supported image validates successfully
- **THEN** the workflow SHALL start the remaining bounded Remote workers

#### Scenario: First item fails

- **WHEN** the first validation request fails
- **THEN** the workflow SHALL report the failure according to existing policy and SHALL NOT start the remaining Remote worker tasks

#### Scenario: Large scope

- **WHEN** the scope contains more items than the worker limit
- **THEN** queued work SHALL remain bounded by the existing Future scheduling and SHALL not create unbounded simultaneous requests
