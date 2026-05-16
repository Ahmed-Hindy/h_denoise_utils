"""Prototype multilayer EXR wrapper for the compiled NvidiaAIDenoiser.

This is intentionally isolated from the main app. It extracts multipart EXR
subimages with Houdini's hoiiotool, runs the standalone OptiX denoiser on the
beauty plane and optionally selected AOVs, then recomposes the original
subimage order into one multipart EXR.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


RAW_AOV_NAMES = {
    "albedo",
    "alpha",
    "crypto",
    "cryptomatte",
    "depth",
    "id",
    "mask",
    "motion",
    "motionvector",
    "motionvectors",
    "n",
    "normal",
    "normals",
    "p",
    "position",
    "velocity",
    "z",
}


@dataclass(frozen=True)
class PlaneInfo:
    index: int
    name: str
    channels: List[str]
    pixel_type: str = ""

    @property
    def channel_count(self) -> int:
        return len(self.channels)


@dataclass(frozen=True)
class RunResult:
    command: List[str]
    returncode: int
    seconds: float
    log_path: str


def safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return stem.strip("._") or "unnamed"


def parse_plane_list(value: Optional[Iterable[str]]) -> List[str]:
    if not value:
        return []
    out = []
    seen = set()
    for raw in value:
        for part in str(raw).split(","):
            name = part.strip()
            key = name.lower()
            if name and key not in seen:
                seen.add(key)
                out.append(name)
    return out


def parse_oiiotool_info(text: str) -> List[PlaneInfo]:
    planes = []
    current = None
    channel_parts = []

    def flush_channels() -> None:
        nonlocal channel_parts
        if current is None or not channel_parts:
            return
        channels_text = " ".join(channel_parts)
        current["channels"] = re.findall(r"[A-Za-z0-9_.]+", channels_text)
        channel_parts = []

    def finish_current() -> None:
        nonlocal current, channel_parts
        if current is None:
            return
        flush_channels()
        name = current["name"] or "subimage_{}".format(current["index"])
        planes.append(
            PlaneInfo(
                index=current["index"],
                name=name,
                channels=current["channels"],
                pixel_type=current["pixel_type"],
            )
        )
        current = None
        channel_parts = []

    for line in text.splitlines():
        subimage = re.match(
            r"\s*subimage\s+(\d+):.*?,\s*\d+\s+channel,\s+([A-Za-z0-9_]+)",
            line,
            re.IGNORECASE,
        )
        if subimage:
            finish_current()
            current = {
                "index": int(subimage.group(1)),
                "name": "",
                "channels": [],
                "pixel_type": subimage.group(2),
            }
            continue

        if current is None:
            continue

        if channel_parts and ":" in line and "channel list:" not in line:
            flush_channels()

        name_match = re.match(r'\s*name:\s*"([^"]*)"', line)
        if name_match:
            current["name"] = name_match.group(1).strip()
            continue

        if "channel list:" in line:
            channel_parts = [line.split("channel list:", 1)[1].strip()]
            continue

        if channel_parts:
            if re.match(r"\s+[A-Za-z0-9_.]+", line):
                channel_parts.append(line.strip())
            else:
                flush_channels()

    finish_current()
    return planes


def run_command(
    command: Sequence[str],
    log_path: Path,
    timeout: int = 300,
) -> RunResult:
    start = time.perf_counter()
    proc = subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    seconds = time.perf_counter() - start
    log_text = "\n".join(
        [
            "$ {}".format(subprocess.list2cmdline(list(command))),
            "",
            "returncode={}".format(proc.returncode),
            "seconds={:.3f}".format(seconds),
            "",
            proc.stdout or "",
            proc.stderr or "",
        ]
    )
    log_path.write_text(log_text, encoding="utf-8")
    result = RunResult(
        command=list(command),
        returncode=proc.returncode,
        seconds=seconds,
        log_path=str(log_path),
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "Command failed with exit code {}. See {}".format(
                proc.returncode, log_path
            )
        )
    return result


def write_step_log(
    command: Sequence[str],
    log_path: Path,
    *,
    seconds: float,
    message: str,
    returncode: int = 0,
) -> RunResult:
    log_text = "\n".join(
        [
            "$ {}".format(subprocess.list2cmdline(list(command))),
            "",
            "returncode={}".format(returncode),
            "seconds={:.3f}".format(seconds),
            "",
            message,
        ]
    )
    log_path.write_text(log_text, encoding="utf-8")
    result = RunResult(
        command=list(command),
        returncode=returncode,
        seconds=seconds,
        log_path=str(log_path),
    )
    if returncode != 0:
        raise RuntimeError(
            "Step failed with exit code {}. See {}".format(returncode, log_path)
        )
    return result


def load_oiio(oiiotool: Optional[Path] = None):
    if os.name == "nt" and oiiotool:
        add_dll_directory = getattr(os, "add_dll_directory", None)
        if add_dll_directory:
            try:
                add_dll_directory(str(oiiotool.parent))
            except OSError:
                pass
    try:
        import OpenImageIO as oiio  # type: ignore
    except Exception:
        return None
    return oiio


def inspect_planes(oiiotool: Path, source: Path, log_dir: Path) -> List[PlaneInfo]:
    result = run_command(
        [str(oiiotool), "--info", "-v", "-a", str(source)],
        log_dir / "inspect_input.log",
        timeout=180,
    )
    text = Path(result.log_path).read_text(encoding="utf-8", errors="replace")
    marker = "\n\nreturncode="
    payload = text.split(marker, 1)[-1]
    planes = parse_oiiotool_info(payload)
    if not planes:
        raise RuntimeError("No multipart EXR subimages were detected in {}".format(source))
    return planes


def inspect_planes_oiio(oiio, source: Path) -> List[PlaneInfo]:
    image_input = oiio.ImageInput.open(str(source))
    if not image_input:
        raise RuntimeError(
            "Could not open {} with OpenImageIO: {}".format(
                source, oiio.geterror()
            )
        )
    try:
        planes = []
        index = 0
        while image_input.seek_subimage(index, 0):
            spec = image_input.spec()
            name = (
                spec.get_string_attribute("oiio:subimagename")
                or spec.get_string_attribute("name")
                or "subimage_{}".format(index)
            )
            planes.append(
                PlaneInfo(
                    index=index,
                    name=name,
                    channels=list(spec.channelnames),
                    pixel_type=str(spec.format),
                )
            )
            index += 1
    finally:
        image_input.close()
    if not planes:
        raise RuntimeError("No multipart EXR subimages were detected in {}".format(source))
    return planes


def find_plane(planes: Sequence[PlaneInfo], name: Optional[str]) -> Optional[PlaneInfo]:
    if not name:
        return None
    wanted = name.strip().lower()
    for plane in planes:
        if plane.name.lower() == wanted:
            return plane
    return None


def is_auto_denoisable_aov(
    plane: PlaneInfo,
    *,
    beauty: PlaneInfo,
    albedo: Optional[PlaneInfo],
    normal: Optional[PlaneInfo],
) -> bool:
    name = plane.name.lower()
    if plane.index == beauty.index:
        return False
    if albedo and plane.index == albedo.index:
        return False
    if normal and plane.index == normal.index:
        return False
    if plane.channel_count not in (3, 4):
        return False
    base = name.rsplit(".", 1)[-1]
    if base in RAW_AOV_NAMES:
        return False
    if any(token in name for token in ("crypto", "depth", "mask", "id")):
        return False
    return True


def required_extraction_planes(
    *,
    beauty: PlaneInfo,
    albedo: Optional[PlaneInfo],
    normal: Optional[PlaneInfo],
    denoise_aovs: Sequence[PlaneInfo],
) -> List[PlaneInfo]:
    required = []
    seen = set()

    def add(plane: Optional[PlaneInfo]) -> None:
        if plane is None or plane.index in seen:
            return
        seen.add(plane.index)
        required.append(plane)

    add(beauty)
    add(albedo)
    if albedo:
        add(normal)
    for plane in denoise_aovs:
        add(plane)
    return required


def extract_planes(
    oiiotool: Path,
    source: Path,
    planes: Sequence[PlaneInfo],
    extract_dir: Path,
    log_dir: Path,
) -> Tuple[Dict[int, Path], RunResult]:
    extracted = {}
    for plane in planes:
        out = extract_dir / "{:03d}_{}.exr".format(plane.index, safe_stem(plane.name))
        extracted[plane.index] = out
    result = run_command(
        build_extract_command(oiiotool, source, planes, extracted),
        log_dir / "extract_all.log",
        timeout=600,
    )
    return extracted, result


def build_extract_command(
    oiiotool: Path,
    source: Path,
    planes: Sequence[PlaneInfo],
    extracted: Dict[int, Path],
) -> List[str]:
    command = [str(oiiotool)]
    for plane in planes:
        command.extend(
            [
                str(source),
                "--subimage",
                str(plane.index),
                "-o",
                str(extracted[plane.index]),
            ]
        )
    return command


def extract_planes_oiio(
    oiio,
    source: Path,
    planes: Sequence[PlaneInfo],
    extract_dir: Path,
    log_dir: Path,
) -> Tuple[Dict[int, Path], RunResult]:
    command = [
        "python-oiio",
        "extract",
        str(source),
        "{} subimages".format(len(planes)),
    ]
    start = time.perf_counter()
    extracted = {}
    messages = []
    try:
        for plane in planes:
            out = extract_dir / "{:03d}_{}.exr".format(
                plane.index, safe_stem(plane.name)
            )
            buf = read_imagebuf(oiio, source, plane.index)
            if not buf.write(str(out)):
                raise RuntimeError(
                    "Could not write extracted plane {}: {}".format(
                        plane.name, buf.geterror()
                    )
                )
            extracted[plane.index] = out
            messages.append("{} -> {}".format(plane.name, out))
    except Exception as exc:
        seconds = time.perf_counter() - start
        write_step_log(
            command,
            log_dir / "extract_all_oiio.log",
            seconds=seconds,
            message="\n".join(messages + [repr(exc)]),
            returncode=1,
        )
    seconds = time.perf_counter() - start
    result = write_step_log(
        command,
        log_dir / "extract_all_oiio.log",
        seconds=seconds,
        message="\n".join(messages),
    )
    return extracted, result


def build_denoiser_command(
    denoiser: Path,
    beauty_input: Path,
    beauty_output: Path,
    *,
    albedo_input: Optional[Path],
    normal_input: Optional[Path],
    aov_input: Optional[Path] = None,
    aov_output: Optional[Path] = None,
    verbosity: int = 1,
) -> List[str]:
    command = [
        str(denoiser),
        "-v",
        str(verbosity),
        "-i",
        str(beauty_input),
        "-o",
        str(beauty_output),
    ]
    if albedo_input:
        command.extend(["-a", str(albedo_input)])
        if normal_input:
            command.extend(["-n", str(normal_input)])
    if aov_input or aov_output:
        if not aov_input or not aov_output:
            raise ValueError("aov_input and aov_output must be provided together")
        command.extend(["-aov0", str(aov_input), "-oaov0", str(aov_output)])
    return command


def denoise_planes(
    denoiser: Path,
    extracted: Dict[int, Path],
    beauty: PlaneInfo,
    albedo: Optional[PlaneInfo],
    normal: Optional[PlaneInfo],
    denoise_aovs: Sequence[PlaneInfo],
    output_dir: Path,
    log_dir: Path,
    verbosity: int,
) -> Tuple[Path, Dict[int, Path], List[RunResult]]:
    denoised_beauty = output_dir / "{:03d}_{}_denoised.exr".format(
        beauty.index, safe_stem(beauty.name)
    )
    denoised_aov_paths = {}
    results = []
    albedo_path = extracted.get(albedo.index) if albedo else None
    normal_path = extracted.get(normal.index) if normal else None
    if denoise_aovs:
        first = denoise_aovs[0]
        first_output = output_dir / "{:03d}_{}_denoised.exr".format(
            first.index, safe_stem(first.name)
        )
        results.append(
            run_command(
                build_denoiser_command(
                    denoiser,
                    extracted[beauty.index],
                    denoised_beauty,
                    albedo_input=albedo_path,
                    normal_input=normal_path,
                    aov_input=extracted[first.index],
                    aov_output=first_output,
                    verbosity=verbosity,
                ),
                log_dir
                / "denoise_beauty_and_{:03d}_{}.log".format(
                    first.index, safe_stem(first.name)
                ),
                timeout=600,
            )
        )
        denoised_aov_paths[first.index] = first_output

        for plane in denoise_aovs[1:]:
            aov_output = output_dir / "{:03d}_{}_denoised.exr".format(
                plane.index, safe_stem(plane.name)
            )
            scratch_beauty = output_dir / "_scratch_{}_beauty.exr".format(
                safe_stem(plane.name)
            )
            results.append(
                run_command(
                    build_denoiser_command(
                        denoiser,
                        extracted[beauty.index],
                        scratch_beauty,
                        albedo_input=albedo_path,
                        normal_input=normal_path,
                        aov_input=extracted[plane.index],
                        aov_output=aov_output,
                        verbosity=verbosity,
                    ),
                    log_dir
                    / "denoise_aov_{:03d}_{}.log".format(
                        plane.index, safe_stem(plane.name)
                    ),
                    timeout=600,
                )
            )
            denoised_aov_paths[plane.index] = aov_output
    else:
        results.append(
            run_command(
                build_denoiser_command(
                    denoiser,
                    extracted[beauty.index],
                    denoised_beauty,
                    albedo_input=albedo_path,
                    normal_input=normal_path,
                    verbosity=verbosity,
                ),
                log_dir / "denoise_beauty.log",
                timeout=600,
            )
        )

    return denoised_beauty, denoised_aov_paths, results


def recompose(
    oiiotool: Path,
    source: Path,
    planes: Sequence[PlaneInfo],
    denoised_beauty: Path,
    denoised_aovs: Dict[int, Path],
    beauty: PlaneInfo,
    output: Path,
    log_dir: Path,
) -> RunResult:
    output.parent.mkdir(parents=True, exist_ok=True)
    return run_command(
        build_recompose_command(
            oiiotool,
            source,
            planes,
            denoised_beauty,
            denoised_aovs,
            beauty,
            output,
        ),
        log_dir / "recompose.log",
        timeout=600,
    )


def recompose_oiio(
    oiio,
    source: Path,
    planes: Sequence[PlaneInfo],
    denoised_beauty: Path,
    denoised_aovs: Dict[int, Path],
    beauty: PlaneInfo,
    output: Path,
    log_dir: Path,
) -> RunResult:
    command = [
        "python-oiio",
        "recompose",
        str(source),
        str(output),
        "{} subimages".format(len(planes)),
    ]
    start = time.perf_counter()
    messages = []
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        bufs = []
        for plane in planes:
            source_spec = read_subimage_spec(oiio, source, plane.index)
            if plane.index == beauty.index:
                buf = read_image_as_spec(oiio, denoised_beauty, source_spec)
                messages.append("{} <- {}".format(plane.name, denoised_beauty))
            elif plane.index in denoised_aovs:
                buf = read_image_as_spec(oiio, denoised_aovs[plane.index], source_spec)
                messages.append("{} <- {}".format(plane.name, denoised_aovs[plane.index]))
            else:
                buf = read_imagebuf(oiio, source, plane.index)
                messages.append("{} <- source subimage {}".format(plane.name, plane.index))
            bufs.append(buf)

        write_multipart_imagebufs(oiio, output, bufs)
    except Exception as exc:
        seconds = time.perf_counter() - start
        write_step_log(
            command,
            log_dir / "recompose_oiio.log",
            seconds=seconds,
            message="\n".join(messages + [repr(exc)]),
            returncode=1,
        )
    seconds = time.perf_counter() - start
    return write_step_log(
        command,
        log_dir / "recompose_oiio.log",
        seconds=seconds,
        message="\n".join(messages),
    )


def read_imagebuf(oiio, filename: Path, subimage: int):
    buf = oiio.ImageBuf(str(filename))
    if not buf.read(subimage, 0, True):
        raise RuntimeError(
            "Could not read subimage {} from {}: {}".format(
                subimage, filename, buf.geterror()
            )
        )
    return buf


def read_subimage_spec(oiio, filename: Path, subimage: int):
    image_input = oiio.ImageInput.open(str(filename))
    if not image_input:
        raise RuntimeError(
            "Could not open {} with OpenImageIO: {}".format(
                filename, oiio.geterror()
            )
        )
    try:
        if not image_input.seek_subimage(subimage, 0):
            raise RuntimeError("Subimage {} not found in {}".format(subimage, filename))
        return image_input.spec().copy()
    finally:
        image_input.close()


def read_image_as_spec(oiio, filename: Path, output_spec):
    image_input = oiio.ImageInput.open(str(filename))
    if not image_input:
        raise RuntimeError(
            "Could not open {} with OpenImageIO: {}".format(
                filename, oiio.geterror()
            )
        )
    try:
        pixels = image_input.read_image(output_spec.format)
        if pixels is None:
            raise RuntimeError(
                "Could not read {} with OpenImageIO: {}".format(
                    filename, image_input.geterror()
                )
            )
    finally:
        image_input.close()

    expected_channels = output_spec.nchannels
    if len(pixels.shape) != 3 or pixels.shape[2] != expected_channels:
        raise RuntimeError(
            "{} has {} channels, expected {}".format(
                filename,
                pixels.shape[2] if len(pixels.shape) == 3 else pixels.shape,
                expected_channels,
            )
        )
    buf = oiio.ImageBuf(output_spec.copy(), True)
    if not buf.set_pixels(buf.roi, pixels):
        raise RuntimeError("Could not set pixels for {}: {}".format(filename, buf.geterror()))
    return buf


def write_multipart_imagebufs(oiio, output: Path, bufs: Sequence[object]) -> None:
    if not bufs:
        raise RuntimeError("No image buffers to write")
    image_output = oiio.ImageOutput.create(str(output))
    if not image_output:
        raise RuntimeError(
            "Could not create {} with OpenImageIO: {}".format(
                output, oiio.geterror()
            )
        )
    specs = tuple(buf.spec() for buf in bufs)
    try:
        if not image_output.open(str(output), specs):
            raise RuntimeError(
                "Could not open {} with OpenImageIO: {}".format(
                    output, image_output.geterror()
                )
            )
        for index, buf in enumerate(bufs):
            if index > 0 and not image_output.open(
                str(output), specs[index], "AppendSubimage"
            ):
                raise RuntimeError(
                    "Could not append subimage {} to {}: {}".format(
                        index, output, image_output.geterror()
                    )
                )
            if not buf.write(image_output):
                raise RuntimeError(
                    "Could not write subimage {} to {}: {}".format(
                        index, output, buf.geterror() or image_output.geterror()
                    )
                )
    finally:
        image_output.close()


def build_recompose_command(
    oiiotool: Path,
    source: Path,
    planes: Sequence[PlaneInfo],
    denoised_beauty: Path,
    denoised_aovs: Dict[int, Path],
    beauty: PlaneInfo,
    output: Path,
) -> List[str]:
    command = [str(oiiotool)]
    for plane in planes:
        if plane.index == beauty.index:
            command.append(str(denoised_beauty))
        elif plane.index in denoised_aovs:
            command.append(str(denoised_aovs[plane.index]))
        else:
            command.extend([str(source), "--subimage", str(plane.index)])
    command.extend(["--siappendall", "-o", str(output)])
    return command


def write_manifest(
    manifest_path: Path,
    *,
    source: Path,
    output: Path,
    planes: Sequence[PlaneInfo],
    beauty: PlaneInfo,
    albedo: Optional[PlaneInfo],
    normal: Optional[PlaneInfo],
    denoise_aovs: Sequence[PlaneInfo],
    extracted_planes: Sequence[PlaneInfo],
    extract_result: RunResult,
    denoise_results: Sequence[RunResult],
    recompose_result: RunResult,
    image_io_backend: str,
) -> None:
    manifest = {
        "source": str(source),
        "output": str(output),
        "beauty": asdict(beauty),
        "albedo": asdict(albedo) if albedo else None,
        "normal": asdict(normal) if normal else None,
        "denoised_aovs": [asdict(plane) for plane in denoise_aovs],
        "plane_count": len(planes),
        "planes": [asdict(plane) for plane in planes],
        "extracted_plane_count": len(extracted_planes),
        "extracted_planes": [asdict(plane) for plane in extracted_planes],
        "image_io_backend": image_io_backend,
        "extract_run": asdict(extract_result),
        "denoise_runs": [asdict(result) for result in denoise_results],
        "recompose_run": asdict(recompose_result),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def detect_oiiotool() -> Optional[Path]:
    try:
        from h_denoise_utils.discovery.houdini import detect_default_oiiotool

        value = detect_default_oiiotool()
        if value:
            path = Path(value)
            if path.is_file():
                return path
    except Exception:
        return None
    return None


def resolve_tool(path: Optional[str], env_name: str, detector=None) -> Optional[Path]:
    candidates = [path, os.environ.get(env_name)]
    for candidate in candidates:
        if candidate:
            resolved = Path(candidate)
            if resolved.is_file():
                return resolved
    if detector:
        return detector()
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prototype compiled OptiX multilayer EXR AOV wrapper."
    )
    parser.add_argument("--input", required=True, help="Input multipart EXR.")
    parser.add_argument("--output", required=True, help="Output multipart EXR.")
    parser.add_argument("--denoiser", help="Path to compiled Denoiser.exe.")
    parser.add_argument("--oiiotool", help="Path to Houdini hoiiotool.exe.")
    parser.add_argument("--beauty", default="C", help="Beauty subimage name.")
    parser.add_argument("--albedo", default="albedo", help="Albedo guide name.")
    parser.add_argument("--normal", default="N", help="Normal guide name.")
    parser.add_argument(
        "--denoise-aov",
        action="append",
        default=[],
        help="AOV name to denoise. May be repeated or comma-separated.",
    )
    parser.add_argument(
        "--auto-denoise-rgb-aovs",
        action="store_true",
        help="Denoise all non-raw 3/4 channel AOVs detected by the prototype.",
    )
    parser.add_argument(
        "--work-dir",
        help="Optional work directory. Defaults to a temp directory.",
    )
    parser.add_argument(
        "--keep-work",
        action="store_true",
        help="Keep generated extraction, denoise, and log files.",
    )
    parser.add_argument(
        "--verbosity",
        type=int,
        default=1,
        choices=(0, 1, 2),
        help="Denoiser verbosity.",
    )
    parser.add_argument(
        "--image-io-backend",
        choices=("auto", "oiio", "hoiiotool"),
        default="auto",
        help="Image I/O backend for EXR inspect, extract, and recomposition.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    source = Path(args.input)
    output = Path(args.output)
    if not source.is_file():
        parser.error("Input EXR does not exist: {}".format(source))

    denoiser = resolve_tool(args.denoiser, "HDU_OPTIX_DENOISER")
    if not denoiser:
        parser.error("Denoiser.exe not found; pass --denoiser or HDU_OPTIX_DENOISER")

    oiiotool = resolve_tool(args.oiiotool, "HDU_OIIOTOOL", detector=detect_oiiotool)
    oiio = None
    if args.image_io_backend in ("auto", "oiio"):
        oiio = load_oiio(oiiotool)
        if args.image_io_backend == "oiio" and oiio is None:
            parser.error(
                "OpenImageIO Python bindings are not importable in this Python. "
                "Use Houdini's Python or choose --image-io-backend hoiiotool."
            )
    image_io_backend = "oiio" if oiio is not None else "hoiiotool"
    if image_io_backend == "hoiiotool" and not oiiotool:
        parser.error("hoiiotool.exe not found; pass --oiiotool or HDU_OIIOTOOL")

    owns_work_dir = args.work_dir is None
    work_dir = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(prefix="hdu_optix_aov_"))
    extract_dir = work_dir / "extract"
    denoise_dir = work_dir / "denoise"
    log_dir = work_dir / "logs"
    for path in (extract_dir, denoise_dir, log_dir):
        path.mkdir(parents=True, exist_ok=True)

    try:
        if image_io_backend == "oiio":
            planes = inspect_planes_oiio(oiio, source)
        else:
            planes = inspect_planes(oiiotool, source, log_dir)
        beauty = find_plane(planes, args.beauty)
        if not beauty:
            raise RuntimeError("Beauty plane '{}' was not found".format(args.beauty))

        albedo = find_plane(planes, args.albedo)
        normal = find_plane(planes, args.normal)
        selected_names = parse_plane_list(args.denoise_aov)
        selected_planes = []
        for name in selected_names:
            plane = find_plane(planes, name)
            if not plane:
                raise RuntimeError("Requested AOV '{}' was not found".format(name))
            selected_planes.append(plane)

        if args.auto_denoise_rgb_aovs:
            selected_indexes = {plane.index for plane in selected_planes}
            for plane in planes:
                if plane.index in selected_indexes:
                    continue
                if is_auto_denoisable_aov(
                    plane,
                    beauty=beauty,
                    albedo=albedo,
                    normal=normal,
                ):
                    selected_planes.append(plane)

        extracted_planes = required_extraction_planes(
            beauty=beauty,
            albedo=albedo,
            normal=normal,
            denoise_aovs=selected_planes,
        )
        if image_io_backend == "oiio":
            extracted, extract_result = extract_planes_oiio(
                oiio, source, extracted_planes, extract_dir, log_dir
            )
        else:
            extracted, extract_result = extract_planes(
                oiiotool, source, extracted_planes, extract_dir, log_dir
            )
        denoised_beauty, denoised_aovs, denoise_results = denoise_planes(
            denoiser,
            extracted,
            beauty,
            albedo,
            normal,
            selected_planes,
            denoise_dir,
            log_dir,
            args.verbosity,
        )
        if image_io_backend == "oiio":
            recompose_result = recompose_oiio(
                oiio,
                source,
                planes,
                denoised_beauty,
                denoised_aovs,
                beauty,
                output,
                log_dir,
            )
        else:
            recompose_result = recompose(
                oiiotool,
                source,
                planes,
                denoised_beauty,
                denoised_aovs,
                beauty,
                output,
                log_dir,
            )
        write_manifest(
            work_dir / "manifest.json",
            source=source,
            output=output,
            planes=planes,
            beauty=beauty,
            albedo=albedo,
            normal=normal,
            denoise_aovs=selected_planes,
            extracted_planes=extracted_planes,
            extract_result=extract_result,
            denoise_results=denoise_results,
            recompose_result=recompose_result,
            image_io_backend=image_io_backend,
        )
        print("Wrote {}".format(output))
        print("Manifest {}".format(work_dir / "manifest.json"))
        print("Work dir {}".format(work_dir))
        return 0
    finally:
        if owns_work_dir and not args.keep_work:
            shutil.rmtree(str(work_dir), ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
