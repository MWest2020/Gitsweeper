# report-rendering

## Purpose

Provide a single, pluggable seam through which every analysis
capability emits its results. Centralising the renderer contract
means each analysis stays focused on what it computes, output
formats can be added without touching analysis code, and end users
get a uniform `--json` / table experience across capabilities.
## Requirements
### Requirement: Define a renderer interface that consumes structured results

The system SHALL expose a renderer interface that accepts a
structured analysis result — not pre-formatted strings — so that
analysis capabilities never decide how output is presented.

#### Scenario: Structured input only

- **GIVEN** an analysis capability has produced a result
- **WHEN** that capability hands the result to a renderer
- **THEN** the value handed over is a structured object (rows,
  records, or a typed result model), not a pre-formatted string,
  table, or JSON blob
- **AND** the renderer is fully responsible for turning that
  structure into bytes for an output stream

### Requirement: Ship a CLI table renderer and a JSON renderer in v1

The system SHALL provide at least two concrete renderers in v1: a
human-readable CLI table renderer (the default) and a JSON renderer
selected by the user.

#### Scenario: CLI table is the default

- **GIVEN** the user has not selected an output format
- **WHEN** an analysis result is rendered
- **THEN** the CLI table renderer is used
- **AND** the table is written to standard output

#### Scenario: JSON renderer selected explicitly

- **GIVEN** the user has selected JSON output (for example, via
  `--json`)
- **WHEN** an analysis result is rendered
- **THEN** the JSON renderer is used
- **AND** the rendered output on standard output is valid JSON,
  with no decorative banners, log lines, or table characters mixed
  in
- **AND** any progress, warning, or diagnostic text goes to
  standard error, not standard output

### Requirement: Allow new renderers without changing analysis capabilities

The system SHALL allow new output formats — such as markdown, PDF,
or dashboard payloads — to be added by introducing a new
implementation of the renderer interface, without modifying any
analysis capability.

#### Scenario: Adding a markdown renderer is a local change

- **GIVEN** a new markdown renderer is being introduced
- **WHEN** the renderer is added to the codebase
- **THEN** the change touches only the rendering layer (the new
  renderer plus the registration that makes it selectable)
- **AND** no analysis capability's source files require edits to
  produce markdown output

### Requirement: Renderers MUST contain no analysis logic

Renderers SHALL be pure presentation. They MUST NOT compute,
aggregate, filter, sort, or otherwise alter the substance of an
analysis result.

#### Scenario: Renderer receives an already-final result

- **GIVEN** an analysis result handed to a renderer
- **WHEN** the renderer produces output
- **THEN** the values shown are exactly the values present in the
  input structure (with formatting only — number formatting, column
  alignment, JSON encoding)
- **AND** the renderer performs no computation that would change
  any value, exclude any record, or re-order records in a way that
  carries semantic meaning

### Requirement: Provide a markdown renderer in the registry

The system SHALL provide a markdown renderer, selectable through the
same renderer registry as the existing CLI-table and JSON renderers,
that converts an `AnalysisResult` into a GitHub-flavoured markdown
fragment containing a heading, a table of rows, and a metadata
block.

#### Scenario: Markdown renderer selected by name

- **GIVEN** the renderer registry is queried for `"markdown"`
- **WHEN** an `AnalysisResult` is rendered
- **THEN** the markdown renderer is used
- **AND** the output is a markdown fragment whose first non-blank
  line is a level-2 heading derived from the result's title

#### Scenario: Markdown renderer is pure presentation

- **GIVEN** an `AnalysisResult` is rendered to markdown
- **WHEN** the rendered text is parsed back as markdown
- **THEN** every value present in the input result appears in the
  rendered output (with formatting only — number formatting, table
  alignment)
- **AND** the renderer performs no computation, filtering, or
  reordering that changes meaning

#### Scenario: Adding the markdown renderer does not break existing renderers

- **GIVEN** the registry now contains markdown alongside table and
  json
- **WHEN** an existing caller selects `"table"` or `"json"`
- **THEN** the previously-shipping renderers behave identically to
  before

