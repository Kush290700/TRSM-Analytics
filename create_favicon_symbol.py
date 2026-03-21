from PIL import Image
import os

def create_favicon_symbol(input_path, output_path):
    try:
        original_logo = Image.open(input_path).convert("RGBA")
    except FileNotFoundError:
        print(f"Error: Input file not found at {input_path}")
        return
    except Exception as e:
        print(f"Error opening image: {e}")
        return

    # Define the crop box: (left, upper, right, lower)
    # Keeping only the left square portion of 120x120 pixels
    # Based on the original logo dimensions 420x120
    crop_box = (0, 0, 120, 120)
    cropped_logo = original_logo.crop(crop_box)

    # Resize to 256x256 for high quality
    resized_logo = cropped_logo.resize((256, 256), Image.Resampling.LANCZOS)

    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    resized_logo.save(output_path)
    print(f"Successfully created favicon symbol at {output_path}")

if __name__ == "__main__":
    input_logo_path = "app/static/images/logo.png"
    output_favicon_symbol_path = "app/static/images/favicon_symbol.png"
    create_favicon_symbol(input_logo_path, output_favicon_symbol_path)
