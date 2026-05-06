## ADDED Requirements

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
