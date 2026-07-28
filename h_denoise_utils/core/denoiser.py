"""Batch denoising orchestration."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from typing import Any

from ..constants import DEFAULT_DENOISER_TIMEOUT_SECONDS
from ..discovery.aov_validator import filter_existing_aovs
from ..discovery.bundled_denoiser import resolve_bundled_denoiser
from ..discovery.bundled_oidn import resolve_bundled_oidn_denoiser
from ..discovery.exr_inspector import list_exr_planes
from ..utils.file_utils import (
    build_output_path,
    compute_output_folder,
    is_image_file,
    natural_sort_key,
    scan_images,
)
from ..utils.process_utils import run_subprocess
from .command_builder import build_bundled_multipart_command
from .config import (
    AOVS_NEVER_DENOISE,
    DEFAULT_INPUT_EXTS,
    AOVConfig,
    DenoiseConfig,
    is_beauty_plane,
    normalize_plane_name,
)

logger = logging.getLogger(__name__)


def _build_denoiser_subprocess_environment(
    backend: str,
    denoiser_path: str,
    *,
    platform_name: str | None = None,
    current_env: dict[str, str] | None = None,
) -> dict[str, str] | None:
    """Build runtime environment overrides for a denoiser subprocess.

    Args:
        backend: Denoiser backend key.
        denoiser_path: Path to the native denoiser executable.
        platform_name: Optional platform override for tests.
        current_env: Optional base environment override for tests.

    Returns:
        Environment mapping for the subprocess, or None when no override is needed.
    """
    platform_key = platform_name or os.name
    if backend != "oidn" or platform_key == "nt":
        return None

    env = dict(os.environ if current_env is None else current_env)
    runtime_dir = os.path.dirname(os.path.abspath(denoiser_path))
    existing = env.get("LD_LIBRARY_PATH")
    env["LD_LIBRARY_PATH"] = (
        runtime_dir if not existing else f"{runtime_dir}:{existing}"
    )
    return env


class Denoiser:
    """Batch image denoiser using bundled multipart Denoiser.exe backends."""

    def __init__(
        self,
        input_path: str,
        denoise_config: DenoiseConfig | None = None,
        aov_config: AOVConfig | None = None,
        denoiser_path: str | None = None,
        output_folder: str | None = None,
        extensions: list[str] | None = None,
        file_list: list[str] | None = None,
    ) -> None:
        """Initialize denoiser.

        Args:
            input_path: Path to file or folder
            denoise_config: Denoising configuration
            aov_config: AOV configuration
            denoiser_path: Optional path to bundled denoiser executable
            output_folder: Output directory
            extensions: File extensions to process (empty or None = no filtering)
        """
        self.input_path = input_path
        self.denoise_config = denoise_config or DenoiseConfig()
        self.aov_config = aov_config or AOVConfig()
        if denoiser_path:
            self.denoiser_path = denoiser_path
        elif self.denoise_config.backend == "oidn":
            self.denoiser_path = resolve_bundled_oidn_denoiser(required=False)
        else:
            self.denoiser_path = resolve_bundled_denoiser(required=False)
        self.output_folder = output_folder
        self.extensions = DEFAULT_INPUT_EXTS if extensions is None else extensions
        self.file_list = file_list

        self.temp_root: str | None = None
        self.files: list[str] = []
        self.base_folder: str = ""
        self.dest_folder: str = ""

    def prepare(self) -> dict[str, Any]:
        """Prepare for denoising (validate inputs, create temp dirs).

        Returns:
            Dict with preparation results
        """
        if not self.denoiser_path or not os.path.isfile(self.denoiser_path):
            backend_upper = self.denoise_config.backend.upper()
            raise FileNotFoundError(f"Could not locate bundled {backend_upper} denoiser executable")
        if self.denoise_config.backend not in ("optix", "oidn"):
            raise ValueError("The bundled denoiser branch only supports OptiX and OIDN")
        if self.denoise_config.temporal:
            raise ValueError("Temporal denoising is not validated in the bundled denoiser branch")
        if self.denoise_config.threads:
            raise ValueError("CPU thread count is not exposed by the bundled denoiser v1")
        if self.denoise_config.exrmode is not None:
            raise ValueError("Legacy EXR mode does not apply to the bundled denoiser")
        if self.denoise_config.options_json:
            raise ValueError("Legacy JSON options are not supported by the bundled denoiser")
        if self.aov_config.motionvectors_plane:
            raise ValueError("Motion vectors are not used by the bundled denoiser v1")
        if self.aov_config.extra_aovs:
            raise ValueError("Extra reference AOVs are not supported by the bundled denoiser v1")

        # Normalize extensions
        exts = None
        if self.extensions:
            exts = [".{}".format(e.lstrip(".").lower()) for e in self.extensions]

        # Build file list
        if self.file_list:
            valid_files = [f for f in self.file_list if os.path.isfile(f)]
            if exts:
                valid_files = [f for f in valid_files if is_image_file(f, exts)]
            if not valid_files:
                return {"status": "no_files", "message": "No image files found"}

            base_dirs = {os.path.dirname(f) for f in valid_files}
            if len(base_dirs) != 1:
                return {
                    "status": "mixed_folders",
                    "message": "Selected files must be in the same folder",
                }

            self.base_folder = base_dirs.pop()
            files_with_names = [(os.path.basename(f), f) for f in valid_files]
            files_with_names.sort(key=lambda pair: natural_sort_key(pair[0]))
            self.files = [name for name, _ in files_with_names]
            self.dest_folder = self.output_folder or compute_output_folder(self.base_folder, exts)
        else:
            if not os.path.exists(self.input_path):
                raise FileNotFoundError(f"Input not found: {self.input_path}")
            if os.path.isdir(self.input_path):
                self.base_folder = self.input_path
                self.files = scan_images(self.input_path, exts)
                self.files.sort(key=natural_sort_key)
                if not self.files:
                    return {"status": "no_files", "message": "No image files found"}
                self.dest_folder = self.output_folder or compute_output_folder(
                    self.input_path, exts
                )
            else:
                self.base_folder = os.path.dirname(self.input_path) or os.getcwd()
                if not is_image_file(self.input_path, exts):
                    return {
                        "status": "unsupported",
                        "message": f"Unsupported file type: {self.input_path}",
                    }
                self.files = [os.path.basename(self.input_path)]
                self.dest_folder = self.output_folder or compute_output_folder(
                    self.input_path, exts
                )

        # Create temp workspace
        self.temp_root = tempfile.mkdtemp(prefix="hdu_denoise_")
        temp_in = os.path.join(self.temp_root, "in")
        temp_out = os.path.join(self.temp_root, "out")
        os.makedirs(temp_in, exist_ok=True)
        os.makedirs(temp_out, exist_ok=True)

        # Copy files to temp
        for f in self.files:
            shutil.copy2(os.path.join(self.base_folder, f), os.path.join(temp_in, f))

        # Validate AOVs
        if self.files:
            probe_file = os.path.join(self.base_folder, self.files[0])
            self._validate_aovs(probe_file)

        os.makedirs(self.dest_folder, exist_ok=True)

        return {
            "status": "ready",
            "file_count": len(self.files),
            "output_folder": self.dest_folder,
        }

    def _validate_aovs(self, probe_file: str) -> None:
        """Validate and filter AOVs based on what exists in the EXR."""
        aovs_to_denoise = self.aov_config.aovs_to_denoise

        # Auto-detect AOVs if not specified
        if aovs_to_denoise is None:
            planes = list_exr_planes(probe_file)
            if planes:
                skip = {
                    normalize_plane_name(self.aov_config.beauty_plane),
                    normalize_plane_name(self.aov_config.normal_plane),
                    normalize_plane_name(self.aov_config.albedo_plane),
                    normalize_plane_name(self.aov_config.motionvectors_plane),
                }
                skip |= {p.lower() for p in AOVS_NEVER_DENOISE}
                aovs_to_denoise = [
                    p
                    for p in planes
                    if normalize_plane_name(p) not in skip and not is_beauty_plane(p)
                ]
                logger.info("Auto-detected AOVs: %s", aovs_to_denoise)

        # Validate AOVs exist
        validated = filter_existing_aovs(
            probe_file,
            normal_plane=self.aov_config.normal_plane,
            albedo_plane=self.aov_config.albedo_plane,
            motionvectors_plane=self.aov_config.motionvectors_plane,
            aovs_to_denoise=aovs_to_denoise,
            extra_aovs=self.aov_config.extra_aovs,
        )

        # Remove beauty/combined passes from explicit AOV list
        filtered_aovs = validated.get("aovs_to_denoise")
        if filtered_aovs:
            filtered_aovs = [p for p in filtered_aovs if not is_beauty_plane(p)]
            if not filtered_aovs:
                filtered_aovs = None

        # Update config with validated values
        self.aov_config = AOVConfig(
            beauty_plane=self.aov_config.beauty_plane,
            normal_plane=validated.get("normal_plane"),
            albedo_plane=validated.get("albedo_plane"),
            motionvectors_plane=validated.get("motionvectors_plane"),
            aovs_to_denoise=filtered_aovs,
            extra_aovs=validated.get("extra_aovs"),
        )

    def denoise_one(self, index: int, prev_output: str | None = None) -> dict[str, Any]:
        """Denoise a single file.

        Args:
            index: File index
            prev_output: Previous output path (for temporal)

        Returns:
            Dict with result status
        """
        if index >= len(self.files):
            return {"status": "error", "message": "Invalid index"}

        fname = self.files[index]
        temp_in = os.path.join(self.temp_root, "in")
        temp_out = os.path.join(self.temp_root, "out")

        src = os.path.join(temp_in, fname)
        dst = os.path.join(temp_out, f"{self.denoise_config.prefix}{fname}")
        orig_src = os.path.join(self.base_folder, fname)
        final_dst = build_output_path(orig_src, self.dest_folder, self.denoise_config.prefix)

        # Check if already exists
        if os.path.exists(final_dst) and not self.denoise_config.overwrite:
            return {
                "status": "skipped",
                "message": f"Output exists: {final_dst}",
                "output_path": final_dst,
            }

        cmd = build_bundled_multipart_command(
            denoiser_exe=self.denoiser_path,
            input_path=src,
            output_path=dst,
            beauty_plane=self.aov_config.beauty_plane or "C",
            normal_plane=self.aov_config.normal_plane,
            albedo_plane=self.aov_config.albedo_plane,
            aovs_to_denoise=self.aov_config.aovs_to_denoise,
        )

        # Run denoising
        env = _build_denoiser_subprocess_environment(
            self.denoise_config.backend,
            self.denoiser_path,
        )
        success, error = run_subprocess(
            cmd,
            timeout=DEFAULT_DENOISER_TIMEOUT_SECONDS,
            env=env,
        )
        if not success:
            return {"status": "error", "message": error}

        # Copy to final destination
        try:
            if os.path.exists(final_dst):
                os.remove(final_dst)
            shutil.copy2(dst, final_dst)
        except Exception as e:
            return {"status": "error", "message": f"Copy failed: {e}"}

        return {"status": "success", "output_path": final_dst}

    def cleanup(self) -> None:
        """Clean up temporary files."""
        if self.temp_root and os.path.exists(self.temp_root):
            try:
                shutil.rmtree(self.temp_root)
            except Exception as e:
                logger.warning("Failed to clean temp dir: %s", e)
