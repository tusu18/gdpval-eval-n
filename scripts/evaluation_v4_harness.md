# V4 native workspace instructions

Use the original prompt from `--describe`. Do not read other tasks, previous outputs, gold answers, judge packets, or human labels. This is a shared filesystem with instruction isolation, not an OS sandbox. Original sources are hash-checked and read-only by instruction. No API key is needed or inherited by local builder processes. No paid model calls or external actions are permitted.

Run with the bundled Python:

```text
/Users/tusu18/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/evaluation_v4_workspace.py --task PREFIX --describe
```

Save tool requests as JSON inside your task directory, then use `--request /absolute/request.json`. The root directory is `output/evaluation_v4/solver/<full-task-id>`. Each request has `{ "tool": "name", "arguments": { ... } }`. Basic native writers remain available; the builder route supports native features that those simple schemas cannot express.

1. `list_files`, then `read_file` (continue `next_offset`) and `view_source` for charts, scans, forms and page layout. Display returned `queued_images` through the image tool. The exact queued records can be saved as a JSON array and passed with `--ack` after actual display. Acknowledgement is an attestation, not independent gaze verification.
2. Write your `.mjs` or `.py` builder inside your task directory. Execute through `run_builder`, never by unlogged direct execution. Example arguments: `{ "script": "builders/create.mjs", "artifacts": ["Report.docx", "Model.xlsx"], "timeout_seconds": 300 }`.
3. Builders receive `TASK_OUTPUT_DIR`, `TASK_WORK_DIR`, `TASK_SOURCE_MANIFEST`, and `TASK_NATIVE_XLSX_ADAPTER`. Read the source manifest JSON: each entry contains `name`, original `path`, `sha256`, and a byte-preserving or namespace-only compatible `import_path`. Native output files must be written under `TASK_OUTPUT_DIR` using the filenames listed in `artifacts`. Bundled Node modules resolve normally. Python scripts can import `evaluation_v4_native_xlsx` via the supplied `PYTHONPATH`.
4. The harness copies the exact builder code, records its hash, commands, timestamps, sanitized stdout/stderr, source integrity and every output hash. Failed builds and native revisions remain on disk. Each imported file receives native extraction and visual previews. To register another file from a successful recorded build, use `import_artifact` with the exact absolute output `path` and simple `filename`.
5. `inspect_file` reads each final native artifact. `view_page` queues rendered previews, including complete chart/drawing areas. Display and acknowledge every returned final view, revise through another builder if needed, and `submit_files`. First submission is frozen. Native feature counts and submission do not certify content or business acceptance.

## Builder libraries and native spreadsheet features

Use bundled `@oai/artifact-tool` for spreadsheet and presentation authoring, `docx` for DOCX including images, and installed PDF libraries for PDFs. Follow the relevant bundled document/spreadsheet skills. Preserve requested formats and editable/native functionality.

The artifact-tool quickstart warns that pivot XLSX export is unreliable; bounded API documentation lookup did not expose an authoring signature for pivots or print controls. The narrow `evaluation_v4_native_xlsx.py` adapter supplies these missing native OOXML features after artifact-tool exports the base workbook. It preserves unrelated ZIP members. This is an explicitly disclosed compatibility adapter, not a flat pivot substitute.

Call from JavaScript using `spawnSync('python3', [process.env.TASK_NATIVE_XLSX_ADAPTER, workbookPath, specificationPath], {encoding:'utf8'})`; check the return code and stderr. From Python, `from evaluation_v4_native_xlsx import apply; apply(workbook_path, specification)`.

Example specification using synthetic fields only:

```json
{
  "pivots": [{
    "name": "RegionCategoryTotals",
    "source_sheet": "Data",
    "source_range": "A1:D101",
    "target_sheet": "Summary",
    "target_cell": "A1",
    "row_fields": ["Region", "Category"],
    "values": [{"field": "Amount", "aggregate": "sum", "caption": "Total amount"}],
    "overwrite_target": true
  }],
  "print": [{
    "sheet": "Summary",
    "area": "$A$1:$F$40",
    "orientation": "landscape",
    "paper_size": 9,
    "fit_to_width": 1,
    "fit_to_height": 0
  }]
}
```

Create the source and target worksheets before calling the adapter. Native pivots support one or more categorical `row_fields` (or one `row_field`), one or more numeric value fields using `sum`, `count`, `average`, `min`, or `max`, and a worksheet range source. They have a refreshable source/cache definition, cache records, relationship parts and cached display cells. Column-axis and report-filter-axis pivots are not implemented by this adapter. It does not claim complete Microsoft Excel compatibility. Choose row fields and aggregation from the task; the harness never chooses business logic.

Native charts, filters, dropdown validation, conditional formatting, formulas and visual formatting should be created with artifact-tool. In saved-file checks the harness counts actual OOXML parts/rules. Presence is not proof that the requirement was implemented correctly. Inspection recalculates a separate in-memory copy and never re-exports over the retained native file.

## Visual coverage

DOCX/PDF/PPTX outputs require all rendered pages/slides. Workbooks with at most 120 cell/drawing tiles render every tile. Larger workbooks use up to 12 evenly spaced tiles per sheet, including first and last, plus complete drawing areas. `metadata.visual_coverage` discloses this sampling; unviewed layouts remain unverified. Full native file, full cell/formula extraction and structural audits are retained. This is an engineering coverage limit, not a content failure.

## Public research

When task-relevant web research is needed, use browser/web tools. Record each relied-upon public source with `record_external_source`: `url`, `title`, ISO8601 `retrieved_at`, and either exact `text` or `downloaded_file` (a file under your task directory). Optional `filename` names it in `list_files`. Never pass credentials or paid model URLs. The harness records provenance and hashes, not an independent guarantee of page authenticity. External records live at `external-sources.json`; their content files live under `external-sources/NNN/`. The judge can receive these sources without builder code or model identity.
