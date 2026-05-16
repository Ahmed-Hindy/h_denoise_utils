# Design Document: UI Denoising Lock

## Overview

When a denoising job starts, all interactive controls in `BaseWindow` are disabled
except the Control_Button (which becomes "Stop"). When the job ends — whether by
completion or cancellation — every widget is restored to the enabled state it had
before the run. The lock state is driven entirely by `UiState.is_running`.

The implementation is intentionally minimal: a single `_apply_ui_lock(locked: bool)`
method on `BaseWindow` that iterates a fixed list of Lockable_Widgets, saves their
pre-run enabled states on lock, and restores them on unlock.

## Architecture

```
BaseWindow
  │
  ├── _start_denoise()
  │     ├── sets UiState.is_running = True
  │     ├── calls _apply_ui_lock(True)   ← disables Lockable_Widgets
  │     └── starts DenoiseWorker
  │
  ├── _on_finished()
  │     ├── sets UiState.is_running = False
  │     └── calls _apply_ui_lock(False)  ← restores Lockable_Widgets
  │
  └── _apply_ui_lock(locked)
        ├── locked=True  → saves each widget's isEnabled(), then setEnabled(False)
        └── locked=False → restores each widget's saved enabled state
```

The `DenoiseWorker` and `UiState` are unchanged. No new signals or threads are
introduced.

## Components and Interfaces

### `BaseWindow._lockable_widgets()` (new)

Returns the ordered list of `QWidget` instances that should be locked during a run.
Defined as a method (not a class-level constant) so it can be called after `__init__`
completes and all widgets exist.

```python
def _lockable_widgets(self):
    # type: () -> List[QtWidgets.QWidget]
    widgets = [
        self.path_edit,
        self.browse_btn,
        self.scan_btn,
        self.files_remove_btn,
        self.files_clear_btn,
        self.preset_combo,
        self.aovs_input,
        self.overwrite_chk,
        self.output_toggle,
        self.advanced_toggle,
        self.advanced_settings_toggle,
        self.prefix_edit,
        self.albedo_combo,
        self.normal_combo,
        self.motion_combo,
        self.temporal_chk,
        self.backend_combo,
        self.thread_spin,
        self.denoiser_combo,
        self.custom_exe_btn,
        self.exrmode_combo,
        self.options_edit,
        self.extra_aovs_edit,
        self.log_filter_combo,
    ]
    return [w for w in widgets if w is not None]
```

Widgets intentionally excluded (remain interactive during a run):
- `control_btn` — must stay enabled to allow stopping
- `progress`, `progress_label`, `action_dest_label`, `output_path_label` — read-only display
- `log_table` — read-only, user may scroll/copy during a run
- `open_output_btn` — harmless; lets user open the output folder mid-run

### `BaseWindow._apply_ui_lock(locked)` (new)

```python
def _apply_ui_lock(self, locked):
    # type: (bool) -> None
    if locked:
        self._pre_run_enabled = {
            w: w.isEnabled() for w in self._lockable_widgets()
        }
        for w in self._lockable_widgets():
            w.setEnabled(False)
    else:
        for w, was_enabled in (self._pre_run_enabled or {}).items():
            w.setEnabled(was_enabled)
        self._pre_run_enabled = {}
```

`_pre_run_enabled` is a `dict` instance variable initialised to `{}` in `__init__`.

### Changes to `_start_denoise()`

After setting `self._ui_state.is_running = True` and before `self.worker.start()`:

```python
self._apply_ui_lock(True)
```

### Changes to `_on_finished()`

After setting `self._ui_state.is_running = False` and before returning:

```python
self._apply_ui_lock(False)
```

### `UiState` (unchanged)

`UiState.is_running` already exists and is the single source of truth for whether
a run is active. No new fields are needed.

## Data Models

### `_pre_run_enabled: Dict[QWidget, bool]`

A transient dictionary stored on `BaseWindow`. It maps each Lockable_Widget to its
`isEnabled()` value captured just before the lock is applied. It is cleared after
the lock is released. It is never persisted.

This design means:
- Widgets that were already disabled before the run (e.g. `temporal_chk` when
  backend is OptiX) are restored to disabled after the run — not incorrectly
  re-enabled.
- No widget-specific special-casing is needed.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid
executions of a system — essentially, a formal statement about what the system
should do. Properties serve as the bridge between human-readable specifications and
machine-verifiable correctness guarantees.*

Property 1: Lock disables all lockable widgets
*For any* `BaseWindow` instance and any arbitrary pre-run enabled/disabled
assignment of its Lockable_Widgets, after `_apply_ui_lock(True)` is called, every
widget returned by `_lockable_widgets()` should have `isEnabled() == False`.
**Validates: Requirements 1.1, 3.2**

Property 2: Lock/unlock round-trip preserves pre-run enabled states
*For any* `BaseWindow` instance and any arbitrary pre-run enabled/disabled
assignment of its Lockable_Widgets, calling `_apply_ui_lock(True)` followed by
`_apply_ui_lock(False)` should leave every Lockable_Widget with exactly the same
`isEnabled()` value it had before the lock was applied — including widgets that
were already disabled (e.g. `temporal_chk` when backend is OptiX).
**Validates: Requirements 2.1, 2.2, 3.3**

Property 3: Unlock with no prior lock is a no-op
*For any* `BaseWindow` instance, calling `_apply_ui_lock(False)` when
`_pre_run_enabled` is empty should not change the `isEnabled()` state of any
Lockable_Widget.
**Validates: Requirements 5.1, 5.2**

## Error Handling

- If `_apply_ui_lock(False)` is called without a prior `_apply_ui_lock(True)` (e.g.
  due to an unexpected exception path), `_pre_run_enabled` will be empty and no
  widgets will be modified — a safe no-op.
- If a widget is garbage-collected between lock and unlock (unlikely in normal use),
  the dict iteration will skip it gracefully because Qt widget deletion removes the
  Python reference.

## Testing Strategy

### Unit Tests

Specific examples and edge cases verified with `pytest-qt`:

- After `_apply_ui_lock(True)`, all widgets in `_lockable_widgets()` are disabled.
- After `_apply_ui_lock(True)`, `control_btn` is still enabled.
- After `_apply_ui_lock(True)` then `_apply_ui_lock(False)`, all widgets are
  restored to their original states.
- A widget that was disabled before the run (e.g. `temporal_chk` set to disabled)
  remains disabled after unlock.
- Calling `_apply_ui_lock(False)` with no prior lock is a no-op.

### Property-Based Tests

Using `hypothesis` with `pytest-qt`. Minimum 100 iterations per property.

Each property test is tagged:
`# Feature: ui-denoising-lock, Property N: <property_text>`

- **Property 1** — Generate a random subset of Lockable_Widgets to be enabled/disabled
  before the lock; verify all are disabled after `_apply_ui_lock(True)`.
- **Property 2** — Generate a random enabled/disabled assignment for all
  Lockable_Widgets; apply lock then unlock; verify each widget's state matches the
  original assignment (including already-disabled widgets staying disabled).
- **Property 3** — Call `_apply_ui_lock(False)` on a fresh window (empty
  `_pre_run_enabled`); verify no widget state changes.

Requirements 1.2, 1.3, 4.1, and 4.2 are concrete single-case assertions covered
by unit tests rather than property tests.
