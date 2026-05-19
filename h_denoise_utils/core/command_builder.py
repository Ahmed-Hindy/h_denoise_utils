"""Command builders for denoiser subprocess execution."""

from typing import List, Optional


def build_bundled_multipart_command(
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
    """Build the bundled multipart Denoiser.exe command.

    The custom OptiX and OIDN wrappers intentionally share this CLI contract.
    """
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


def build_bundled_optix_command(*args, **kwargs) -> List[str]:
    """Build the bundled OptiX multipart denoiser command."""
    return build_bundled_multipart_command(*args, **kwargs)


def build_oidn_denoise_command(
    denoiser_exe: str,
    input_path: str,
    output_path: str,
    *,
    albedo_path: Optional[str] = None,
    normal_path: Optional[str] = None,
    device: Optional[str] = None,
    quality: Optional[str] = None,
    threads: Optional[int] = None,
    verbosity: int = 1,
) -> List[str]:
    """Build a stock oidnDenoise command for separate feature images.

    The official oidnDenoise app is useful as an upstream reference for simple
    image inputs. Production multipart EXR denoising uses the custom
    Denoiser.exe wrapper and build_bundled_multipart_command().
    """
    cmd = [denoiser_exe]

    if device:
        cmd += ["--device", device]

    cmd += ["--hdr", input_path]

    if albedo_path:
        cmd += ["--alb", albedo_path]
    if normal_path:
        cmd += ["--nrm", normal_path]
    if quality:
        cmd += ["--quality", quality]
    if threads is not None:
        cmd += ["--threads", str(threads)]

    cmd += ["-o", output_path, "-v", str(verbosity)]
    return cmd
