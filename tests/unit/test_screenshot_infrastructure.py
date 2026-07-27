"""
Unit Tests for Screenshot Infrastructure

Tests for screenshot generator and configuration loader.
"""

import ast
import os
import pytest
import tempfile
import json
import yaml
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from PIL import Image
from tests.e2e.screenshot_generator import ScreenshotGenerator, new_manifest
from tests.e2e.screenshot_config_loader import ScreenshotConfig, load_screenshot_config
from tests.e2e.screenshot_verifier import (
    MAX_SCREENSHOT_KB,
    VALID_CAPTURE_STATUSES,
    _collect,
    build_notes,
    list_png_files,
    main,
    manifest_filenames,
    verify,
)


class TestScreenshotGenerator:
    """Tests for ScreenshotGenerator class"""

    @pytest.fixture
    def mock_page(self):
        """Create a mock Playwright page object"""
        page = Mock()
        page.viewport_size = {'width': 1920, 'height': 1080}
        page.query_selector_all.return_value = []
        return page

    @pytest.fixture
    def temp_output_dir(self):
        """Create a temporary output directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_screenshot_generator_initialization(self, mock_page, temp_output_dir):
        """Test ScreenshotGenerator initialization"""
        generator = ScreenshotGenerator(mock_page, output_dir=temp_output_dir)

        assert generator.page == mock_page
        assert generator.output_dir == Path(temp_output_dir)
        assert 'generated_at' in generator.metadata
        assert 'screenshots' in generator.metadata
        assert len(generator.metadata['screenshots']) == 0

    def test_screenshot_generator_creates_output_dir(self, mock_page, temp_output_dir):
        """Test that output directory is created if it doesn't exist"""
        output_dir = Path(temp_output_dir) / 'new_dir'
        assert not output_dir.exists()

        generator = ScreenshotGenerator(mock_page, output_dir=str(output_dir))

        assert output_dir.exists()

    @patch('tests.e2e.screenshot_generator.Image')
    def test_capture_full_page(self, mock_image, mock_page, temp_output_dir):
        """Test full page screenshot capture"""
        generator = ScreenshotGenerator(mock_page, output_dir=temp_output_dir)

        # Mock Image.open to avoid actual image processing
        mock_img = MagicMock()
        mock_img.mode = 'RGB'
        mock_image.open.return_value = mock_img

        output_path = generator.capture_full_page('test.png')

        # Verify screenshot was called
        mock_page.screenshot.assert_called_once()
        call_args = mock_page.screenshot.call_args
        assert call_args[1]['path'] == str(output_path)
        assert call_args[1]['full_page'] is True

        # Verify metadata was recorded
        assert len(generator.metadata['screenshots']) == 1
        assert generator.metadata['screenshots'][0]['filename'] == 'test.png'
        assert generator.metadata['screenshots'][0]['capture_type'] == 'full_page'

    @patch('tests.e2e.screenshot_generator.Image')
    def test_capture_element(self, mock_image, mock_page, temp_output_dir):
        """Test element screenshot capture"""
        generator = ScreenshotGenerator(mock_page, output_dir=temp_output_dir)

        # Mock element with bounding box
        mock_element = Mock()
        mock_element.bounding_box.return_value = {
            'x': 100,
            'y': 200,
            'width': 300,
            'height': 400
        }
        mock_page.wait_for_selector.return_value = mock_element

        # Mock Image.open
        mock_img = MagicMock()
        mock_img.mode = 'RGB'
        mock_image.open.return_value = mock_img

        output_path = generator.capture_element('#test-element', 'element.png', padding=10)

        # Verify wait_for_selector was called
        mock_page.wait_for_selector.assert_called_once_with('#test-element', timeout=5000)

        # Verify screenshot was called with clip
        mock_page.screenshot.assert_called_once()
        call_args = mock_page.screenshot.call_args
        clip = call_args[1]['clip']
        assert clip['x'] == 90  # 100 - 10 padding
        assert clip['y'] == 190  # 200 - 10 padding
        assert clip['width'] == 320  # 300 + 2*10 padding
        assert clip['height'] == 420  # 400 + 2*10 padding

    def test_capture_element_not_found(self, mock_page, temp_output_dir):
        """Test capture_element raises error when element not found"""
        generator = ScreenshotGenerator(mock_page, output_dir=temp_output_dir)
        mock_page.wait_for_selector.return_value = None

        with pytest.raises(ValueError, match="Element not found"):
            generator.capture_element('#missing-element', 'test.png')

    def test_get_screenshot_count(self, mock_page, temp_output_dir):
        """Test getting screenshot count"""
        generator = ScreenshotGenerator(mock_page, output_dir=temp_output_dir)

        assert generator.get_screenshot_count() == 0

        # Add some metadata manually
        generator.metadata['screenshots'].append({'test': 'data'})
        generator.metadata['screenshots'].append({'test': 'data2'})

        assert generator.get_screenshot_count() == 2

    def test_save_metadata(self, mock_page, temp_output_dir):
        """Test saving metadata to JSON file"""
        generator = ScreenshotGenerator(mock_page, output_dir=temp_output_dir)

        # Add some test metadata
        generator.metadata['screenshots'].append({
            'filename': 'test.png',
            'capture_type': 'full_page'
        })

        metadata_path = generator.save_metadata()

        # Verify file was created
        assert metadata_path.exists()

        # Verify contents
        with open(metadata_path) as f:
            saved_metadata = json.load(f)

        assert 'generated_at' in saved_metadata
        assert len(saved_metadata['screenshots']) == 1
        assert saved_metadata['screenshots'][0]['filename'] == 'test.png'


