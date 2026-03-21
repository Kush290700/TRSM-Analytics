import numpy as np
from PIL import Image, ImageDraw, ImageFont
import os

def find_font(font_names):
    """
    Attempts to find a suitable font from a list of preferred font names.
    """
    # Common font paths for Windows, macOS, and Linux
    common_font_paths = [
        # Windows
        os.path.join(os.environ.get("SystemRoot", "C:/Windows"), "Fonts"),
        # macOS
        "/System/Library/Fonts",
        "/Library/Fonts",
        "~/Library/Fonts",
        # Linux
        "/usr/share/fonts",
        "/usr/local/share/fonts",
    ]

    for font_name in font_names:
        # Try system-wide search
        try:
            # ImageFont.truetype can often find fonts by name on some systems
            # However, direct path is more reliable.
            # We'll try to use a generic font name first.
            font = ImageFont.truetype(font_name, 10) # Test with a small size
            return font_name # Return the name if it works
        except IOError:
            pass

        # Try searching in common font directories
        for font_path_base in common_font_paths:
            full_path = os.path.join(os.path.expanduser(font_path_base), font_name + ".ttf")
            if os.path.exists(full_path):
                try:
                    font = ImageFont.truetype(full_path, 10) # Test with a small size
                    return full_path # Return the full path
                except IOError:
                    pass
            full_path = os.path.join(os.path.expanduser(font_path_base), font_name + ".otf")
            if os.path.exists(full_path):
                try:
                    font = ImageFont.truetype(full_path, 10) # Test with a small size
                    return full_path # Return the full path
                except IOError:
                    pass

    return None # No suitable font found

def generate_gradient_favicon():
    # Canvas dimensions
    width, height = 256, 256
    text_to_render = "TRSM"
    output_path = "app/static/images/favicon_trsm_gradient.png"

    # 1. Canvas: Deep Black background
    img = Image.new("RGB", (width, height), "#000000")
    draw = ImageDraw.Draw(img)

    # Preferred bold sans-serif fonts
    preferred_fonts = [
        "Impact", "Arial Black", "Roboto-Black", "DejaVuSans-Bold",
        "sans-serif-bold", "LiberationSans-Bold", "NotoSans-Bold",
        "Helvetica-Bold", "Verdana-Bold"
    ]
    
    font_file = find_font(preferred_fonts)

    if not font_file:
        print("Warning: Could not find a preferred bold sans-serif font. Falling back to default Pillow font.")
        print("You might need to install a font like 'Impact', 'Arial Black', or 'Roboto Black' for better results.")
        # Fallback to default font if none found, though it might not be bold enough
        font = ImageFont.load_default()
        # For default font, we might not be able to dynamically size as effectively
        # Let's just pick a large size and hope for the best if no TTF is found
        font_size = 100 
        font = ImageFont.load_default(size=font_size)
    else:
        # 3. Dynamic Sizing
        font_size = 1
        # Target width for the text: 92% of canvas width
        target_text_width = int(width * 0.92)

        # Iterate to find the maximum font size that fits the target width
        while True:
            try:
                current_font = ImageFont.truetype(font_file, font_size)
                bbox = draw.textbbox((0, 0), text_to_render, font=current_font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]

                if text_width >= target_text_width or text_height >= height * 0.92:
                    font_size -= 1 # Go back to the last size that fit
                    break
                font_size += 1
            except IOError: # Catch potential font loading issues during sizing
                print(f"Error loading font '{font_file}' at size {font_size}. Using last successful size.")
                font_size -= 1
                break
            except Exception as e:
                print(f"An unexpected error occurred during font sizing: {e}")
                font_size -= 1
                break
        
        if font_size <= 0: # Ensure font_size is at least 1
            font_size = 1
        font = ImageFont.truetype(font_file, font_size)

    # Re-calculate text dimensions with the final font size
    bbox = draw.textbbox((0, 0), text_to_render, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Calculate position to center the text
    text_x = (width - text_width) // 2 - bbox[0] # Adjust for potential negative bbox[0]
    text_y = (height - text_height) // 2 - bbox[1] # Adjust for potential negative bbox[1]

    # 4. Text Mask Creation
    mask_img = Image.new("L", (width, height), 0) # Black background for mask
    mask_draw = ImageDraw.Draw(mask_img)
    mask_draw.text((text_x, text_y), text_to_render, font=font, fill=255) # White text for mask

    # 5. Gradient Generation
    gradient = Image.new("RGB", (width, height), color=0)
    
    # Bright Cinematic Red (e.g., #FF2424)
    r1, g1, b1 = (255, 36, 36) 
    # Deep Crimson Red (e.g., #990000)
    r2, g2, b2 = (153, 0, 0)

    for y in range(height):
        r = int(r1 + (r2 - r1) * (y / height))
        g = int(g1 + (g2 - g1) * (y / height))
        b = int(b1 + (b2 - b1) * (y / height))
        draw_gradient = ImageDraw.Draw(gradient)
        draw_gradient.line([(0, y), (width, y)], fill=(r, g, b))

    # 6. Composition: Apply gradient using the text mask
    # The mask image (L mode) is used directly as the alpha channel when pasting
    img.paste(gradient, (0, 0), mask_img)

    # 7. Output
    img.save(output_path)
    print(f"Favicon generated and saved to {output_path}")

if __name__ == "__main__":
    generate_gradient_favicon()
