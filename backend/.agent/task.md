# Refactor Backend Utilities

- [ ] Refactor `app/infrastructure/filesystem/tool.py`
    - Replace `subprocess.run` with `app.utils.process.run_command`.
    - Use `DEFAULT_EXCLUDED_DIRS` from `app.constants`.
- [ ] Refactor `app/domain/codebase/analysis/tools.py`
    - Use `DEFAULT_EXCLUDED_DIRS` from `app.constants`.