class TestScreenshotManifestAccumulation:
    """Tests for manifest sharing, normalisation and stable serialisation"""

    @pytest.fixture
    def mock_page(self):
        """Create a mock Playwright page object"""
        page = Mock()
        page.viewport_size = {'width': 1920, 'height': 1080}
        page.query_selector_all.return_value = []
        return page

    @pytest.fixture
    def temp_output_dir(self):
        """Create a temporary output directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def mock_image(self):
        """Patch out PIL so no real image processing happens"""
        with patch('tests.e2e.screenshot_generator.Image') as mock:
            img = MagicMock()
            img.mode = 'RGB'
            mock.open.return_value = img
            yield mock

    def test_new_manifest_shape(self):
        """new_manifest() returns an empty, timestamped manifest"""
        manifest = new_manifest()

        assert 'generated_at' in manifest
        assert manifest['screenshots'] == []

        # Each call returns an independent object
        assert new_manifest()['screenshots'] is not manifest['screenshots']

    def test_get_metadata_does_not_expose_the_shared_screenshots_list(
        self, mock_page, temp_output_dir, mock_image
    ):
        """A caller's edit to the returned copy cannot corrupt the session manifest"""
        manifest = new_manifest()
        generator = ScreenshotGenerator(mock_page, output_dir=temp_output_dir,
                                        manifest=manifest)
        generator.capture_full_page('a.png')

        copy = generator.get_metadata()
        copy['screenshots'].clear()

        assert generator.get_screenshot_count() == 1
        assert manifest['screenshots'][0]['filename'] == 'a.png'

    def test_manifest_shared_between_generators(self, mock_page, temp_output_dir,
                                                mock_image):
        """Two generators sharing a manifest accumulate into one file"""
        manifest = new_manifest()

        first = ScreenshotGenerator(mock_page, output_dir=temp_output_dir,
                                    manifest=manifest)
        second = ScreenshotGenerator(mock_page, output_dir=temp_output_dir,
                                     manifest=manifest)

        first.capture_full_page('a.png')
        second.capture_full_page('b.png')

        assert first.get_screenshot_count() == 2
        assert second.get_screenshot_count() == 2

        # A single save writes both entries
        metadata_path = second.save_metadata()
        with open(metadata_path) as f:
            saved = json.load(f)

        assert [entry['filename'] for entry in saved['screenshots']] == ['a.png', 'b.png']

    def test_manifest_defaults_to_private_when_omitted(self, mock_page,
                                                       temp_output_dir, mock_image):
        """Without a shared manifest each generator keeps its own"""
        first = ScreenshotGenerator(mock_page, output_dir=temp_output_dir)
        second = ScreenshotGenerator(mock_page, output_dir=temp_output_dir)

        first.capture_full_page('a.png')

        assert first.get_screenshot_count() == 1
        assert second.get_screenshot_count() == 0

    def test_recapture_replaces_entry(self, mock_page, temp_output_dir, mock_image):
        """Capturing the same filename twice replaces, never duplicates"""
        generator = ScreenshotGenerator(mock_page, output_dir=temp_output_dir)

        generator.capture_full_page('a.png')
        first_timestamp = generator.metadata['screenshots'][0]['timestamp']
        generator.capture_viewport('a.png', viewport_size=(800, 600))

        assert generator.get_screenshot_count() == 1
        entry = generator.metadata['screenshots'][0]
        assert entry['capture_type'] == 'viewport'
        assert entry['details']['viewport_size'] == (800, 600)
        assert entry['timestamp'] >= first_timestamp

    def test_details_normalized_for_full_page(self, mock_page, temp_output_dir,
                                              mock_image):
        """full_page captures always record viewport_size and hide_selectors"""
        generator = ScreenshotGenerator(mock_page, output_dir=temp_output_dir)

        generator.capture_full_page('a.png', hide_selectors=['.toast-container'])

        details = generator.metadata['screenshots'][0]['details']
        assert details['viewport_size'] is None
        assert details['hide_selectors'] == ['.toast-container']

    def test_details_normalized_for_element(self, mock_page, temp_output_dir,
                                            mock_image):
        """element captures always record viewport_size and hide_selectors"""
        element = Mock()
        element.bounding_box.return_value = {
            'x': 0, 'y': 0, 'width': 10, 'height': 10
        }
        mock_page.wait_for_selector.return_value = element

        generator = ScreenshotGenerator(mock_page, output_dir=temp_output_dir)
        generator.capture_element('#thing', 'a.png')

        details = generator.metadata['screenshots'][0]['details']
        assert details['viewport_size'] is None
        assert details['hide_selectors'] is None
        assert details['selector'] == '#thing'

    def test_details_normalized_for_viewport(self, mock_page, temp_output_dir,
                                             mock_image):
        """viewport captures always record viewport_size and hide_selectors"""
        generator = ScreenshotGenerator(mock_page, output_dir=temp_output_dir)

        generator.capture_viewport('a.png', viewport_size=(1280, 720))

        details = generator.metadata['screenshots'][0]['details']
        assert details['viewport_size'] == (1280, 720)
        assert details['hide_selectors'] is None

    def test_every_entry_has_required_keys(self, mock_page, temp_output_dir,
                                           mock_image):
        """All three capture methods emit the manifest's required keys"""
        element = Mock()
        element.bounding_box.return_value = {
            'x': 0, 'y': 0, 'width': 10, 'height': 10
        }
        mock_page.wait_for_selector.return_value = element

        generator = ScreenshotGenerator(mock_page, output_dir=temp_output_dir)
        generator.capture_full_page('a.png')
        generator.capture_element('#thing', 'b.png')
        generator.capture_viewport('c.png')

        for entry in generator.metadata['screenshots']:
            assert set(entry) >= {'filename', 'capture_type', 'timestamp', 'details'}
            assert 'viewport_size' in entry['details']
            assert 'hide_selectors' in entry['details']

    def test_save_metadata_sorted_and_newline_terminated(self, mock_page,
                                                         temp_output_dir,
                                                         mock_image):
        """save_metadata sorts by filename and ends the file with a newline"""
        generator = ScreenshotGenerator(mock_page, output_dir=temp_output_dir)

        generator.capture_full_page('z.png')
        generator.capture_full_page('a.png')
        generator.capture_full_page('m.png')

        metadata_path = generator.save_metadata()
        raw = metadata_path.read_text()

        assert raw.endswith('\n')

        saved = json.loads(raw)
        filenames = [entry['filename'] for entry in saved['screenshots']]
        assert filenames == ['a.png', 'm.png', 'z.png']


