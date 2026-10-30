# Submission Hygiene & Clean Repo Checklist

Internal checklist for pre-submission verification and repository cleanup:

- [x] **No hardcoded secrets or sensitive keys** in git history (All keys generated dynamically in `data/` and git-ignored).
- [x] **No compiled bytecode artifacts** (`__pycache__`, `.pyc`, `.pytest_cache` excluded in `.gitignore`).
- [x] **All 150 automated tests pass** (`python -m pytest tests -q`).
- [x] **Redundant/Duplicate files cleaned up**:
  - `message.md` & `read-jashan.md` are consolidated into the master `README.md`.
  - Stale `v1/` legacy prototype files and temporary scratch files (`1.json`, `PPT GAP.md`) can be safely archived/removed.
