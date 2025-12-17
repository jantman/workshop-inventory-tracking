"""
Unit Tests for Screenshot Infrastructure

Tests for screenshot generator and configuration loader.
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from tests.e2e.screenshot_generator import ScreenshotGenerator
from tests.e2e.screenshot_config_loader import ScreenshotConfig, load_screenshot_config


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
