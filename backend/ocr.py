from PIL import Image
import pytesseract
import io


def extract_text_from_image(file_bytes: bytes) -> str:
    """
    Extract text from image files like PNG, JPG, JPEG, WEBP.
    """
    image = Image.open(io.BytesIO(file_bytes))

    # Convert image to RGB for better compatibility
    image = image.convert("RGB")

    text = pytesseract.image_to_string(image)

    return text.strip()