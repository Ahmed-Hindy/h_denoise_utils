"""Command builder for idenoise subprocess execution."""

import json
from typing import List, Optional


def build_idenoise_command(
    idenoise_exe: str,
    input_path: str,
    output_path: str,
    *,
    backend: str,
    normal_plane: Optional[str] = None,
    albedo_plane: Optional[str] = None,
    motionvectors_plane: Optional[str] = None,
    prev_frame: Optional[str] = None,
    aovs_to_denoise: Optional[List[str]] = None,
    extra_aovs: Optional[List[str]] = None,
    exrmode: Optional[int] = None,
    options_json: Optional[str] = None,
) -> List[str]:
    """Build the idenoise command according to SideFX documentation.

    Args:
        idenoise_exe: Path to idenoise executable
        input_path: Input image path
        output_path: Output image path
        backend: Denoiser backend ('oidn' or 'optix')
        normal_plane: Name of normal plane (-n flag)
        albedo_plane: Name of albedo plane (-a flag)
        motionvectors_plane: Name of motion vectors plane (-m flag)
        prev_frame: Previous frame path for temporal denoising (-p flag)
        aovs_to_denoise: List of AOV names to denoise (--aovs flag)
        extra_aovs: List of extra reference AOVs (--extra_aovs flag)
        exrmode: EXR mode (-1, 0, or 1)
        options_json: JSON string for additional options

    Returns:
        Command list ready for subprocess.run()

    Raises:
        ValueError: If options_json is not valid JSON
    """
    cmd = [idenoise_exe, input_path, output_path]

    if backend:
        cmd += ["-d", backend]
    if normal_plane:
        cmd += ["-n", normal_plane]
    if albedo_plane:
        cmd += ["-a", albedo_plane]
    if motionvectors_plane:
        cmd += ["-m", motionvectors_plane]
    if prev_frame:
        cmd += ["-p", prev_frame]
    if aovs_to_denoise:
        cmd += ["--aovs"] + aovs_to_denoise
    if extra_aovs:
        cmd += ["--extra_aovs"] + extra_aovs
    if exrmode is not None:
        cmd += ["--exrmode", str(exrmode)]
    if options_json:
        # Validate JSON
        try:
            json.loads(options_json)
            cmd += ["--options", options_json]
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in options parameter: {e}")

    return cmd


def override_normal_plane(cmd: List[str], new_normal: str) -> List[str]:
    """Return a copy of idenoise command with -n flag replaced or added.

    Args:
        cmd: Original command list
        new_normal: New normal plane name

    Returns:
        Modified command list with updated normal plane
    """
    out = []
    skip_next = False
    found = False

    for i, tok in enumerate(cmd):
        if skip_next:
            skip_next = False
            continue
        if tok == "-n" and i + 1 < len(cmd):
            out.extend(["-n", new_normal])
            skip_next = True
            found = True
        else:
            out.append(tok)

    if not found:
        # Insert before output path (last arg)
        if len(out) >= 2:
            out = out[:-1] + ["-n", new_normal, out[-1]]
        else:
            out += ["-n", new_normal]

    return out
