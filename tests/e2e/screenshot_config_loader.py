"""
Screenshot Configuration Loader

Utilities for loading and parsing screenshot configuration from YAML files.
"""

import yaml
from pathlib import Path
from typing import Dict, List, Optional


class ScreenshotConfig:
    """
    Screenshot configuration container.

    Loads and provides access to screenshot definitions from YAML config.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the config loader.

        Args:
            config_path: Path to the YAML config file. If None, uses default.
        """
        if config_path is None:
            # Default to screenshot_config.yaml in the same directory
            config_path = Path(__file__).parent / 'screenshot_config.yaml'

        self.config_path = Path(config_path)
        self._config_data = None
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Screenshot config file not found: {self.config_path}"
            )

        with open(self.config_path, 'r') as f:
            self._config_data = yaml.safe_load(f)

        if not self._config_data:
            raise ValueError("Screenshot config file is empty")

    def get_all_screenshots(self) -> List[Dict]:
        """
        Get all screenshot definitions.

        Returns:
            List of screenshot definition dictionaries
        """
        return self._config_data.get('screenshots', [])

    def get_screenshot_by_name(self, name: str) -> Optional[Dict]:
        """
        Get a specific screenshot definition by name.

        Args:
            name: Screenshot name

        Returns:
            Screenshot definition dict or None if not found
        """
        for screenshot in self.get_all_screenshots():
            if screenshot.get('name') == name:
                return screenshot
        return None

    def get_screenshots_by_test(self, test_name: str) -> List[Dict]:
        """
        Get all screenshots associated with a specific test.

        Args:
            test_name: Test function name

        Returns:
            List of screenshot definitions for this test
        """
        return [
            screenshot for screenshot in self.get_all_screenshots()
            if screenshot.get('test') == test_name
        ]

    def get_screenshots_for_doc_file(self, doc_file: str) -> List[Dict]:
        """
        Get all screenshots that should be inserted into a specific doc file.

        Args:
            doc_file: Documentation file path (e.g., "README.md")

        Returns:
            List of screenshot definitions for this doc file
        """
        results = []
        for screenshot in self.get_all_screenshots():
            doc_files = screenshot.get('documentation_files', [])
            for doc in doc_files:
                if doc.get('file') == doc_file:
                    results.append({
                        **screenshot,
                        'doc_section': doc.get('section'),
                        'doc_caption': doc.get('caption')
                    })
        return results

    def get_config_value(self, key: str, default=None):
        """
        Get a configuration value from the config section.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        config_section = self._config_data.get('config', {})
        return config_section.get(key, default)

    def get_default_viewport(self) -> tuple:
        """Get the default viewport size as a tuple."""
        viewport = self.get_config_value('default_viewport', [1920, 1080])
        return tuple(viewport)

    def get_default_timeout(self) -> int:
        """Get the default timeout in milliseconds."""
        return self.get_config_value('default_timeout', 5000)

    def should_optimize_images(self) -> bool:
        """Check if image optimization is enabled."""
        return self.get_config_value('optimize_images', True)

    def get_optimization_quality(self) -> int:
        """Get the image optimization quality setting."""
        return self.get_config_value('optimization_quality', 85)

    def should_generate_metadata(self) -> bool:
        """Check if metadata generation is enabled."""
        return self.get_config_value('generate_metadata', True)

    def get_metadata_filename(self) -> str:
        """Get the metadata filename."""
        return self.get_config_value('metadata_filename', 'metadata.json')

    def count_screenshots(self) -> int:
        """Get the total number of screenshots defined."""
        return len(self.get_all_screenshots())

    def get_screenshots_by_category(self) -> Dict[str, List[Dict]]:
        """
        Group screenshots by documentation file.

        Returns:
            Dictionary mapping doc files to screenshot lists
        """
        categories = {}
        for screenshot in self.get_all_screenshots():
            doc_files = screenshot.get('documentation_files', [])
            for doc in doc_files:
                file_path = doc.get('file', 'uncategorized')
                if file_path not in categories:
                    categories[file_path] = []
                categories[file_path].append(screenshot)
        return categories

    def validate_config(self) -> tuple[bool, List[str]]:
        """
        Validate the configuration for completeness and correctness.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Check for screenshots section
        if 'screenshots' not in self._config_data:
            errors.append("Missing 'screenshots' section in config")
            return False, errors

        # Validate each screenshot
        required_fields = ['name', 'description', 'test', 'output']
        for i, screenshot in enumerate(self.get_all_screenshots()):
            for field in required_fields:
                if field not in screenshot:
                    errors.append(
                        f"Screenshot {i}: Missing required field '{field}'"
                    )

            # Check for documentation_files
            if 'documentation_files' not in screenshot:
                errors.append(
                    f"Screenshot '{screenshot.get('name', i)}': "
                    "Missing 'documentation_files'"
                )

        return len(errors) == 0, errors


def load_screenshot_config(config_path: Optional[str] = None) -> ScreenshotConfig:
    """
    Convenience function to load screenshot configuration.

    Args:
        config_path: Optional path to config file

    Returns:
        ScreenshotConfig instance
    """
    return ScreenshotConfig(config_path)
