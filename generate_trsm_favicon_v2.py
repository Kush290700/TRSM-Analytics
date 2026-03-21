from PIL import Image, ImageDraw, ImageFont
import os
import platform

def find_font(font_names):
    """Attempts to find a font file from a list of font names across common system paths."""
    # Common font directories
    font_dirs = []
    if platform.system() == "Windows":
        font_dirs = [
            os.environ.get("WINDIR", "C:\\Windows") + "\\Fonts",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft\\Windows\\Fonts")
        ]
    elif platform.system() == "Darwin": # macOS
        font_dirs = [
            "/Library/Fonts",
            "/System/Library/Fonts",
            os.path.expanduser("~/Library/Fonts")
        ]
    else: # Linux/Unix
        font_dirs = [
            "/usr/share/fonts",
            "/usr/local/share/fonts",
            os.path.expanduser("~/.fonts")
        ]

    for name in font_names:
        for font_dir in font_dirs:
            for ext in ['.ttf', '.otf']:
                font_path = os.path.join(font_dir, name + ext)
                if os.path.exists(font_path):
                    return font_path
    return None

def generate_trsm_favicon_v2(output_path):
    # Canvas size
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 255)) # Deep Black background
    draw = ImageDraw.Draw(img)

    # Add a 4-pixel White border
    border_color = (255, 255, 255, 255) # White
    border_width = 4
    for i in range(border_width):
        draw.rectangle([i, i, size - 1 - i, size - 1 - i], outline=border_color)

    # Text content
    text = "TRSM"
    text_color = (255, 255, 255, 255) # White color

    # Font logic
    font_candidates = ['Impact', 'Arial Black', 'Verdana-Bold', 'Tahoma-Bold', 'DejaVuSans-Bold']
    font_file = find_font(font_candidates)

    if font_file:
        print(f"Using font: {os.path.basename(font_file)}")
        # Dynamic Sizing: Start with a large font size and adjust
        font_size = 100
        font = ImageFont.truetype(font_file, font_size)

        # Loop to find the largest font size that fits 90% of the canvas width
        while True:
            # Check if increasing font size makes text too wide
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            if text_width > size * 0.9:
                font_size -= 1 # Reduce size if it's too wide
                if font_size <= 10: # Safety break
                    break
                font = ImageFont.truetype(font_file, font_size)
            else:
                # Try to increase font size
                test_font = ImageFont.truetype(font_file, font_size + 1)
                test_bbox = draw.textbbox((0, 0), text, font=test_font)
                test_text_width = test_bbox[2] - test_bbox[0]
                if test_text_width <= size * 0.9:
                    font_size += 1
                    font = test_font
                else:
                    break # Optimal size found

        print(f"Final font size: {font_size}")

    else:
        print("Warning: No preferred fonts found. Using default PIL font.")
        font = ImageFont.load_default()
        # For default font, resizing is not directly supported by truetype,
        # so we'll pick a fixed size that looks reasonable for default.
        # This part might require manual adjustment for optimal appearance with default.
        font_size = 80 # Adjust as needed for default font
        # No direct resize for default font, so just set a size if possible
        # For ImageFont.load_default(), font size is fixed.
        # We might need a different approach or accept it smaller.
        # For simplicity, we proceed with the default size, knowing it won't be dynamic.

    # Re-calculate text dimensions with the final font
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Calculate position to center the text
    x = (size - text_width) // 2
    y = (size - text_height) // 2

    draw.text((x, y), text, font=font, fill=text_color)

    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    img.save(output_path)
    print(f"Successfully generated new favicon at {output_path}")

if __name__ == "__main__":
    output_favicon_path = "app/static/images/favicon_trsm_v2.png"
    generate_trsm_favicon_v2(output_favicon_path)
