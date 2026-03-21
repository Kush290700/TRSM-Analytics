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
            # Handle common variations like "Arial Black.ttf" or "arialbd.ttf" for Arial Black
            base_name = name.split('-')[0].strip() # e.g., 'Montserrat' from 'Montserrat-ExtraBold'
            for ext in ['.ttf', '.otf']:
                # Try exact name first
                font_path = os.path.join(font_dir, name + ext)
                if os.path.exists(font_path):
                    return font_path
                # Try common variations
                font_path = os.path.join(font_dir, base_name.replace(" ", "") + ext) # e.g., ArialBlack.ttf
                if os.path.exists(font_path):
                    return font_path
                font_path = os.path.join(font_dir, base_name.replace(" ", "").lower() + ext) # e.g., arialblack.ttf
                if os.path.exists(font_path):
                    return font_path
                font_path = os.path.join(font_dir, name.replace(" ", "") + ext) # e.g., Montserrat-ExtraBold.ttf
                if os.path.exists(font_path):
                    return font_path
                font_path = os.path.join(font_dir, name.replace(" ", "").lower() + ext) # e.g., montserrat-extrabold.ttf
                if os.path.exists(font_path):
                    return font_path

    return None

def generate_trsm_netflix_favicon(output_path):
    # Canvas size
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 255)) # Deep Black background
    draw = ImageDraw.Draw(img)

    # Text content
    text = "TRSM"
    text_color = (229, 9, 20, 255) # Netflix Red (#E50914)

    # Font logic
    font_candidates = ['Impact', 'Arial Black', 'Montserrat-ExtraBold', 'Roboto-Black', 'Verdana-Bold']
    font_file = find_font(font_candidates)

    selected_font = None
    if font_file:
        print(f"Using font: {os.path.basename(font_file)}")
        # Dynamic Sizing: Start with a large font size and adjust
        font_size = 100
        # Check initial font size
        try:
            selected_font = ImageFont.truetype(font_file, font_size)
            # Find the largest font size that fits 90-95% of the canvas width
            while True:
                # Check current size
                bbox = draw.textbbox((0, 0), text, font=selected_font)
                text_width = bbox[2] - bbox[0]

                if text_width < size * 0.90: # If too small, try increasing
                    test_font_size = font_size + 1
                    try:
                        test_font = ImageFont.truetype(font_file, test_font_size)
                        test_bbox = draw.textbbox((0, 0), text, font=test_font)
                        test_text_width = test_bbox[2] - test_bbox[0]
                        if test_text_width <= size * 0.95: # Increase if it's still within 95%
                            font_size = test_font_size
                            selected_font = test_font
                        else: # Can't increase more without exceeding 95%
                            break
                    except IOError: # Should not happen if font_file is valid
                        break
                elif text_width > size * 0.95: # If too large, decrease
                    font_size -= 1
                    if font_size <= 10: # Safety break
                        break
                    selected_font = ImageFont.truetype(font_file, font_size)
                else: # Optimal size found (between 90% and 95%)
                    break
        except IOError:
            print(f"Error loading font file {font_file}. Using default font.")
            selected_font = ImageFont.load_default()
            font_size = 80 # A reasonable size for default font
    else:
        print("Warning: No preferred fonts found. Using default PIL font.")
        selected_font = ImageFont.load_default()
        font_size = 80 # A reasonable size for default font


    print(f"Final font size: {font_size}")

    # Re-calculate text dimensions with the final font
    bbox = draw.textbbox((0, 0), text, font=selected_font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Calculate position to center the text
    x = (size - text_width) // 2
    y = (size - text_height) // 2

    draw.text((x, y), text, font=selected_font, fill=text_color)

    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    img.save(output_path)
    print(f"Successfully generated new favicon at {output_path}")

if __name__ == "__main__":
    output_favicon_path = "app/static/images/favicon_trsm_netflix.png"
    generate_trsm_netflix_favicon(output_favicon_path)
