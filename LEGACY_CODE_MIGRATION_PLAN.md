# Legacy Code Migration Plan

## Current Status

### ✅ Safe to Remove (No External Dependencies)

#### 1. `app/core/engine/cleanup.py`
- **Status**: DEPRECATED with warning since Phase 1
- **Dependencies**: 
  - Only imported by `app/core/engine/history.py`
  - Uses `ICleanupHandler` from interfaces
- **Safe to move**: ✅ YES
- **Action**: Move to `app/core/engine/_legacy/cleanup.py`

#### 2. `app/core/engine/history.py`
- **Status**: BEING MIGRATED
- **Dependencies**:
  - Only used internally (no external imports found)
  - Imports from `cleanup.py`
  - Defines `history_service = HistoryService()`
- **Safe to move**: ✅ YES
- **Action**: Move to `app/core/engine/_legacy/history.py`

### ⚠️ KEEP (Still Used)

#### 3. `app/core/interfaces/cleanup.py`
- **Status**: Interface preserved for backward compatibility
- **Used by**:
  - `app/core/file/rewind.py`
  - `app/core/memory/rewind.py`
  - `app/infrastructure/database/models/rewind.py`
  - `app/domain/learning/rewind.py`
  - `app/domain/todo/rewind.py`
  - `app/core/engine/rewind/state.py`
  - `app/core/engine/cleanup.py` (legacy)
- **Safe to move**: ❌ NO
- **Action**: Keep in place - interface still actively used

## Migration Steps

### Step 1: Create Legacy Directory
```bash
mkdir -p app/core/engine/_legacy
```

### Step 2: Move Files
```bash
# Move cleanup.py to legacy
mv app/core/engine/cleanup.py app/core/engine/_legacy/cleanup.py

# Move history.py to legacy
mv app/core/engine/history.py app/core/engine/_legacy/history.py
```

### Step 3: Update Imports in Moved Files
Update internal imports within the legacy files to use new paths:
- `cleanup.py`: Update import of `ICleanupHandler` (if needed)
- `history.py`: Update import of `cleanup_side_effects`

### Step 4: Create Compatibility Shim (Optional)
Create `app/core/engine/cleanup.py` and `app/core/engine/history.py` with:
```python
# Deprecated - moved to _legacy/
import warnings
warnings.warn(
    "This module has moved to app.core.engine._legacy",
    DeprecationWarning,
    stacklevel=2
)
from app.core.engine._legacy.cleanup import *  # or specific exports
```

### Step 5: Run Tests
```bash
pytest tests/integration/rewind/ tests/unit/core/rewind/ -v
```

## Verification Checklist

- [ ] No imports of `cleanup` from `app.core.engine.cleanup`
- [ ] No imports of `history` from `app.core.engine.history`
- [ ] No usage of `history_service`
- [ ] No usage of `HistoryService`
- [ ] No usage of `cleanup_side_effects`
- [ ] All rewind tests pass
- [ ] Server starts successfully
- [ ] Retry API works correctly
- [ ] Rewind API works correctly

## Rollback Plan

If issues are discovered:
1. Restore files from `_legacy/` back to original location
2. Update imports if needed
3. Restart server
4. Verify functionality

## Notes

- The `ICleanupHandler` interface is intentionally kept in `app/core/interfaces/cleanup.py`
- New handlers still implement this interface for consistency
- Legacy files are moved (not deleted) for safety
- If no issues after 1 week, legacy files can be permanently removed
