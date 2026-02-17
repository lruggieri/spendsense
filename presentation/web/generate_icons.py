#!/usr/bin/env python3
"""
Generate PWA icons for the SpendSense app.
Creates icons in multiple sizes with a simple design.
"""

from PIL import Image, ImageDraw, ImageFont
import os

# Icon sizes required for PWA
SIZES = [72, 96, 128, 144, 152, 192, 384, 512]

# Colors matching the app theme
BACKGROUND_COLOR = '#0f3460'  # Theme color from manifest
TEXT_COLOR = '#ffffff'
ACCENT_COLOR = '#16c79a'

def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def create_icon(size):
    """Create a single icon with the given size"""
    # Create image with background
    img = Image.new('RGB', (size, size), hex_to_rgb(BACKGROUND_COLOR))
    draw = ImageDraw.Draw(img)

    # Draw a simple design - currency symbol or initials
    # Draw a circle in the center
    margin = size // 6
    circle_bbox = [margin, margin, size - margin, size - margin]
    draw.ellipse(circle_bbox, fill=hex_to_rgb(ACCENT_COLOR))

    # Draw currency symbol ($) or "ET" text
    try:
        # Try to use a system font
        font_size = size // 2
        try:
            # Try different font paths for different systems
            font_paths = [
                '/System/Library/Fonts/Helvetica.ttc',  # macOS
                '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',  # Linux
                'C:\\Windows\\Fonts\\arial.ttf',  # Windows
            ]
            font = None
            for font_path in font_paths:
                if os.path.exists(font_path):
                    font = ImageFont.truetype(font_path, font_size)
                    break

            if font is None:
                font = ImageFont.load_default()
        except:
            font = ImageFont.load_default()

        text = "$"

        # Get text bounding box for centering
        if hasattr(font, 'getbbox'):
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        else:
            # Fallback for older Pillow versions
            text_width, text_height = draw.textsize(text, font=font)

        # Center the text
        x = (size - text_width) // 2
        y = (size - text_height) // 2 - size // 20  # Slight adjustment

        draw.text((x, y), text, fill=hex_to_rgb(BACKGROUND_COLOR), font=font)
    except Exception as e:
        print(f"Warning: Could not add text to icon: {e}")

    return img

def main():
    """Generate all icon sizes"""
    # Create icons directory
    icons_dir = os.path.join('static', 'icons')
    os.makedirs(icons_dir, exist_ok=True)

    print("Generating PWA icons...")
    for size in SIZES:
        icon = create_icon(size)
        filename = f'icon-{size}x{size}.png'
        filepath = os.path.join(icons_dir, filename)
        icon.save(filepath, 'PNG', optimize=True)
        print(f"  ✓ Created {filename} ({size}x{size})")

    print(f"\nAll icons generated successfully in {icons_dir}/")
    print("Icons are optimized and ready for PWA installation.")

if __name__ == '__main__':
    main()
