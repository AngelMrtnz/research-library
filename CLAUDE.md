# Research Library

Read `PLAN.md` first. Project skills live in `.claude/skills/`: `research-library-builder` for code changes, `paper-intake-review` for metadata, naming and BibTeX rules.
Never add a code path that renames files or writes `library.bib` outside `Library.confirm` / `Library.undo` / `Library.delete` (each one a click by the owner).
Run `pytest -q` and `ruff check .` before committing.
