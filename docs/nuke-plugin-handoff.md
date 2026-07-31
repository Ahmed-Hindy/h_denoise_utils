# Nuke denoiser nodes handoff

Last updated: 2026-07-31

## Current state

Work remains on draft pull request #44 and must not be merged or published yet.

- Branch: `dev/nuke-optix`
- Package identity: `HDenoiseNodes`
- Nodes: `HOptixDenoise` and `HOidnDenoise`
- Platform: Windows x64
- PR: draft and mergeable

The permanent design is documented in
[Nuke denoiser architecture](nuke-plugin-architecture.md). New contributors
should start with [Nuke denoiser onboarding](nuke-plugin-onboarding.md).

## Completed implementation

### HOptixDenoise

- Native Nuke `PlanarIop` using the CUDA Driver API and NVIDIA OptiX.
- Beauty, optional albedo, and optional normal inputs.
- Reusable thread-safe CUDA/OptiX session and GPU buffers.
- Input blend, tile size, GPU selection, normal encoding, and error passthrough.
- Spatial denoising only.

### HOidnDenoise

- Native Nuke `PlanarIop` with the same three-input contract.
- OIDN 2.5 CUDA backend.
- Fast, Balanced, and High quality modes.
- HDR, clean auxiliary guides, normal encoding, GPU selection, blend, and
  passthrough controls.
- OIDN runs in `HOidnBridge.exe` through versioned raw float buffers rather than
  intermediate EXRs.

The helper is a required ABI boundary. Direct OIDN initialization inside Nuke
crashed because Nuke's private Visual C++ and oneTBB DLLs conflict with Intel's
binary OIDN runtime. The package therefore includes only the OIDN core and CUDA
runtime DLLs.

## Package identity decision

The combined package has been renamed from the misleading `HOptixDenoise`
container to:

```text
HDenoiseNodes/
```

The public Nuke class names remain unchanged. The manifest, CMake install
location, build script, release validator, fixtures, launcher, package README,
and documentation all use the neutral package identity.

This decision is complete and should not be revisited before the first release
unless manual artist feedback exposes a concrete naming problem.

## Acceptance completed

The checked-in `tools/validate_nuke_denoiser_acceptance.py` passes on Nuke
17.0v3 with the OptiX 9.1 package. It verifies:

- both native classes instantiate;
- required knobs exist and have expected defaults and tooltips;
- all three inputs remain connected after save/reopen;
- non-default OptiX and OIDN controls serialize correctly;
- live OptiX and OIDN renders complete;
- invalid OIDN GPU selection produces readable passthrough behavior;
- no OIDN exchange files remain after evaluation.

The checked-in `tools/validate_nuke_oidn_cancellation.py` launches a UHD OIDN
render in a separate Nuke process, sends Ctrl+Break after `HOidnBridge.exe`
starts, and verifies:

- Nuke reports cancellation;
- the helper exits;
- no exchange files leak.

The live Canyon Run playground also renders guided OptiX, guided OIDN, and the
amplified difference branch.

## Performance benchmark

`tools/benchmark_nuke_denoiser_nodes.py` provides a reproducible Nuke 17.0v3
benchmark. It uses one warm-up frame and the median of three animated-frame EXR
renders, subtracting a source-write baseline.

Current approximate guided overhead on CUDA device 0:

| Resolution | OptiX | OIDN Fast | OIDN Balanced | OIDN High |
| --- | ---: | ---: | ---: | ---: |
| 1920 x 1080 | 0.35 s | 0.82 s | 0.79 s | 0.84 s |
| 3840 x 2160 | 1.44 s | 2.81 s | 2.95 s | 3.22 s |

The helper overhead is acceptable for the first release. UHD timings contain
occasional outliers, so they should not be used as a quality-mode ranking.
Persistent helper or shared-memory work remains deferred until production
profiling demonstrates a real bottleneck.

## Validation already completed

- 169 Python tests passed before the acceptance-tool additions.
- Ruff, workflow YAML, PowerShell parsing, and whitespace checks passed.
- All Nuke/OptiX pairs built and rendered locally:
  - Nuke 14.1v8, 15.0v1, 15.1v4, and 17.0v3;
  - OptiX 8.1, 9.0, and 9.1.
- The 12-package matrix passed release identity, source commit, dependency,
  runtime-set, size, and SHA-256 validation before the neutral-container commit.
- Hosted PR checks and CodeRabbit are green.

A fresh final matrix must be generated after the latest documentation and
acceptance-tool commit so package manifests contain the final source SHA.

## Self-hosted workflow status

The repository currently has no registered `nuke-ndk` self-hosted runner.
Therefore the `Nuke Denoiser Nodes` workflow cannot be meaningfully dispatched;
it would remain queued. Release publication must remain disabled.

Once a runner is registered, dispatch in this order:

1. `single`, Nuke 17.0v3, OptiX 9.1, publish disabled;
2. inspect the uploaded `HDenoiseNodes` ZIP and manifest;
3. `supported-matrix`, publish disabled;
4. run the release validator against all downloaded artifacts.

## Remaining pre-merge work

1. Commit the acceptance, cancellation, benchmark, and documentation updates.
2. Run focused tests, the full Python suite, Ruff, YAML parsing, PowerShell
   parsing, and Markdown-link validation.
3. Build the final 12 local packages from the resulting commit.
4. Validate the final matrix against that exact source SHA.
5. Check PR review comments and CI.
6. Leave the PR draft until the user explicitly decides it is ready.

## Deferred work

Not required for the first release:

- OptiX temporal state;
- Linux Nuke packages;
- CPU or non-NVIDIA OIDN backends;
- persistent OIDN helper service;
- shared-memory bridge transport;
- multi-frame or multi-AOV batching in one native node.

## Working-tree caution

Do not stage the old local artifacts:

- `nul`
- `tools/build_optix_denoiser.ps1`
- `tools/build_optix_denoiser_windows.ps1`
- `tools/fetch_optix_denoiser.ps1`
