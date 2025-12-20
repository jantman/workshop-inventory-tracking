"""
Create Sample Images for Screenshot Testing

This script generates simple placeholder images for photo upload demonstrations.
"""

from PIL import Image, ImageDraw, ImageFont
import os
from pathlib import Path


def create_sample_image(
    filename: str,
    size: tuple = (800, 600),
    color: str = 'lightblue',
    text: str = None
):
    """
    Create a sample image with a solid color and optional text.

    Args:
        filename: Output filename
        size: Image size (width, height)
        color: Background color
        text: Optional text to draw on the image
    """
    # Create image with solid color
    img = Image.new('RGB', size, color=color)

    if text:
        draw = ImageDraw.Draw(img)
        # Try to use a font, fall back to default if not available
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48)
        except:
            font = ImageFont.load_default()

        # Calculate text position (centered)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        position = ((size[0] - text_width) // 2, (size[1] - text_height) // 2)

        # Draw text
        draw.text(position, text, fill='black', font=font)

    return img


def main():
    """Create all sample images for testing."""
    # Get the fixtures/images directory
    script_dir = Path(__file__).parent
    images_dir = script_dir / 'images'
    images_dir.mkdir(exist_ok=True)

    # Create sample images for metal parts
    samples = [
        {
            'filename': 'steel_rod_sample.jpg',
            'color': 'slategray',
            'text': 'Steel Rod\n1018 CR'
        },
        {
            'filename': 'aluminum_tube_sample.jpg',
            'color': 'lightgray',
            'text': 'Aluminum Tube\n6061-T6'
        },
        {
            'filename': 'brass_rod_sample.jpg',
            'color': 'gold',
            'text': 'Brass Rod\n360'
        },
        {
            'filename': 'steel_plate_sample.jpg',
            'color': 'dimgray',
            'text': 'Steel Plate\nA36'
        },
        {
            'filename': 'aluminum_plate_sample.jpg',
            'color': 'silver',
            'text': 'Aluminum Plate\n7075-T651'
        },
    ]

    for sample in samples:
        img = create_sample_image(
            filename=sample['filename'],
            color=sample['color'],
            text=sample['text']
        )
        output_path = images_dir / sample['filename']
        img.save(output_path, 'JPEG', quality=85)
        print(f"Created: {output_path}")

    # Create a PDF sample for PDF photo testing
    # Simple colored image that can represent a document/spec sheet
    pdf_img = create_sample_image(
        filename='spec_sheet.pdf',
        size=(612, 792),  # Letter size in pixels at 72 DPI
        color='white',
        text='Material\nSpecification\nSheet'
    )
    pdf_output = images_dir / 'spec_sheet_preview.jpg'
    pdf_img.save(pdf_output, 'JPEG', quality=85)
    print(f"Created: {pdf_output}")

    print("\nAll sample images created successfully!")


if __name__ == '__main__':
    main()
