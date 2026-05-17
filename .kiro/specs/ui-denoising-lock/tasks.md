# Implementation Plan: UI Denoising Lock

## Overview

Add `_lockable_widgets()` and `_apply_ui_lock()` to `BaseWindow`, wire them into
`_start_denoise()` and `_on_finished()`, and cover the behaviour with unit and
property-based tests. Do it in a new git worktree.

## Tasks

- [x] 1. Add `_pre_run_enabled` initialisation and `_lockable_widgets()` to `BaseWindow`
  - In `BaseWindow.__init__`, add `self._pre_run_enabled = {}` after the existing
    instance variable declarations.
  - Add `_lockable_widgets()` method returning the list of interactive widgets
    (path_edit, browse_btn, scan_btn, files_remove_btn, files_clear_btn,
    preset_combo, aovs_input, overwrite_chk, output_toggle, advanced_toggle,
    advanced_settings_toggle, prefix_edit, albedo_combo, normal_combo,
    motion_combo, temporal_chk, backend_combo, thread_spin, denoiser_combo,
    custom_exe_btn, exrmode_combo, options_edit, extra_aovs_edit,
    log_filter_combo). Filter out `None` entries.
  - _Requirements: 1.1, 1.2, 1.3, 3.1_

- [x] 2. Implement `_apply_ui_lock()` and wire it into the denoising lifecycle
  - [x] 2.1 Implement `_apply_ui_lock(locked: bool)` on `BaseWindow`
    - When `locked=True`: snapshot each widget's `isEnabled()` into
      `_pre_run_enabled`, then call `setEnabled(False)` on each.
    - When `locked=False`: restore each widget's enabled state from
      `_pre_run_enabled`, then clear the dict. No-op if dict is empty.
    - _Requirements: 1.1, 2.1, 2.2, 5.1, 5.2_

  - [x] 2.2 Call `_apply_ui_lock(True)` in `_start_denoise()`
    - Insert the call after `self._ui_state.is_running = True` and before
      `self.worker.start()`.
    - _Requirements: 1.1, 5.1_

  - [x] 2.3 Call `_apply_ui_lock(False)` in `_on_finished()`
    - Insert the call after `self._ui_state.is_running = False` and before
      the method returns.
    - _Requirements: 2.1, 2.2, 5.2_

- [x] 3. Checkpoint — verify manual smoke test passes
  - Ensure all existing tests still pass, ask the user if questions arise.

- [x] 4. Write tests for the UI lock behaviour
  - [x] 4.1 Write unit tests in `tests/test_ui_denoising_lock.py`
    - Test: after `_apply_ui_lock(True)`, all `_lockable_widgets()` are disabled.
    - Test: after `_apply_ui_lock(True)`, `control_btn` is still enabled.
    - Test: after `_apply_ui_lock(True)` then `_apply_ui_lock(False)`, all widgets
      are restored to their original states.
    - Test: a widget disabled before the run (e.g. `temporal_chk.setEnabled(False)`)
      remains disabled after unlock.
    - Test: calling `_apply_ui_lock(False)` with no prior lock is a no-op.
    - Test: Ctrl+Enter shortcut calls `_stop_denoise` when `is_running=True`.
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 3.3, 4.1, 5.1, 5.2_

  - [x]* 4.2 Write property-based tests using `hypothesis` in `tests/test_ui_denoising_lock.py`
    - **Property 1: Lock disables all lockable widgets**
      - Strategy: `st.lists(st.booleans(), ...)` to generate a random enabled/disabled
        assignment; apply to widgets; call `_apply_ui_lock(True)`; assert all disabled.
      - `# Feature: ui-denoising-lock, Property 1: lock disables all lockable widgets`
      - **Validates: Requirements 1.1, 3.2**
    - **Property 2: Lock/unlock round-trip preserves pre-run enabled states**
      - Strategy: random enabled/disabled assignment; lock then unlock; assert each
        widget's state equals the original assignment.
      - `# Feature: ui-denoising-lock, Property 2: lock/unlock round-trip preserves pre-run enabled states`
      - **Validates: Requirements 2.1, 2.2, 3.3**
    - **Property 3: Unlock with no prior lock is a no-op**
      - Strategy: capture widget states on a fresh window; call `_apply_ui_lock(False)`;
        assert no state changed.
      - `# Feature: ui-denoising-lock, Property 3: unlock with no prior lock is a no-op`
      - **Validates: Requirements 5.1, 5.2**
    - Configure `@settings(max_examples=100)` on each property test.

- [x] 5. Final checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP.
- `control_btn`, `progress`, `progress_label`, `action_dest_label`,
  `output_path_label`, `log_table`, and `open_output_btn` are intentionally
  excluded from `_lockable_widgets()`.
- The `_pre_run_enabled` snapshot pattern handles widgets that are already disabled
  before a run (e.g. `temporal_chk` when backend is OptiX) without any
  widget-specific special-casing.
