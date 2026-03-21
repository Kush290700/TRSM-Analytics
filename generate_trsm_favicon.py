from PIL import Image, ImageDraw, ImageFont
import os

def generate_trsm_favicon(output_path):
    # Canvas size
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 255)) # Black background
    draw = ImageDraw.Draw(img)

    # Text content
    text = "TRSM"
    text_color = (255, 255, 255, 255) # White color

    # Attempt to load bold sans-serif fonts
    try:
        font_path = "arialbd.ttf" # Arial Bold
        font_size = 150 # Initial guess for font size
        font = ImageFont.truetype(font_path, font_size)
    except IOError:
        try:
            font_path = "calibrib.ttf" # Calibri Bold
            font_size = 150
            font = ImageFont.truetype(font_path, font_size)
        except IOError:
            # Fallback to default PIL font if specific fonts are not found
            print("Warning: Specific fonts (arialbd.ttf, calibrib.ttf) not found. Using default PIL font.")
            font_size = 100 # Default font usually needs a smaller size
            font = ImageFont.load_default()

    # Adjust font size to fit and center the text
    # This is an iterative process to find the best fit
    while True:
        if font.getbbox(text)[2] >= size * 0.9 or font.getbbox(text)[3] >= size * 0.9:
            font_size -= 5
            if font_size <= 10: # Prevent infinite loop if text is too large or font.getbbox() is misbehaving
                break
            try:
                if 'font_path' in locals():
                    font = ImageFont.truetype(font_path, font_size)
                else:
                    # For default font, resizing is not directly supported this way
                    # and it's less critical for precise sizing.
                    break
            except IOError:
                break # Should not happen if font was already loaded successfully
        else:
            if font.getbbox(text)[2] < size * 0.75 and font.getbbox(text)[3] < size * 0.75: # Try to make it bigger
                font_size += 5
                try:
                    if 'font_path' in locals():
                        font = ImageFont.truetype(font_path, font_size)
                    else:
                        break
                except IOError:
                    break
            else:
                break


    # Get text bounding box for centering
    # `getbbox` returns (left, top, right, bottom)
    text_bbox = draw.textbbox((0,0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]

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
    output_favicon_path = "app/static/images/favicon_trsm.png"
    generate_trsm_favicon(output_favicon_path)
