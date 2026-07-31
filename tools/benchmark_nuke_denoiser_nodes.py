"""Benchmark live OptiX and OIDN Nuke nodes at representative resolutions."""

from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path

import nuke

OUTPUT_ROOT = Path(tempfile.gettempdir()) / "hdu-nuke-benchmark"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def _constant(name: str, color: list[float], format_name: str) -> nuke.Node:
    """Create an animated constant that forces evaluation on every frame."""
    node = nuke.nodes.Constant(name=name)
    node["format"].setValue(format_name)
    node["color"].setValue(color)
    node["color"].setAnimated()
    for frame in range(1, 5):
        node["color"].setValueAt(color[0] + frame * 0.01, frame, 0)
    return node


def _writer(node: nuke.Node, stem: str) -> nuke.Node:
    """Create an EXR writer with compression disabled when supported."""
    writer = nuke.nodes.Write(name=f"WRITE_{stem.replace('-', '_')}")
    writer.setInput(0, node)
    writer["file_type"].setValue("exr")
    writer["channels"].setValue("rgba")
    if "compression" in writer.knobs():
        try:
            writer["compression"].setValue("none")
        except (ValueError, RuntimeError):
            pass
    writer["file"].setValue((OUTPUT_ROOT / f"{stem}.%04d.exr").as_posix())
    return writer


def _measure(writer: nuke.Node, stem: str) -> dict[str, object]:
    """Warm up once, then time three animated frames."""
    paths = [OUTPUT_ROOT / f"{stem}.{frame:04d}.exr" for frame in range(1, 5)]
    for path in paths:
        path.unlink(missing_ok=True)
    nuke.execute(writer, 1, 1)
    samples: list[float] = []
    sizes: list[int] = []
    for frame, path in zip(range(2, 5), paths[1:], strict=True):
        started = time.perf_counter()
        nuke.execute(writer, frame, frame)
        samples.append(time.perf_counter() - started)
        sizes.append(path.stat().st_size)
    return {
        "samples_seconds": [round(value, 4) for value in samples],
        "median_seconds": round(statistics.median(samples), 4),
        "mean_seconds": round(statistics.mean(samples), 4),
        "output_megabytes": round(statistics.mean(sizes) / (1024 * 1024), 2),
    }


def _benchmark_resolution(width: int, height: int) -> dict[str, object]:
    """Benchmark source writing and guided denoiser configurations."""
    nuke.scriptClear()
    format_name = nuke.addFormat(
        f"{width} {height} 1.0 HDenoiseBenchmark{width}x{height}"
    ).name()
    beauty = _constant("BEAUTY", [0.25, 0.5, 0.75, 1.0], format_name)
    albedo = _constant("ALBEDO", [0.5, 0.5, 0.5, 1.0], format_name)
    normal = _constant("NORMAL", [0.0, 0.0, 1.0, 1.0], format_name)

    results: dict[str, dict[str, object]] = {}
    baseline_stem = f"baseline-{width}x{height}"
    results["baseline_write"] = _measure(_writer(beauty, baseline_stem), baseline_stem)

    optix = nuke.createNode("HOptixDenoise", inpanel=False)
    optix.setInput(0, beauty)
    optix.setInput(1, albedo)
    optix.setInput(2, normal)
    optix["tile_size"].setValue("1024 x 1024")
    optix["passthrough_on_error"].setValue(False)
    optix_stem = f"optix-{width}x{height}"
    results["optix_guided"] = _measure(_writer(optix, optix_stem), optix_stem)

    for quality in ("Fast", "Balanced", "High"):
        oidn = nuke.createNode("HOidnDenoise", inpanel=False)
        oidn.setInput(0, beauty)
        oidn.setInput(1, albedo)
        oidn.setInput(2, normal)
        oidn["quality"].setValue(quality)
        oidn["passthrough_on_error"].setValue(False)
        slug = quality.lower()
        stem = f"oidn-{slug}-{width}x{height}"
        results[f"oidn_{slug}_guided"] = _measure(_writer(oidn, stem), stem)

    baseline = float(results["baseline_write"]["median_seconds"])
    for value in results.values():
        value["estimated_denoiser_overhead_seconds"] = round(
            max(0.0, float(value["median_seconds"]) - baseline),
            4,
        )
    return results


def main() -> None:
    """Run 1080p and UHD benchmarks and emit JSON."""
    result = {
        "nuke": nuke.NUKE_VERSION_STRING,
        "gpu": "CUDA device 0",
        "method": "one warm-up frame plus median of three animated-frame EXR renders",
        "resolutions": {
            "1920x1080": _benchmark_resolution(1920, 1080),
            "3840x2160": _benchmark_resolution(3840, 2160),
        },
    }
    path = OUTPUT_ROOT / "benchmark.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(path)


if __name__ == "__main__":
    main()
