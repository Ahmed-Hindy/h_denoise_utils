"""AOV validation and filtering utilities."""

import logging

from .exr_inspector import list_exr_planes

logger = logging.getLogger(__name__)


def validate_aov_exists(exr_path, aov_name, oiiotool_path=None):
    # type: (str, Optional[str], Optional[str]) -> bool
    """Check if a specific AOV exists in an EXR file (case-insensitive).

    Args:
        exr_path: Path to EXR file
        aov_name: AOV name to check
        oiiotool_path: Optional path to oiiotool

    Returns:
        True if AOV exists, False otherwise
    """
    if not aov_name:
        return False

    available_planes = list_exr_planes(exr_path, oiiotool_path)
    if not available_planes:
        return False

    aov_lower = aov_name.strip().lower()
    available_lower = {p.lower() for p in available_planes}  # type: Set[str]

    return aov_lower in available_lower


def filter_existing_aovs(exr_path, **aov_params):
    # type: (str, **Any) -> Dict[str, Any]
    """Filter AOVs to only include those that exist in the EXR file.

    Works with any AOV names from any render engine (Arnold, Karma, etc.),
    supporting both multipart and layered EXR formats.

    Args:
        exr_path: Path to EXR file to check
        **aov_params: AOV specifications as keyword arguments
            - Single AOVs: normal_plane="N", albedo_plane="albedo"
            - List AOVs: aovs_to_denoise=["diffuse", "specular"]

    Returns:
        Dict with same keys as input, missing AOVs set to None or removed from lists

    Examples:
        >>> result = filter_existing_aovs(
        ...     "/path/to/file.exr",
        ...     normal_plane="N",
        ...     aovs_to_denoise=["beauty", "diffuse", "specular"]
        ... )
        >>> # Returns: {'normal_plane': 'N', 'aovs_to_denoise': ['beauty', 'diffuse']}
    """
    available_planes = list_exr_planes(exr_path)
    if not available_planes:
        logger.warning(
            "Could not detect planes in %s, proceeding with user-specified AOVs",
            exr_path,
        )
        return aov_params

    # Build case-insensitive lookup
    available_lower = {p.lower(): p for p in available_planes}

    validated = {}  # type: Dict[str, Any]

    for key, value in aov_params.items():
        if value is None:
            validated[key] = None
            continue

        # Handle list of AOVs
        if isinstance(value, list):
            validated_list = []  # type: List[str]
            for aov in value:
                if not aov:
                    continue
                aov_lower = str(aov).strip().lower()
                if aov_lower in available_lower:
                    validated_list.append(aov)
                else:
                    logger.info("AOV '%s' not found in EXR, will not be used", aov)

            validated[key] = validated_list if validated_list else None

        # Handle single AOV string
        elif isinstance(value, str):
            if not value.strip():
                validated[key] = None
                continue

            aov_lower = value.strip().lower()
            if aov_lower in available_lower:
                validated[key] = value
            else:
                logger.info(
                    "AOV '%s' (parameter '%s') not found in EXR, will be skipped",
                    value,
                    key,
                )
                validated[key] = None
        else:
            # Pass through other types unchanged
            validated[key] = value

    return validated