class TestScreenshotConfig:
    """Tests for ScreenshotConfig class"""

    @pytest.fixture
    def config_path(self):
        """Get path to the actual screenshot config file"""
        return Path(__file__).parent.parent / 'e2e' / 'screenshot_config.yaml'

    def test_load_config(self, config_path):
        """Test loading the screenshot configuration"""
        config = ScreenshotConfig(str(config_path))

        assert config._config_data is not None
        assert 'screenshots' in config._config_data

    def test_load_config_file_not_found(self):
        """Test loading config with nonexistent file"""
        with pytest.raises(FileNotFoundError):
            ScreenshotConfig('/nonexistent/config.yaml')

    def test_get_all_screenshots(self, config_path):
        """Test getting all screenshot definitions"""
        config = ScreenshotConfig(str(config_path))
        screenshots = config.get_all_screenshots()

        assert isinstance(screenshots, list)
        assert len(screenshots) > 0

        # Verify each screenshot has required fields
        for screenshot in screenshots:
            assert 'name' in screenshot
            assert 'description' in screenshot
            assert 'output' in screenshot

    def test_get_screenshot_by_name(self, config_path):
        """Test getting a specific screenshot by name"""
        config = ScreenshotConfig(str(config_path))

        screenshot = config.get_screenshot_by_name('inventory_list_main')

        assert screenshot is not None
        assert screenshot['name'] == 'inventory_list_main'
        assert 'description' in screenshot

        # Test nonexistent screenshot
        assert config.get_screenshot_by_name('nonexistent') is None

    def test_get_default_viewport(self, config_path):
        """Test getting default viewport size"""
        config = ScreenshotConfig(str(config_path))
        viewport = config.get_default_viewport()

        assert isinstance(viewport, tuple)
        assert len(viewport) == 2
        assert viewport[0] > 0
        assert viewport[1] > 0

    def test_get_config_values(self, config_path):
        """Test getting configuration values"""
        config = ScreenshotConfig(str(config_path))

        assert isinstance(config.should_optimize_images(), bool)
        assert isinstance(config.get_default_timeout(), int)
        assert isinstance(config.get_metadata_filename(), str)

    def test_count_screenshots(self, config_path):
        """Test counting screenshots"""
        config = ScreenshotConfig(str(config_path))
        count = config.count_screenshots()

        assert count > 0
        assert count == len(config.get_all_screenshots())

    def test_validate_config(self, config_path):
        """Test configuration validation"""
        config = ScreenshotConfig(str(config_path))
        is_valid, errors = config.validate_config()

        assert is_valid is True
        assert len(errors) == 0

    def test_get_screenshots_for_doc_file(self, config_path):
        """Test getting screenshots for a specific documentation file"""
        config = ScreenshotConfig(str(config_path))

        # Get screenshots for README
        readme_screenshots = config.get_screenshots_for_doc_file('README.md')

        assert len(readme_screenshots) > 0
        for screenshot in readme_screenshots:
            assert 'doc_section' in screenshot
            assert 'doc_caption' in screenshot

    def test_load_screenshot_config_function(self, config_path):
        """Test the convenience function for loading config"""
        config = load_screenshot_config(str(config_path))

        assert isinstance(config, ScreenshotConfig)
        assert config.count_screenshots() > 0

    def test_every_definition_has_valid_capture_status(self, config_path):
        """Every definition declares required/conditional/planned"""
        config = ScreenshotConfig(str(config_path))

        for definition in config.get_all_screenshots():
            status = definition.get('capture_status')
            assert status in VALID_CAPTURE_STATUSES, (
                f"{definition.get('name')}: invalid capture_status {status!r}"
            )

    def test_definition_outputs_are_unique(self, config_path):
        """No two definitions claim the same output path"""
        config = ScreenshotConfig(str(config_path))

        outputs = [d['output'] for d in config.get_all_screenshots()]

        assert len(outputs) == len(set(outputs)), (
            f"duplicate outputs: {sorted({o for o in outputs if outputs.count(o) > 1})}"
        )

    def test_capturing_definitions_name_real_test_methods(self, config_path):
        """`test:` on required/conditional entries names a real test method

        Parsed from source rather than imported, because importing the e2e
        module pulls in Playwright and the app.
        """
        test_module = (
            Path(__file__).parent.parent / 'e2e' / 'test_screenshot_generation.py'
        )
        tree = ast.parse(test_module.read_text())
        method_names = {
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith('test_')
        }

        config = ScreenshotConfig(str(config_path))
        for definition in config.get_all_screenshots():
            if definition['capture_status'] not in ('required', 'conditional'):
                continue
            assert definition['test'] in method_names, (
                f"{definition['name']}: test '{definition['test']}' does not "
                f"exist in {test_module.name}"
            )


