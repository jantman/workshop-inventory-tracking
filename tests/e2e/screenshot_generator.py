"""
Screenshot Generator for Documentation

This module provides utilities for capturing, processing, and managing
screenshots for documentation purposes. It integrates with Playwright-based
e2e tests to generate consistent, high-quality screenshots.
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from PIL import Image
import io


class ScreenshotGenerator:
    """Utility class for capturing and managing documentation screenshots"""

    def __init__(self, page, output_dir='docs/images/screenshots'):
        """
        Initialize the screenshot generator.

        Args:
            page: Playwright page object
            output_dir: Base directory for screenshot output
        """
        self.page = page
        self.output_dir = Path(output_dir)
        self.metadata = {
            'generated_at': datetime.now().isoformat(),
            'screenshots': []
        }

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def capture_full_page(
        self,
        filename: str,
        wait_for_selector: Optional[str] = None,
        hide_selectors: Optional[List[str]] = None,
        wait_timeout: int = 5000
    ) -> Path:
        """
        Capture full page screenshot with optional element hiding.

        Args:
            filename: Output filename (relative to output_dir)
            wait_for_selector: Optional selector to wait for before capturing
            hide_selectors: Optional list of selectors to hide before capture
            wait_timeout: Timeout in milliseconds for wait_for_selector

        Returns:
            Path to the saved screenshot
        """
        # Wait for specific element if requested
        if wait_for_selector:
            self.page.wait_for_selector(wait_for_selector, timeout=wait_timeout)

        # Hide elements if requested
        hidden_elements = []
        if hide_selectors:
            for selector in hide_selectors:
                try:
                    elements = self.page.query_selector_all(selector)
                    for element in elements:
                        element.evaluate('el => el.style.display = "none"')
                        hidden_elements.append(element)
                except Exception:
                    # Element might not exist, continue
                    pass

        # Capture screenshot
        output_path = self.output_dir / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self.page.screenshot(path=str(output_path), full_page=True)

        # Restore hidden elements
        for element in hidden_elements:
            try:
                element.evaluate('el => el.style.display = ""')
            except Exception:
                pass

        # Optimize the image
        self._optimize_image(output_path)

        # Record metadata
        self._record_screenshot(filename, 'full_page', {
            'wait_for_selector': wait_for_selector,
            'hide_selectors': hide_selectors
        })

        return output_path

    def capture_element(
        self,
        selector: str,
        filename: str,
        padding: int = 10,
        wait_timeout: int = 5000
    ) -> Path:
        """
        Capture screenshot of specific element with padding.

        Args:
            selector: CSS selector for the element to capture
            filename: Output filename (relative to output_dir)
            padding: Padding around the element in pixels
            wait_timeout: Timeout in milliseconds for element

        Returns:
            Path to the saved screenshot
        """
        # Wait for element to be visible
        element = self.page.wait_for_selector(selector, timeout=wait_timeout)

        if not element:
            raise ValueError(f"Element not found: {selector}")

        # Get element bounding box
        box = element.bounding_box()
        if not box:
            raise ValueError(f"Element has no bounding box: {selector}")

        # Add padding
        clip = {
            'x': max(0, box['x'] - padding),
            'y': max(0, box['y'] - padding),
            'width': box['width'] + (2 * padding),
            'height': box['height'] + (2 * padding)
        }

        # Capture screenshot
        output_path = self.output_dir / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self.page.screenshot(path=str(output_path), clip=clip)

        # Optimize the image
        self._optimize_image(output_path)

        # Record metadata
        self._record_screenshot(filename, 'element', {
            'selector': selector,
            'padding': padding,
            'clip': clip
        })

        return output_path

    def capture_viewport(
        self,
        filename: str,
        viewport_size: Tuple[int, int] = (1920, 1080),
        wait_for_selector: Optional[str] = None,
        hide_selectors: Optional[List[str]] = None,
        full_page: bool = False
    ) -> Path:
        """
        Capture screenshot at specific viewport size.

        Args:
            filename: Output filename (relative to output_dir)
            viewport_size: Tuple of (width, height)
            wait_for_selector: Optional selector to wait for before capturing
            hide_selectors: Optional list of selectors to hide before capture
            full_page: Whether to capture full page or just viewport

        Returns:
            Path to the saved screenshot
        """
        # Set viewport size
        original_viewport = self.page.viewport_size
        self.page.set_viewport_size({
            'width': viewport_size[0],
            'height': viewport_size[1]
        })

        # Wait for specific element if requested
        if wait_for_selector:
            self.page.wait_for_selector(wait_for_selector)

        # Hide elements if requested
        hidden_elements = []
        if hide_selectors:
            for selector in hide_selectors:
                try:
                    elements = self.page.query_selector_all(selector)
                    for element in elements:
                        element.evaluate('el => el.style.display = "none"')
                        hidden_elements.append(element)
                except Exception:
                    pass

        # Capture screenshot
        output_path = self.output_dir / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self.page.screenshot(path=str(output_path), full_page=full_page)

        # Restore hidden elements
        for element in hidden_elements:
            try:
                element.evaluate('el => el.style.display = ""')
            except Exception:
                pass

        # Restore original viewport
        if original_viewport:
            self.page.set_viewport_size(original_viewport)

        # Optimize the image
        self._optimize_image(output_path)

        # Record metadata
        self._record_screenshot(filename, 'viewport', {
            'viewport_size': viewport_size,
            'full_page': full_page,
            'wait_for_selector': wait_for_selector,
            'hide_selectors': hide_selectors
        })

        return output_path

    def _optimize_image(self, image_path: Path, quality: int = 85) -> None:
        """
        Optimize PNG file size while maintaining quality.

        Args:
            image_path: Path to the image file
            quality: Quality level (not used for PNG, but reserved for future)
        """
        try:
            # Open image
            img = Image.open(image_path)

            # Convert RGBA to RGB if needed (for smaller file size)
            if img.mode == 'RGBA':
                # Create white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])  # Use alpha channel as mask
                img = background

            # Save with optimization
            img.save(image_path, 'PNG', optimize=True)

        except Exception as e:
            # If optimization fails, just log and continue
            print(f"Warning: Could not optimize image {image_path}: {e}")

    def _record_screenshot(
        self,
        filename: str,
        capture_type: str,
        details: Dict
    ) -> None:
        """
        Record screenshot metadata.

        Args:
            filename: Screenshot filename
            capture_type: Type of capture (full_page, element, viewport)
            details: Additional details about the capture
        """
        self.metadata['screenshots'].append({
            'filename': filename,
            'capture_type': capture_type,
            'timestamp': datetime.now().isoformat(),
            'details': details
        })

    def save_metadata(self, filename: str = 'metadata.json') -> Path:
        """
        Save JSON metadata about generated screenshots.

        Args:
            filename: Metadata filename

        Returns:
            Path to the saved metadata file
        """
        metadata_path = self.output_dir / filename

        with open(metadata_path, 'w') as f:
            json.dump(self.metadata, f, indent=2)

        return metadata_path

    def get_screenshot_count(self) -> int:
        """Get the number of screenshots captured in this session."""
        return len(self.metadata['screenshots'])

    def get_metadata(self) -> Dict:
        """Get the current metadata dictionary."""
        return self.metadata.copy()
