from PIL import Image
import os

def create_square_logo(input_path, output_path):
    try:
        original_logo = Image.open(input_path).convert("RGBA")
    except FileNotFoundError:
        print(f"Error: Input file not found at {input_path}")
        return
    except Exception as e:
        print(f"Error opening image: {e}")
        return

    original_width, original_height = original_logo.size

    if original_width != 420 or original_height != 120:
        print(f"Warning: Expected original logo dimensions 420x120, but found {original_width}x{original_height}. "
              "Proceeding with centering logic based on 420x120 assumption.")

    # Create a new square image with transparent background
    square_dim = 420
    square_logo = Image.new("RGBA", (square_dim, square_dim), (0, 0, 0, 0)) # Fully transparent

    # Calculate centering position
    # The image is 420x120, the canvas is 420x420.
    # We want to center the 120px height in the 420px height.
    # (420 - 120) / 2 = 150
    paste_x = 0  # Centered horizontally since widths are the same
    paste_y = (square_dim - original_height) // 2

    square_logo.paste(original_logo, (paste_x, paste_y), original_logo)

    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    square_logo.save(output_path)
    print(f"Successfully created square logo at {output_path}")

if __name__ == "__main__":
    input_logo_path = "app/static/images/logo.png"
    output_square_logo_path = "app/static/images/logo_square.png"
    create_square_logo(input_logo_path, output_square_logo_path)
