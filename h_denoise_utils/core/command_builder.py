"""Command builders for denoiser subprocess execution."""

from typing import List, Optional


def build_bundled_optix_command(
    denoiser_exe: str,
    input_path: str,
    output_path: str,
    *,
    beauty_plane: Optional[str] = "C",
    normal_plane: Optional[str] = None,
    albedo_plane: Optional[str] = None,
    aovs_to_denoise: Optional[List[str]] = None,
    verbosity: int = 1,
) -> List[str]:
    """Build the bundled OptiX multipart denoiser command."""
    cmd = [
        denoiser_exe,
        "-v",
        str(verbosity),
        "-multipart",
        input_path,
        "-o",
        output_path,
    ]

    if beauty_plane:
        cmd += ["-beauty-name", beauty_plane]
    if albedo_plane:
        cmd += ["-albedo-name", albedo_plane]
    if normal_plane:
        cmd += ["-normal-name", normal_plane]
    for index, aov_name in enumerate(aovs_to_denoise or []):
        if aov_name:
            cmd += [f"-aov-name{index}", aov_name]

    return cmd
