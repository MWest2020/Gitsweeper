## 1. Dependency

- [ ] 1.1 Add `matplotlib` to `[project] dependencies` in
      `pyproject.toml`. Run `uv lock`.

## 2. SVG-chart helper in lib/rendering

- [ ] 2.1 Function `render_line_svg(rows, *, x, y, by, title) ->
      str` that takes a list of dicts (or AnalysisResult.rows
      with a column index map), groups by the `by` dimension,
      plots one line per group on a single axes with title and
      legend, returns the SVG as a string.
- [ ] 2.2 No state — pure function so callers can fan out to
      many charts without worrying about pyplot global state.

## 3. dashboard capability

- [ ] 3.1 New module `capabilities/dashboard.py` with `publish(conn,
      out_dir, *, repos=None, since=None, baseline=12,
      threshold=2.0)`. Empty cache for the requested scope raises
      a clear error.
- [ ] 3.2 The function:
      a. Computes the four analyses (`kpi_timeseries`,
         `regression_monitoring`, `effort_allocation`,
         `pr_classification.compute_classification` once per repo
         in scope).
      b. Writes JSON files under `<out>/data/`.
      c. Writes per-repo HTML under `<out>/repo/<owner>-<name>.html`,
         each with embedded SVG charts.
      d. Writes `<out>/index.html` as the portfolio overview.
      e. Writes `<out>/assets/style.css`.

## 4. CLI

- [ ] 4.1 New command `gitsweeper publish [--out PATH] [--repos]
      [--since] [--baseline] [--threshold] [--db-path]`. Default
      `--out` is `docs/examples/dashboard/`.

## 5. Tests

- [ ] 5.1 Empty cache raises clear error, no partial bundle.
- [ ] 5.2 Publish writes index.html, per-repo .html files, JSON
      data files, CSS asset.
- [ ] 5.3 No `<script>` tags or remote URLs in any rendered HTML.
- [ ] 5.4 Index lists every repo in scope.
- [ ] 5.5 `--repos` filters the index.
- [ ] 5.6 JSON data files parse and contain the same rows the
      capabilities produce when called directly.

## 6. Validation, smoke, archive

- [ ] 6.1 `openspec validate --strict`.
- [ ] 6.2 `pytest -q` and `ruff check .` clean.
- [ ] 6.3 Smoke against the existing
      `cache/conductionnl-openregister.sqlite`:
      `gitsweeper publish --out docs/examples/dashboard-test/
      --since 2026-01-01 --baseline 6` and eyeball the result.
- [ ] 6.4 Update `CHANGELOG.md`.
- [ ] 6.5 `openspec archive static-site-publish`.
