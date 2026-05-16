"""Tests for the isolated OptiX multilayer AOV prototype."""

from pathlib import Path

from tools.optix_multilayer_aov import (
    PlaneInfo,
    build_denoiser_command,
    build_extract_command,
    build_recompose_command,
    is_auto_denoisable_aov,
    parse_oiiotool_info,
    parse_plane_list,
    required_extraction_planes,
)


def test_parse_oiiotool_info_reads_subimages_and_channels():
    text = """
 subimage  0: 1280 x  720, 4 channel, half openexr
    channel list: R, G, B, A
    name: "C"
 subimage  1: 1280 x  720, 3 channel, half openexr
    channel list: albedo.R, albedo.G, albedo.B
    name: "albedo"
 subimage  2: 1280 x  720, 3 channel, float openexr
    channel list: indirectdiffuse.R, indirectdiffuse.G,
                  indirectdiffuse.B
    name: "indirectdiffuse"
"""
    planes = parse_oiiotool_info(text)

    assert [plane.name for plane in planes] == ["C", "albedo", "indirectdiffuse"]
    assert planes[0].channels == ["R", "G", "B", "A"]
    assert planes[1].pixel_type == "half"
    assert planes[2].channels == [
        "indirectdiffuse.R",
        "indirectdiffuse.G",
        "indirectdiffuse.B",
    ]


def test_parse_oiiotool_info_does_not_fold_metadata_into_channels():
    text = """
 subimage  0: 1280 x  720, 4 channel, half openexr
    channel list: R, G, B, A
    name: "C"
    compression: "zips"
    typeSemantics: "color"
"""
    planes = parse_oiiotool_info(text)

    assert planes[0].channels == ["R", "G", "B", "A"]


def test_parse_plane_list_splits_commas_and_preserves_order():
    assert parse_plane_list(["directdiffuse, indirectdiffuse", "directdiffuse"]) == [
        "directdiffuse",
        "indirectdiffuse",
    ]


def test_build_denoiser_command_includes_guides_and_single_aov():
    command = build_denoiser_command(
        Path("Denoiser.exe"),
        Path("C.exr"),
        Path("C_denoised.exr"),
        albedo_input=Path("albedo.exr"),
        normal_input=Path("N.exr"),
        aov_input=Path("directdiffuse.exr"),
        aov_output=Path("directdiffuse_denoised.exr"),
        verbosity=2,
    )

    assert command == [
        "Denoiser.exe",
        "-v",
        "2",
        "-i",
        "C.exr",
        "-o",
        "C_denoised.exr",
        "-a",
        "albedo.exr",
        "-n",
        "N.exr",
        "-aov0",
        "directdiffuse.exr",
        "-oaov0",
        "directdiffuse_denoised.exr",
    ]


def test_build_extract_command_batches_all_subimages():
    planes = [
        PlaneInfo(index=0, name="C", channels=["R", "G", "B", "A"]),
        PlaneInfo(index=1, name="albedo", channels=["albedo.R", "albedo.G", "albedo.B"]),
    ]
    extracted = {
        0: Path("000_C.exr"),
        1: Path("001_albedo.exr"),
    }

    assert build_extract_command(
        Path("hoiiotool.exe"),
        Path("source.exr"),
        planes,
        extracted,
    ) == [
        "hoiiotool.exe",
        "source.exr",
        "--subimage",
        "0",
        "-o",
        "000_C.exr",
        "source.exr",
        "--subimage",
        "1",
        "-o",
        "001_albedo.exr",
    ]


def test_required_extraction_planes_uses_only_denoiser_inputs():
    beauty = PlaneInfo(index=0, name="C", channels=["R", "G", "B", "A"])
    albedo = PlaneInfo(index=1, name="albedo", channels=["albedo.R", "albedo.G", "albedo.B"])
    depth = PlaneInfo(index=2, name="depth", channels=["depth.z"])
    diffuse = PlaneInfo(index=3, name="directdiffuse", channels=["R", "G", "B"])
    normal = PlaneInfo(index=4, name="N", channels=["N.x", "N.y", "N.z"])

    required = required_extraction_planes(
        beauty=beauty,
        albedo=albedo,
        normal=normal,
        denoise_aovs=[diffuse],
    )

    assert [plane.name for plane in required] == ["C", "albedo", "N", "directdiffuse"]
    assert depth not in required


def test_build_recompose_command_reuses_source_for_untouched_planes():
    beauty = PlaneInfo(index=0, name="C", channels=["R", "G", "B", "A"])
    albedo = PlaneInfo(index=1, name="albedo", channels=["albedo.R", "albedo.G", "albedo.B"])
    diffuse = PlaneInfo(index=2, name="directdiffuse", channels=["R", "G", "B"])

    assert build_recompose_command(
        Path("hoiiotool.exe"),
        Path("source.exr"),
        [beauty, albedo, diffuse],
        Path("C_denoised.exr"),
        {2: Path("directdiffuse_denoised.exr")},
        beauty,
        Path("output.exr"),
    ) == [
        "hoiiotool.exe",
        "C_denoised.exr",
        "source.exr",
        "--subimage",
        "1",
        "directdiffuse_denoised.exr",
        "--siappendall",
        "-o",
        "output.exr",
    ]


def test_auto_denoisable_aov_skips_raw_and_guide_planes():
    beauty = PlaneInfo(index=0, name="C", channels=["R", "G", "B", "A"])
    albedo = PlaneInfo(index=1, name="albedo", channels=["albedo.R", "albedo.G", "albedo.B"])
    normal = PlaneInfo(index=2, name="N", channels=["N.x", "N.y", "N.z"])
    diffuse = PlaneInfo(
        index=3,
        name="directdiffuse",
        channels=["directdiffuse.R", "directdiffuse.G", "directdiffuse.B"],
    )
    depth = PlaneInfo(index=4, name="depth", channels=["depth.z"])

    assert is_auto_denoisable_aov(diffuse, beauty=beauty, albedo=albedo, normal=normal)
    assert not is_auto_denoisable_aov(beauty, beauty=beauty, albedo=albedo, normal=normal)
    assert not is_auto_denoisable_aov(albedo, beauty=beauty, albedo=albedo, normal=normal)
    assert not is_auto_denoisable_aov(normal, beauty=beauty, albedo=albedo, normal=normal)
    assert not is_auto_denoisable_aov(depth, beauty=beauty, albedo=albedo, normal=normal)
