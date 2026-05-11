"""Batch denoising orchestration."""

import logging
import os
import shutil
import tempfile

from .config import (
    AOVConfig,
    DenoiseConfig,
    DEFAULT_INPUT_EXTS,
    AOVS_NEVER_DENOISE,
    normalize_plane_name,
    is_beauty_plane,
)
from .command_builder import build_idenoise_command
from ..discovery.houdini import detect_default_denoiser
from ..discovery.exr_inspector import list_exr_planes
from ..discovery.aov_validator import filter_existing_aovs
from ..utils.file_utils import (
    scan_images,
    natural_sort_key,
    is_image_file,
    build_output_path,
    compute_output_folder,
)
from ..utils.process_utils import run_subprocess

logger = logging.getLogger(__name__)


class Denoiser:
    """Batch image denoiser using Houdini's idenoise."""

    def __init__(
        self,
        input_path,  # type: str
        denoise_config=None,  # type: Optional[DenoiseConfig]
        aov_config=None,  # type: Optional[AOVConfig]
        idenoise_path=None,  # type: Optional[str]
        output_folder=None,  # type: Optional[str]
        extensions=None,  # type: Optional[List[str]]
        file_list=None,  # type: Optional[List[str]]
    ):
        # type: (...) -> None
        """Initialize denoiser.

        Args:
            input_path: Path to file or folder
            denoise_config: Denoising configuration
            aov_config: AOV configuration
            idenoise_path: Path to idenoise executable
            output_folder: Output directory
            extensions: File extensions to process (empty or None = no filtering)
        """
        self.input_path = input_path
        self.denoise_config = denoise_config or DenoiseConfig()
        self.aov_config = aov_config or AOVConfig()
        self.idenoise_path = idenoise_path or detect_default_denoiser()
        self.output_folder = output_folder
        self.extensions = DEFAULT_INPUT_EXTS if extensions is None else extensions
        self.file_list = file_list

        self.temp_root = None  # type: Optional[str]
        self.files = []  # type: List[str]
        self.base_folder = ""  # type: str
        self.dest_folder = ""  # type: str

    def prepare(self):
        # type: () -> Dict[str, Any]
        """Prepare for denoising (validate inputs, create temp dirs).

        Returns:
            Dict with preparation results
        """
        if not self.idenoise_path or not os.path.isfile(self.idenoise_path):
            raise FileNotFoundError("Could not locate idenoise executable")

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
            self.dest_folder = self.output_folder or compute_output_folder(
                self.base_folder, exts
            )
        else:
            if not os.path.exists(self.input_path):
                raise FileNotFoundError("Input not found: {}".format(self.input_path))
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
                        "message": "Unsupported file type: {}".format(self.input_path),
                    }
                self.files = [os.path.basename(self.input_path)]
                self.dest_folder = self.output_folder or compute_output_folder(
                    self.input_path, exts
                )

        # Create temp workspace
        self.temp_root = tempfile.mkdtemp(prefix="idenoise_")
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

    def _validate_aovs(self, probe_file):
        # type: (str) -> None
        """Validate and filter AOVs based on what exists in the EXR."""
        aovs_to_denoise = self.aov_config.aovs_to_denoise

        # Auto-detect AOVs if not specified
        if aovs_to_denoise is None:
            planes = list_exr_planes(probe_file)
            if planes:
                skip = {
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
            normal_plane=validated.get("normal_plane"),
            albedo_plane=validated.get("albedo_plane"),
            motionvectors_plane=validated.get("motionvectors_plane"),
            aovs_to_denoise=filtered_aovs,
            extra_aovs=validated.get("extra_aovs"),
        )

    def denoise_one(self, index, prev_output=None):
        # type: (int, Optional[str]) -> Dict[str, Any]
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
        dst = os.path.join(temp_out, "{}{}".format(self.denoise_config.prefix, fname))
        orig_src = os.path.join(self.base_folder, fname)
        final_dst = build_output_path(
            orig_src, self.dest_folder, self.denoise_config.prefix
        )

        # Check if already exists
        if os.path.exists(final_dst) and not self.denoise_config.overwrite:
            return {
                "status": "skipped",
                "message": "Output exists: {}".format(final_dst),
                "output_path": final_dst,
            }

        # Build command
        prev_frame = None
        if self.denoise_config.temporal and prev_output:
            prev_frame = prev_output if os.path.exists(prev_output) else src

        cmd = build_idenoise_command(
            idenoise_exe=self.idenoise_path,
            input_path=src,
            output_path=dst,
            backend=self.denoise_config.backend,
            normal_plane=self.aov_config.normal_plane,
            albedo_plane=self.aov_config.albedo_plane,
            motionvectors_plane=self.aov_config.motionvectors_plane,
            prev_frame=prev_frame,
            aovs_to_denoise=self.aov_config.aovs_to_denoise,
            extra_aovs=self.aov_config.extra_aovs,
            exrmode=self.denoise_config.exrmode,
            options_json=self.denoise_config.options_json,
        )

        # Run denoising
        success, error = run_subprocess(cmd, timeout=300)
        if not success:
            return {"status": "error", "message": error}

        # Copy to final destination
        try:
            if os.path.exists(final_dst):
                os.remove(final_dst)
            shutil.copy2(dst, final_dst)
        except Exception as e:
            return {"status": "error", "message": "Copy failed: {}".format(e)}

        return {"status": "success", "output_path": final_dst}

    def cleanup(self):
        # type: () -> None
        """Clean up temporary files."""
        if self.temp_root and os.path.exists(self.temp_root):
            try:
                shutil.rmtree(self.temp_root)
            except Exception as e:
                logger.warning("Failed to clean temp dir: %s", e)