def _definition(name, output, capture_status, test='test_screenshot_thing'):
    """Build a minimal but valid screenshot definition."""
    return {
        'name': name,
        'description': f'{name} description',
        'test': test,
        'output': output,
        'capture_status': capture_status,
        'documentation_files': [{'file': 'docs/user-manual.md'}],
    }


def _entry(filename, **overrides):
    """Build a well-formed manifest entry."""
    entry = {
        'filename': filename,
        'capture_type': 'viewport',
        'timestamp': '2026-07-27T12:00:00',
        'details': {
            'viewport_size': [1920, 1080],
            'hide_selectors': None,
        },
    }
    entry.update(overrides)
    return entry


class TestScreenshotVerifier:
    """Tests for the screenshot verifier, one per I/O matrix row"""

    @pytest.fixture
    def screenshot_dir(self, tmp_path):
        """Empty screenshot tree"""
        directory = tmp_path / 'screenshots'
        directory.mkdir()
        return directory

    @pytest.fixture
    def make_png(self, screenshot_dir):
        """Write a small valid PNG into the screenshot tree"""
        def _make(relative, mode='RGB', size=(8, 8), noise=False):
            path = screenshot_dir / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if noise:
                # Incompressible data so the PNG blows the size limit
                pixels = os.urandom(size[0] * size[1] * 3)
                img = Image.frombytes('RGB', size, pixels)
            else:
                img = Image.new(mode, size)
            img.save(path, 'PNG')
            return path
        return _make

    @pytest.fixture
    def write_manifest(self, screenshot_dir):
        """Write metadata.json into the screenshot tree"""
        def _write(entries, raw=None):
            path = screenshot_dir / 'metadata.json'
            if raw is not None:
                path.write_text(raw)
            else:
                path.write_text(json.dumps({
                    'generated_at': '2026-07-27T12:00:00',
                    'screenshots': entries,
                }) + '\n')
            return path
        return _write

    @pytest.fixture
    def make_config(self, tmp_path):
        """Write a config YAML and load it"""
        def _make(definitions):
            path = tmp_path / 'screenshot_config.yaml'
            path.write_text(yaml.safe_dump({
                'screenshots': definitions,
                'config': {'metadata_filename': 'metadata.json'},
            }))
            return ScreenshotConfig(str(path))
        return _make

    # -- Matrix row: complete run -------------------------------------------

    def test_complete_run_has_no_issues(self, screenshot_dir, make_png,
                                        write_manifest, make_config):
        make_png('readme/a.png')
        make_png('user-manual/b.png')
        write_manifest([_entry('readme/a.png'), _entry('user-manual/b.png')])
        config = make_config([
            _definition('a', 'readme/a.png', 'required'),
            _definition('b', 'user-manual/b.png', 'conditional'),
            _definition('c', 'user-manual/c.png', 'planned'),
        ])

        assert verify(screenshot_dir, config) == []

    # -- Matrix row: partial regeneration ------------------------------------

    def test_required_capture_missing_from_manifest(self, screenshot_dir, make_png,
                                                    write_manifest, make_config):
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png')])
        config = make_config([
            _definition('a', 'readme/a.png', 'required'),
            _definition('b', 'user-manual/b.png', 'required'),
        ])

        assert verify(screenshot_dir, config) == [
            'user-manual/b.png: required capture missing from manifest'
        ]

    # -- Matrix row: stale/orphan PNG ----------------------------------------

    def test_orphan_png_on_disk(self, screenshot_dir, make_png, write_manifest,
                                make_config):
        make_png('readme/a.png')
        make_png('user-manual/leftover.png')
        write_manifest([_entry('readme/a.png')])
        config = make_config([_definition('a', 'readme/a.png', 'required')])

        assert verify(screenshot_dir, config) == [
            'user-manual/leftover.png: on disk but not recorded in manifest'
        ]

    def test_planned_capture_png_on_disk_is_an_orphan(self, screenshot_dir,
                                                      make_png, write_manifest,
                                                      make_config):
        """A planned capture has no code, so a PNG for it is a leftover."""
        make_png('readme/a.png')
        make_png('user-manual/future.png')
        write_manifest([_entry('readme/a.png')])
        config = make_config([
            _definition('a', 'readme/a.png', 'required'),
            _definition('future', 'user-manual/future.png', 'planned'),
        ])

        assert verify(screenshot_dir, config) == [
            'user-manual/future.png: on disk but not recorded in manifest'
        ]

    def test_conditional_png_on_disk_without_manifest_entry_is_not_an_orphan(
        self, screenshot_dir, make_png, write_manifest, make_config
    ):
        """
        The realistic conditional case: the PNG was committed by an earlier
        run whose guard fired, and this run's guard did not. That is exactly
        what `conditional` means, so it must not fail verification.
        """
        make_png('readme/a.png')
        make_png('user-manual/maybe.png')
        write_manifest([_entry('readme/a.png')])
        config = make_config([
            _definition('a', 'readme/a.png', 'required'),
            _definition('maybe', 'user-manual/maybe.png', 'conditional'),
        ])

        assert verify(screenshot_dir, config) == []

        notes = build_notes(
            manifest_filenames([_entry('readme/a.png')]),
            list_png_files(screenshot_dir),
            config
        )
        assert any(
            'maybe' in note and 'still on disk' in note for note in notes
        )

    # -- Matrix row: recorded but missing file -------------------------------

    def test_recorded_but_missing_on_disk(self, screenshot_dir, make_png,
                                          write_manifest, make_config):
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png'), _entry('user-manual/b.png')])
        config = make_config([
            _definition('a', 'readme/a.png', 'required'),
            _definition('b', 'user-manual/b.png', 'conditional'),
        ])

        assert verify(screenshot_dir, config) == [
            'user-manual/b.png: recorded in manifest but missing on disk'
        ]

    # -- Matrix row: unconfigured capture ------------------------------------

    def test_manifest_entry_not_declared_in_config(self, screenshot_dir, make_png,
                                                   write_manifest, make_config):
        make_png('readme/a.png')
        make_png('user-manual/rogue.png')
        write_manifest([_entry('readme/a.png'), _entry('user-manual/rogue.png')])
        config = make_config([_definition('a', 'readme/a.png', 'required')])

        assert verify(screenshot_dir, config) == [
            'user-manual/rogue.png: not declared in screenshot_config.yaml'
        ]

    # -- Matrix row: planned capture appeared --------------------------------

    def test_planned_capture_appeared(self, screenshot_dir, make_png,
                                      write_manifest, make_config):
        make_png('readme/a.png')
        make_png('user-manual/future.png')
        write_manifest([_entry('readme/a.png'), _entry('user-manual/future.png')])
        config = make_config([
            _definition('a', 'readme/a.png', 'required'),
            _definition('future', 'user-manual/future.png', 'planned'),
        ])

        assert verify(screenshot_dir, config) == [
            'future: captured but marked planned; update capture_status'
        ]

    # -- Matrix row: conditional skipped -------------------------------------

    def test_conditional_skipped_is_a_note_not_an_issue(self, screenshot_dir,
                                                        make_png, write_manifest,
                                                        make_config):
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png')])
        config = make_config([
            _definition('a', 'readme/a.png', 'required'),
            _definition('maybe', 'user-manual/maybe.png', 'conditional'),
            _definition('later', 'user-manual/later.png', 'planned'),
        ])

        assert verify(screenshot_dir, config) == []

        notes = build_notes(
            manifest_filenames([_entry('readme/a.png')]),
            list_png_files(screenshot_dir),
            config
        )
        assert any('maybe' in note and 'conditional' in note for note in notes)
        assert any('later' in note and 'planned' in note for note in notes)

    # -- Matrix row: missing/corrupt manifest --------------------------------

    def test_missing_manifest(self, screenshot_dir, make_png, make_config):
        make_png('readme/a.png')
        config = make_config([_definition('a', 'readme/a.png', 'required')])

        issues = verify(screenshot_dir, config)

        assert len(issues) == 1
        assert issues[0].startswith('metadata.json: manifest not found')

    def test_corrupt_manifest(self, screenshot_dir, make_png, write_manifest,
                              make_config):
        make_png('readme/a.png')
        write_manifest(None, raw='{not json at all')
        config = make_config([_definition('a', 'readme/a.png', 'required')])

        issues = verify(screenshot_dir, config)

        assert len(issues) == 1
        assert issues[0].startswith('metadata.json: not valid JSON')

    def test_manifest_with_undecodable_bytes(self, screenshot_dir, make_png,
                                             make_config):
        """A binary-clobbered manifest is corrupt, not a UnicodeDecodeError"""
        make_png('readme/a.png')
        (screenshot_dir / 'metadata.json').write_bytes(
            b'{"screenshots": [{"filename": "\xff\xfe"}]}'
        )
        config = make_config([_definition('a', 'readme/a.png', 'required')])

        issues = verify(screenshot_dir, config)

        assert len(issues) == 1
        assert issues[0].startswith('metadata.json: not valid JSON')

    def test_manifest_without_screenshots_list(self, screenshot_dir, make_png,
                                               write_manifest, make_config):
        make_png('readme/a.png')
        write_manifest(None, raw=json.dumps({'generated_at': 'x'}))
        config = make_config([_definition('a', 'readme/a.png', 'required')])

        assert verify(screenshot_dir, config) == [
            "metadata.json: missing a 'screenshots' list"
        ]

    # -- Matrix row: malformed entry -----------------------------------------

    def test_entry_missing_top_level_key(self, screenshot_dir, make_png,
                                         write_manifest, make_config):
        make_png('readme/a.png')
        entry = _entry('readme/a.png')
        del entry['timestamp']
        write_manifest([entry])
        config = make_config([_definition('a', 'readme/a.png', 'required')])

        assert verify(screenshot_dir, config) == [
            "manifest entry 0: missing required key 'timestamp'"
        ]

    def test_entry_details_missing_key(self, screenshot_dir, make_png,
                                       write_manifest, make_config):
        make_png('readme/a.png')
        entry = _entry('readme/a.png')
        del entry['details']['hide_selectors']
        write_manifest([entry])
        config = make_config([_definition('a', 'readme/a.png', 'required')])

        assert verify(screenshot_dir, config) == [
            "manifest entry 0: details missing required key 'hide_selectors'"
        ]

    def test_entry_with_empty_filename(self, screenshot_dir, make_png,
                                       write_manifest, make_config):
        """An empty filename is named directly, not echoed as a blank subject"""
        make_png('readme/a.png')
        write_manifest([_entry(''), _entry('readme/a.png')])
        config = make_config([_definition('a', 'readme/a.png', 'required')])

        assert verify(screenshot_dir, config) == [
            "manifest entry 0: 'filename' is empty"
        ]

    # -- Matrix row: duplicate entries ---------------------------------------

    def test_duplicate_manifest_entries(self, screenshot_dir, make_png,
                                        write_manifest, make_config):
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png'), _entry('readme/a.png')])
        config = make_config([_definition('a', 'readme/a.png', 'required')])

        assert verify(screenshot_dir, config) == [
            'readme/a.png: duplicate manifest entry'
        ]

    # -- Matrix row: bad config ----------------------------------------------

    def test_missing_capture_status(self, screenshot_dir, make_png,
                                    write_manifest, make_config):
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png')])
        definition = _definition('a', 'readme/a.png', 'required')
        del definition['capture_status']
        config = make_config([definition])

        issues = verify(screenshot_dir, config)

        assert len(issues) == 1
        assert issues[0].startswith('a: missing or invalid capture_status None')

    def test_invalid_capture_status(self, screenshot_dir, make_png,
                                    write_manifest, make_config):
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png')])
        config = make_config([_definition('a', 'readme/a.png', 'someday')])

        issues = verify(screenshot_dir, config)

        assert len(issues) == 1
        assert "invalid capture_status 'someday'" in issues[0]

    def test_duplicate_config_outputs(self, screenshot_dir, make_png,
                                      write_manifest, make_config):
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png')])
        config = make_config([
            _definition('a', 'readme/a.png', 'required'),
            _definition('a_again', 'readme/a.png', 'required'),
        ])

        assert verify(screenshot_dir, config) == [
            'readme/a.png: declared by multiple definitions (a, a_again)'
        ]

    def test_structurally_invalid_config_is_reported(self, screenshot_dir,
                                                     make_png, write_manifest,
                                                     make_config):
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png')])
        definition = _definition('a', 'readme/a.png', 'required')
        del definition['documentation_files']
        config = make_config([definition])

        issues = verify(screenshot_dir, config)

        assert any('documentation_files' in issue for issue in issues)

    # -- Quality gate --------------------------------------------------------

    def test_no_screenshots_at_all(self, screenshot_dir, write_manifest,
                                   make_config):
        write_manifest([])
        config = make_config([])

        issues = verify(screenshot_dir, config)

        assert any('no screenshots found' in issue for issue in issues)

    def test_oversized_screenshot(self, screenshot_dir, make_png, write_manifest,
                                  make_config):
        make_png('readme/a.png', size=(700, 700), noise=True)
        write_manifest([_entry('readme/a.png')])
        config = make_config([_definition('a', 'readme/a.png', 'required')])

        issues = verify(screenshot_dir, config)

        assert len(issues) == 1
        assert f'over {MAX_SCREENSHOT_KB}KB limit' in issues[0]

    def test_invalid_color_mode(self, screenshot_dir, make_png, write_manifest,
                                make_config):
        make_png('readme/a.png', mode='P')
        write_manifest([_entry('readme/a.png')])
        config = make_config([_definition('a', 'readme/a.png', 'required')])

        assert verify(screenshot_dir, config) == [
            'readme/a.png: invalid color mode P'
        ]

    # -- Malformed manifest entries ------------------------------------------

    def test_invalid_capture_type(self, screenshot_dir, make_png,
                                  write_manifest, make_config):
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png', capture_type='screengrab')])
        config = make_config([_definition('a', 'readme/a.png', 'required')])

        issues = verify(screenshot_dir, config)

        assert any(
            "invalid capture_type 'screengrab'" in issue for issue in issues
        )

    def test_non_string_filename_is_reported(self, screenshot_dir, make_png,
                                             write_manifest, make_config):
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png'), _entry(None)])
        config = make_config([_definition('a', 'readme/a.png', 'required')])

        issues = verify(screenshot_dir, config)

        assert any(
            "'filename' must be a string" in issue for issue in issues
        )

    # -- Malformed config -----------------------------------------------------

    def test_null_screenshots_list_is_reported(self, screenshot_dir, make_png,
                                               write_manifest, tmp_path):
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png')])
        path = tmp_path / 'screenshot_config.yaml'
        path.write_text('screenshots:\nconfig:\n  metadata_filename: metadata.json\n')

        issues = verify(screenshot_dir, ScreenshotConfig(str(path)))

        assert any("'screenshots' must be a list" in issue for issue in issues)

    def test_non_mapping_config_root_is_reported(self, screenshot_dir, make_png,
                                                 write_manifest, tmp_path):
        """A YAML document that is not a mapping yields a finding, not a traceback"""
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png')])
        path = tmp_path / 'screenshot_config.yaml'
        path.write_text('- one\n- two\n')

        issues = verify(screenshot_dir, ScreenshotConfig(str(path)))

        assert issues == [
            "screenshot_config.yaml: document root must be a mapping with a "
            "'screenshots' key"
        ]

    def test_scalar_config_root_is_reported_by_main(self, screenshot_dir,
                                                    make_png, write_manifest,
                                                    tmp_path, capsys):
        """The CLI survives a scalar config document"""
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png')])
        path = tmp_path / 'screenshot_config.yaml'
        path.write_text('just a string\n')

        exit_code = main([
            '--screenshot-dir', str(screenshot_dir), '--config', str(path)
        ])

        assert exit_code == 1
        assert 'document root must be a mapping' in capsys.readouterr().out

    def test_non_string_output_is_reported(self, screenshot_dir, make_png,
                                           write_manifest, make_config):
        """A list-valued `output` is reported rather than used as a set member"""
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png')])
        definition = _definition('a', 'readme/a.png', 'required')
        definition['output'] = ['readme/a.png']
        config = make_config([definition])

        issues = verify(screenshot_dir, config)

        assert 'a: output must be a string, got list' in issues

    def test_empty_output_is_reported(self, screenshot_dir, make_png,
                                      write_manifest, make_config):
        """An empty `output` disables every cross-check, so it must be named"""
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png')])
        config = make_config([_definition('a', '', 'required')])

        assert 'a: output is empty' in verify(screenshot_dir, config)

    def test_details_present_but_not_an_object(self, screenshot_dir, make_png,
                                               write_manifest, make_config):
        """A present-but-wrong-typed `details` is not reported as missing"""
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png', details=['nope'])])
        config = make_config([_definition('a', 'readme/a.png', 'required')])

        assert verify(screenshot_dir, config) == [
            "manifest entry 0: 'details' must be an object, got list"
        ]

    def test_report_values_come_from_the_same_pass_as_the_issues(
        self, screenshot_dir, make_png, write_manifest, make_config
    ):
        """_collect hands the summary the very listing it verified"""
        make_png('readme/a.png')
        make_png('user-manual/b.png')
        write_manifest([_entry('readme/a.png'), _entry('user-manual/b.png')])
        config = make_config([
            _definition('a', 'readme/a.png', 'required'),
            _definition('b', 'user-manual/b.png', 'required'),
        ])

        issues, disk_files, recorded = _collect(screenshot_dir, config)

        assert issues == []
        assert disk_files == ['readme/a.png', 'user-manual/b.png']
        assert recorded == {'readme/a.png', 'user-manual/b.png'}

    def test_non_mapping_definition_is_reported(self, screenshot_dir, make_png,
                                                write_manifest, tmp_path):
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png')])
        path = tmp_path / 'screenshot_config.yaml'
        path.write_text(yaml.safe_dump({
            'screenshots': ['just a string'],
            'config': {'metadata_filename': 'metadata.json'},
        }))

        issues = verify(screenshot_dir, ScreenshotConfig(str(path)))

        assert any('must be a mapping' in issue for issue in issues)

    def test_non_mapping_config_section_is_reported(self, screenshot_dir,
                                                    make_png, write_manifest,
                                                    tmp_path):
        """A scalar `config:` section is a finding, not an AttributeError"""
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png')])
        path = tmp_path / 'screenshot_config.yaml'
        path.write_text(yaml.safe_dump({
            'screenshots': [_definition('a', 'readme/a.png', 'required')],
            'config': 'not a mapping',
        }))

        issues = verify(screenshot_dir, ScreenshotConfig(str(path)))

        assert issues == ["screenshot_config.yaml: 'config' must be a mapping"]

    def test_non_string_metadata_filename_is_reported(self, screenshot_dir,
                                                      make_png, write_manifest,
                                                      tmp_path):
        """A list-valued metadata_filename never reaches `screenshot_dir / ...`"""
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png')])
        path = tmp_path / 'screenshot_config.yaml'
        path.write_text(yaml.safe_dump({
            'screenshots': [_definition('a', 'readme/a.png', 'required')],
            'config': {'metadata_filename': ['metadata.json']},
        }))

        issues = verify(screenshot_dir, ScreenshotConfig(str(path)))

        assert issues == [
            'screenshot_config.yaml: config.metadata_filename must be a '
            'non-empty string, got list'
        ]

    def test_main_survives_a_non_mapping_config_section(self, screenshot_dir,
                                                        make_png,
                                                        write_manifest,
                                                        tmp_path, capsys):
        """The CLI reports the bad section instead of tracebacking"""
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png')])
        path = tmp_path / 'screenshot_config.yaml'
        path.write_text(yaml.safe_dump({
            'screenshots': [_definition('a', 'readme/a.png', 'required')],
            'config': 'not a mapping',
        }))

        exit_code = main([
            '--screenshot-dir', str(screenshot_dir), '--config', str(path)
        ])

        assert exit_code == 1
        assert "'config' must be a mapping" in capsys.readouterr().out

    def test_definition_labels_share_one_index_space(self, screenshot_dir,
                                                     make_png, write_manifest,
                                                     tmp_path):
        """`definition N` names the same entry in shape and field issues"""
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png')])
        path = tmp_path / 'screenshot_config.yaml'
        unnamed = _definition('a', 'readme/a.png', 'bogus')
        del unnamed['name']
        path.write_text(yaml.safe_dump({
            'screenshots': ['just a string', unnamed],
            'config': {'metadata_filename': 'metadata.json'},
        }))

        issues = verify(screenshot_dir, ScreenshotConfig(str(path)))

        assert any('definition 0 must be a mapping' in issue for issue in issues)
        assert any(
            issue.startswith('definition 1: missing or invalid capture_status')
            for issue in issues
        )
        assert not any(
            issue.startswith('definition 0: missing or invalid capture_status')
            for issue in issues
        )

    # -- Case-insensitive discovery -------------------------------------------

    def test_uppercase_png_extension_is_discovered(self, screenshot_dir,
                                                   make_png, write_manifest,
                                                   make_config):
        make_png('readme/a.png')
        make_png('readme/SHOUTY.PNG')
        write_manifest([_entry('readme/a.png')])
        config = make_config([_definition('a', 'readme/a.png', 'required')])

        assert verify(screenshot_dir, config) == [
            'readme/SHOUTY.PNG: on disk but not recorded in manifest'
        ]

    # -- Report notes ---------------------------------------------------------

    def test_planned_capture_in_manifest_gets_no_outstanding_note(
        self, screenshot_dir, make_png, write_manifest, make_config
    ):
        """The 'not written yet' note must not accompany its own failure."""
        make_png('readme/a.png')
        make_png('user-manual/future.png')
        entries = [_entry('readme/a.png'), _entry('user-manual/future.png')]
        write_manifest(entries)
        config = make_config([
            _definition('a', 'readme/a.png', 'required'),
            _definition('future', 'user-manual/future.png', 'planned'),
        ])

        notes = build_notes(
            manifest_filenames(entries), list_png_files(screenshot_dir), config
        )

        assert not any('future' in note for note in notes)

    # -- CLI entry point ------------------------------------------------------

    def test_main_reports_unreadable_config_without_traceback(
        self, screenshot_dir, make_png, write_manifest, tmp_path, capsys
    ):
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png')])
        path = tmp_path / 'broken.yaml'
        path.write_text('screenshots: [oops\n')

        exit_code = main([
            '--screenshot-dir', str(screenshot_dir), '--config', str(path)
        ])

        assert exit_code == 1
        assert 'verification failed' in capsys.readouterr().out

    def test_main_succeeds_on_a_consistent_tree(self, screenshot_dir, make_png,
                                                write_manifest, tmp_path,
                                                capsys):
        make_png('readme/a.png')
        write_manifest([_entry('readme/a.png')])
        path = tmp_path / 'screenshot_config.yaml'
        path.write_text(yaml.safe_dump({
            'screenshots': [_definition('a', 'readme/a.png', 'required')],
            'config': {'metadata_filename': 'metadata.json'},
        }))

        exit_code = main([
            '--screenshot-dir', str(screenshot_dir), '--config', str(path)
        ])

        assert exit_code == 0
        assert 'verified successfully' in capsys.readouterr().out
