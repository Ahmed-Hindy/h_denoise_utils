# Requirements Document

## Introduction

When the user starts a denoising job by pressing the "Denoise" button, most of the
UI should become non-interactive until the job finishes or the user cancels it.
This prevents accidental configuration changes mid-run, avoids confusing state, and
makes it visually clear that a job is in progress. The "Stop" button (the same
control button, relabelled during a run) must remain enabled so the user can cancel
at any time.

## Glossary

- **Denoiser_UI**: The `BaseWindow` Qt main window that hosts all controls.
- **Control_Button**: The `control_btn` QPushButton that reads "Denoise" at rest and
  "Stop" during a run.
- **Lockable_Widget**: Any interactive widget in the Denoiser_UI that is not the
  Control_Button and is not a read-only display widget (progress bar, labels, log
  table).
- **Denoising_Run**: The period between the user pressing "Denoise" and the
  `DenoiseWorker` emitting its `finished` signal (including cancellation).
- **UiState**: The `UiState` dataclass in `state.py` that tracks `is_running` and
  related flags.

## Requirements

### Requirement 1: Lock UI on Denoising Start

**User Story:** As a user, I want the UI controls to be disabled when denoising
starts, so that I cannot accidentally change settings while a job is running.

#### Acceptance Criteria

1. WHEN a Denoising_Run begins, THE Denoiser_UI SHALL disable all Lockable_Widgets.
2. WHEN a Denoising_Run begins, THE Denoiser_UI SHALL leave the Control_Button
   enabled so the user can stop the run.
3. WHEN a Denoising_Run begins, THE Denoiser_UI SHALL leave read-only display
   widgets (progress bar, progress label, log table, output path labels) enabled
   and interactive.

### Requirement 2: Restore UI on Denoising Finish

**User Story:** As a user, I want all UI controls to be re-enabled automatically
when denoising finishes or is cancelled, so that I can start a new job without
restarting the application.

#### Acceptance Criteria

1. WHEN a Denoising_Run ends (success or cancellation), THE Denoiser_UI SHALL
   re-enable all Lockable_Widgets that were disabled at run start.
2. WHEN a Denoising_Run ends, THE Denoiser_UI SHALL restore each widget to exactly
   the enabled state it had before the run started.

### Requirement 3: Consistent Lock State via UiState

**User Story:** As a developer, I want the lock state to be driven by `UiState`,
so that the enabled/disabled state of widgets is always consistent with the
`is_running` flag.

#### Acceptance Criteria

1. THE Denoiser_UI SHALL derive the enabled/disabled state of Lockable_Widgets
   solely from `UiState.is_running`.
2. WHEN `UiState.is_running` is `True`, THE Denoiser_UI SHALL have all
   Lockable_Widgets disabled.
3. WHEN `UiState.is_running` is `False`, THE Denoiser_UI SHALL have all
   Lockable_Widgets enabled (subject to their own independent enable conditions,
   e.g. temporal checkbox disabled when backend is OptiX).

### Requirement 4: Keyboard Shortcut Behaviour During Run

**User Story:** As a user, I want the Ctrl+Enter shortcut to stop an active run
(not start a new one), so that keyboard-driven workflows remain consistent with
the button state.

#### Acceptance Criteria

1. WHILE a Denoising_Run is active, WHEN the user presses Ctrl+Enter, THE
   Denoiser_UI SHALL invoke the stop action (equivalent to clicking "Stop").
2. WHILE no Denoising_Run is active, WHEN the user presses Ctrl+Enter, THE
   Denoiser_UI SHALL invoke the start action (equivalent to clicking "Denoise").

### Requirement 5: No Partial Lock States

**User Story:** As a developer, I want the lock/unlock to be applied atomically,
so that there are no frames where some widgets are locked and others are not.

#### Acceptance Criteria

1. WHEN the lock is applied, THE Denoiser_UI SHALL disable all Lockable_Widgets in
   a single synchronous call before the worker thread is started.
2. WHEN the lock is released, THE Denoiser_UI SHALL re-enable all Lockable_Widgets
   in a single synchronous call within the `_on_finished` handler, before returning.
