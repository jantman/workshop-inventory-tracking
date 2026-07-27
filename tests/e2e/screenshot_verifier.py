"""
Screenshot Verifier

Cross-checks the three things that must agree about documentation
screenshots:

* ``tests/e2e/screenshot_config.yaml`` -- the declared set of captures, each
  tagged ``capture_status: required | conditional | planned``
* ``docs/images/screenshots/metadata.json`` -- the manifest a generation run
  writes, recording what that run actually captured
* the PNGs on disk under ``docs/images/screenshots/``

plus the long standing quality gate (at least one PNG, every PNG under 500 KB
and in RGB/RGBA mode).

Run it as ``python -m tests.e2e.screenshot_verifier`` (this is what
``nox -s screenshots_verify`` does), or import :func:`verify` for testing.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import yaml
from PIL import Image

from tests.e2e.screenshot_config_loader import ScreenshotConfig, load_screenshot_config


#: Maximum permitted size of a single screenshot, in kilobytes.
MAX_SCREENSHOT_KB = 500

#: Colour modes a documentation screenshot may use.
VALID_IMAGE_MODES = ('RGB', 'RGBA')

#: Legal values of the ``capture_status`` field in ``screenshot_config.yaml``.
VALID_CAPTURE_STATUSES = ('required', 'conditional', 'planned')

#: Capture types :class:`~tests.e2e.screenshot_generator.ScreenshotGenerator`
#: may record.
VALID_CAPTURE_TYPES = ('full_page', 'element', 'viewport')

#: Keys every manifest entry must carry.
REQUIRED_ENTRY_KEYS = ('filename', 'capture_type', 'timestamp')

#: Keys every manifest entry's ``details`` dict must carry (null is allowed).
REQUIRED_DETAIL_KEYS = ('viewport_size', 'hide_selectors')

#: Repository-relative default location of the screenshot tree.
DEFAULT_SCREENSHOT_DIR = (
    Path(__file__).resolve().parents[2] / 'docs' / 'images' / 'screenshots'
)


def verify(screenshot_dir: Path, config: ScreenshotConfig) -> List[str]:
    """
    Verify the screenshot tree against its manifest and configuration.

    This function is pure: it prints nothing and never exits. Callers decide
    what to do with the returned issues.

    Args:
        screenshot_dir: Directory holding the screenshot tree and manifest
        config: Loaded screenshot configuration

    Returns:
        List of human-readable issue strings. Empty means everything agrees.
    """
    issues, _disk_files, _recorded = _collect(screenshot_dir, config)
    return issues


def _collect(screenshot_dir: Path,
             config: ScreenshotConfig) -> Tuple[List[str], List[str], Set[str]]:
    """
    Run every check in a single pass over the tree.

    :func:`verify` exposes only the issue list, but ``main()`` also needs the
    disk listing and the recorded filenames to print its summary. Deriving
    those separately would read the tree a second time and let the summary
    disagree with the issues printed beside it.

    Args:
        screenshot_dir: Directory holding the screenshot tree and manifest
        config: Loaded screenshot configuration

    Returns:
        Tuple of (issues, on-disk relative paths, filenames recorded in the
        manifest).
    """
    screenshot_dir = Path(screenshot_dir)
    issues: List[str] = []

    issues.extend(_verify_config(config))

    disk_files = list_png_files(screenshot_dir)
    issues.extend(_verify_quality(screenshot_dir, disk_files))

    _, root_is_mapping = _raw_screenshots(config)
    if not root_is_mapping:
        # Nothing else in the config can be read from a document that is not a
        # mapping -- including the manifest's own filename.
        return issues, disk_files, set()

    manifest_name, _ = _metadata_filename(config)
    if manifest_name is None:
        # The manifest's own name is unusable; _verify_config already said so.
        return issues, disk_files, set()

    manifest_path = screenshot_dir / manifest_name
    entries, manifest_issues = load_manifest(manifest_path)
    issues.extend(manifest_issues)

    if entries is None:
        # Nothing usable to cross-check against.
        return issues, disk_files, set()

    recorded = manifest_filenames(entries)
    issues.extend(_verify_entries(entries))
    issues.extend(_verify_cross_references(recorded, disk_files, config))

    return issues, disk_files, recorded


def list_png_files(screenshot_dir: Path) -> List[str]:
    """
    List every PNG under ``screenshot_dir`` as a sorted relative posix path.

    Args:
        screenshot_dir: Directory to scan

    Returns:
        Sorted list of paths relative to ``screenshot_dir``
    """
    screenshot_dir = Path(screenshot_dir)
    if not screenshot_dir.is_dir():
        return []
    return sorted(
        path.relative_to(screenshot_dir).as_posix()
        for path in screenshot_dir.glob('**/*')
        if path.is_file() and path.suffix.lower() == '.png'
    )


def load_manifest(manifest_path: Path) -> Tuple[Optional[List], List[str]]:
    """
    Load the screenshot manifest.

    Args:
        manifest_path: Path to ``metadata.json``

    Returns:
        Tuple of (entries, issues). ``entries`` is None when the manifest is
        missing or too broken to inspect, in which case ``issues`` says why.
    """
    manifest_path = Path(manifest_path)
    label = manifest_path.name

    if not manifest_path.exists():
        return None, [f"{label}: manifest not found at {manifest_path}"]

    try:
        with open(manifest_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        # A truncated or binary-clobbered manifest decodes as neither JSON nor
        # UTF-8; both are the same "corrupt manifest" state to the reader.
        return None, [f"{label}: not valid JSON - {exc}"]
    except OSError as exc:
        return None, [f"{label}: could not be read - {exc}"]

    if not isinstance(data, dict):
        return None, [
            f"{label}: expected a JSON object, got {type(data).__name__}"
        ]

    entries = data.get('screenshots')
    if not isinstance(entries, list):
        return None, [f"{label}: missing a 'screenshots' list"]

    return entries, []


def manifest_filenames(entries: List) -> Set[str]:
    """Collect the set of filenames recorded by manifest entries."""
    filenames = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        filename = entry.get('filename')
        # An empty filename names nothing; _verify_entries reports it, and
        # carrying it here would only produce issues with a blank subject.
        if isinstance(filename, str) and filename:
            filenames.add(filename)
    return filenames


def _raw_screenshots(config: ScreenshotConfig) -> Tuple[object, bool]:
    """
    Read the config's raw ``screenshots`` value without raising.

    ``ScreenshotConfig`` checks only that the YAML parsed to something truthy,
    so a file whose document root is a list or a scalar rather than a mapping
    makes every accessor raise ``AttributeError``. Reporting that shape is the
    verifier's job, so it must be able to ask without tracebacking.

    Args:
        config: Loaded screenshot configuration

    Returns:
        Tuple of (raw value, whether the document root is a mapping). The
        value is ``None`` when the root is not a mapping.
    """
    try:
        return config.get_all_screenshots(), True
    except AttributeError:
        return None, False


def _metadata_filename(config: ScreenshotConfig) -> Tuple[Optional[str], List[str]]:
    """
    Read the configured manifest filename without raising.

    ``get_config_value`` does ``config_data['config'].get(key)``, so a
    ``config:`` section holding a scalar or a list raises ``AttributeError``,
    and a non-string ``metadata_filename`` reaches the caller's ``Path /``
    as a ``TypeError``. Both are bad-config states the verifier reports.

    Args:
        config: Loaded screenshot configuration

    Returns:
        Tuple of (filename, issues). The filename is ``None`` when the value
        is unusable, in which case ``issues`` says why.
    """
    try:
        filename = config.get_metadata_filename()
    except AttributeError:
        return None, [
            "screenshot_config.yaml: 'config' must be a mapping"
        ]

    if not isinstance(filename, str) or not filename:
        return None, [
            f"screenshot_config.yaml: config.metadata_filename must be a "
            f"non-empty string, got {type(filename).__name__}"
        ]

    return filename, []


def _output_of(definition: Dict) -> Optional[str]:
    """
    Return a definition's output path, or None when it is unusable.

    A missing, empty or non-string ``output`` is reported by
    :func:`_verify_config`; every other consumer skips such a definition
    rather than, say, using a list as a set member.
    """
    output = definition.get('output')
    return output if isinstance(output, str) and output else None


def definitions(config: ScreenshotConfig) -> List[Dict]:
    """
    Return the config's screenshot definitions, tolerating a malformed file.

    ``get_all_screenshots()`` returns whatever the YAML held, which may be
    ``None`` (``screenshots:`` with no value) or contain non-mapping entries,
    and raises outright when the document root is not a mapping. All of those
    are reported as issues by :func:`_verify_config`; every other consumer
    works from this filtered view so a bad file yields findings rather than a
    traceback.

    Args:
        config: Loaded screenshot configuration

    Returns:
        The definitions that are mappings, in declaration order
    """
    raw, _ = _raw_screenshots(config)
    if not isinstance(raw, list):
        return []
    return [definition for definition in raw if isinstance(definition, dict)]


def _verify_config(config: ScreenshotConfig) -> List[str]:
    """Check the config is structurally valid and declares capture statuses."""
    issues: List[str] = []

    # Shape first: ScreenshotConfig.validate_config() assumes a mapping whose
    # 'screenshots' key holds a list of mappings, and raises on anything else,
    # so it is only safe to call once the structure has been checked.
    raw, root_is_mapping = _raw_screenshots(config)
    if not root_is_mapping:
        return [
            "screenshot_config.yaml: document root must be a mapping with a "
            "'screenshots' key"
        ]

    _, filename_issues = _metadata_filename(config)
    issues.extend(filename_issues)

    well_shaped = isinstance(raw, list)
    if not well_shaped:
        issues.append(
            f"screenshot_config.yaml: 'screenshots' must be a list, "
            f"got {type(raw).__name__}"
        )
        raw = []

    for index, definition in enumerate(raw):
        if not isinstance(definition, dict):
            well_shaped = False
            issues.append(
                f"screenshot_config.yaml: definition {index} must be a "
                f"mapping, got {type(definition).__name__}"
            )

    if well_shaped:
        is_valid, errors = config.validate_config()
        if not is_valid:
            issues.extend(f"screenshot_config.yaml: {error}" for error in errors)

    outputs: Dict[str, List[str]] = {}
    # Enumerate the raw list, not the filtered view, so a `definition N` label
    # means the same entry as the shape issue reported for index N above.
    for index, definition in enumerate(raw):
        if not isinstance(definition, dict):
            continue

        name = definition.get('name') or f"definition {index}"

        status = definition.get('capture_status')
        if status not in VALID_CAPTURE_STATUSES:
            issues.append(
                f"{name}: missing or invalid capture_status {status!r} "
                f"(expected one of {', '.join(VALID_CAPTURE_STATUSES)})"
            )

        # A bad `output` is reported here rather than left to surface as a
        # confusing orphan/missing pair -- or, for a non-string, as a
        # TypeError when it is used as a set member downstream.
        output = definition.get('output')
        if 'output' in definition and not isinstance(output, str):
            issues.append(
                f"{name}: output must be a string, got {type(output).__name__}"
            )
        elif output == '':
            issues.append(f"{name}: output is empty")
        elif output:
            outputs.setdefault(output, []).append(name)

    for output, names in sorted(outputs.items()):
        if len(names) > 1:
            issues.append(
                f"{output}: declared by multiple definitions "
                f"({', '.join(names)})"
            )

    return issues


def _verify_quality(screenshot_dir: Path, disk_files: List[str]) -> List[str]:
    """Apply the size/format quality gate to every PNG on disk."""
    issues: List[str] = []

    if not disk_files:
        issues.append(f"{screenshot_dir}: no screenshots found")
        return issues

    for relative in disk_files:
        path = screenshot_dir / relative

        try:
            size_kb = path.stat().st_size / 1024
        except OSError as exc:
            # The file was listed a moment ago; a concurrent generation run
            # can still remove it before we get here.
            issues.append(f"{relative}: failed to read - {exc}")
            continue

        if size_kb >= MAX_SCREENSHOT_KB:
            issues.append(
                f"{relative}: {size_kb:.1f}KB "
                f"(over {MAX_SCREENSHOT_KB}KB limit)"
            )

        try:
            with Image.open(path) as img:
                if img.mode not in VALID_IMAGE_MODES:
                    issues.append(f"{relative}: invalid color mode {img.mode}")
        except Exception as exc:
            issues.append(f"{relative}: failed to open - {exc}")

    return issues


def _verify_entries(entries: List) -> List[str]:
    """Check every manifest entry is well formed and appears exactly once."""
    issues: List[str] = []
    counts: Dict[str, int] = {}

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            issues.append(
                f"manifest entry {index}: expected an object, "
                f"got {type(entry).__name__}"
            )
            continue

        for key in REQUIRED_ENTRY_KEYS:
            if key not in entry:
                issues.append(
                    f"manifest entry {index}: missing required key '{key}'"
                )

        capture_type = entry.get('capture_type')
        if 'capture_type' in entry and capture_type not in VALID_CAPTURE_TYPES:
            issues.append(
                f"manifest entry {index}: invalid capture_type "
                f"{capture_type!r} (expected one of "
                f"{', '.join(VALID_CAPTURE_TYPES)})"
            )

        details = entry.get('details')
        if 'details' not in entry:
            issues.append(
                f"manifest entry {index}: missing required key 'details'"
            )
        elif not isinstance(details, dict):
            issues.append(
                f"manifest entry {index}: 'details' must be an object, "
                f"got {type(details).__name__}"
            )
        else:
            for key in REQUIRED_DETAIL_KEYS:
                if key not in details:
                    issues.append(
                        f"manifest entry {index}: details missing "
                        f"required key '{key}'"
                    )

        filename = entry.get('filename')
        if isinstance(filename, str) and filename:
            counts[filename] = counts.get(filename, 0) + 1
        elif filename == '':
            issues.append(f"manifest entry {index}: 'filename' is empty")
        elif 'filename' in entry:
            issues.append(
                f"manifest entry {index}: 'filename' must be a string, "
                f"got {type(filename).__name__}"
            )

    for filename, count in sorted(counts.items()):
        if count > 1:
            issues.append(f"{filename}: duplicate manifest entry")

    return issues


def _verify_cross_references(
    recorded: Set[str],
    disk_files: List[str],
    config: ScreenshotConfig
) -> List[str]:
    """Cross-check manifest against on-disk files and configured captures."""
    issues: List[str] = []
    on_disk = set(disk_files)

    configured_outputs = {
        output
        for definition in definitions(config)
        if (output := _output_of(definition))
    }

    # A conditional capture whose guard did not fire this run leaves its
    # previously committed PNG on disk with no manifest entry. That is the
    # documented meaning of `conditional`, not a stale file, so it is a note
    # (see build_notes) rather than an issue.
    conditional_outputs = {
        output
        for definition in definitions(config)
        if (output := _output_of(definition))
        and definition.get('capture_status') == 'conditional'
    }

    for relative in disk_files:
        if relative not in recorded and relative not in conditional_outputs:
            issues.append(f"{relative}: on disk but not recorded in manifest")

    for filename in sorted(recorded):
        if filename not in on_disk:
            issues.append(f"{filename}: recorded in manifest but missing on disk")

    for filename in sorted(recorded):
        if filename not in configured_outputs:
            issues.append(f"{filename}: not declared in screenshot_config.yaml")

    for definition in definitions(config):
        name = definition.get('name')
        output = _output_of(definition)
        status = definition.get('capture_status')

        if not output:
            continue

        if status == 'required' and output not in recorded:
            issues.append(f"{output}: required capture missing from manifest")
        elif status == 'planned' and output in recorded:
            issues.append(
                f"{name}: captured but marked planned; update capture_status"
            )
        # 'conditional' captures may legitimately be absent -- reported as a
        # note by build_notes(), never as an issue.

    return issues


def build_notes(recorded: Set[str], disk_files: List[str],
                config: ScreenshotConfig) -> List[str]:
    """
    Build the informational notes accompanying a verification summary.

    Args:
        recorded: Filenames recorded in the manifest
        disk_files: Relative paths of the PNGs on disk
        config: Loaded screenshot configuration

    Returns:
        List of note strings (skipped conditional and outstanding planned
        captures)
    """
    notes: List[str] = []
    on_disk = set(disk_files)

    for definition in definitions(config):
        name = definition.get('name')
        output = _output_of(definition)
        status = definition.get('capture_status')

        if not output:
            continue

        if status == 'conditional' and output not in recorded:
            if output in on_disk:
                notes.append(
                    f"conditional capture skipped (guard did not fire); "
                    f"the PNG from an earlier run is still on disk and is "
                    f"not treated as stale: {name} -> {output}"
                )
            else:
                notes.append(
                    f"conditional capture skipped (guard did not fire): "
                    f"{name} -> {output}"
                )
        elif status == 'planned' and output not in recorded:
            notes.append(
                f"planned capture outstanding (no capture code yet): "
                f"{name} -> {output}"
            )

    return notes


def _count_statuses(config: ScreenshotConfig) -> Dict[str, int]:
    """Count configured definitions by capture_status."""
    counts = {status: 0 for status in VALID_CAPTURE_STATUSES}
    for definition in definitions(config):
        status = definition.get('capture_status')
        if status in counts:
            counts[status] += 1
    return counts


def _print_report(screenshot_dir: Path, config: ScreenshotConfig,
                  disk_files: List[str], recorded: Set[str],
                  issues: List[str]) -> None:
    """
    Print the summary, notes, and any issues found.

    Takes the disk listing and recorded filenames that :func:`_collect`
    already computed rather than re-reading the tree, so the report cannot
    disagree with the issues it accompanies.
    """
    status_counts = _count_statuses(config)

    total_kb = 0.0
    for relative in disk_files:
        try:
            total_kb += (screenshot_dir / relative).stat().st_size / 1024
        except OSError:
            pass

    print(f"   Manifest entries:    {len(recorded)}")
    print(f"   PNGs on disk:        {len(disk_files)}")
    print(
        f"   Configured captures: {len(definitions(config))} "
        f"({status_counts['required']} required, "
        f"{status_counts['conditional']} conditional, "
        f"{status_counts['planned']} planned)"
    )
    if disk_files:
        print(f"   Total size:          {total_kb / 1024:.2f} MB")
        print(f"   Average size:        {total_kb / len(disk_files):.1f} KB")

    notes = build_notes(recorded, disk_files, config)
    if notes:
        print("\nℹ️  Notes:")
        for note in notes:
            print(f"   - {note}")

    if issues:
        print("\n❌ Screenshot verification failed:")
        for issue in issues:
            print(f"   - {issue}")
    else:
        print("\n✅ All screenshots verified successfully!")


def main(argv: Optional[List[str]] = None) -> int:
    """
    Command line entry point.

    Args:
        argv: Optional argument list (defaults to ``sys.argv[1:]``)

    Returns:
        0 when no issues were found, 1 otherwise.
    """
    parser = argparse.ArgumentParser(
        description="Verify documentation screenshots against their manifest "
                    "and configuration."
    )
    parser.add_argument(
        '--screenshot-dir',
        default=str(DEFAULT_SCREENSHOT_DIR),
        help="Directory holding the screenshot tree (default: %(default)s)"
    )
    parser.add_argument(
        '--config',
        default=None,
        help="Path to screenshot_config.yaml (default: alongside the loader)"
    )
    args = parser.parse_args(argv)

    screenshot_dir = Path(args.screenshot_dir)

    print(f"🔍 Verifying screenshots in {screenshot_dir}")

    try:
        config = load_screenshot_config(args.config)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"\n❌ Screenshot verification failed:\n   - {exc}")
        return 1

    issues, disk_files, recorded = _collect(screenshot_dir, config)
    _print_report(screenshot_dir, config, disk_files, recorded, issues)

    return 1 if issues else 0


if __name__ == '__main__':
    sys.exit(main())
