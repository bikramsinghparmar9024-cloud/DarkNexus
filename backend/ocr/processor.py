"""
Tesseract OCR Processor for Drug Intelligence.
Extracts text from screenshots of encrypted chats, marketplace listings,
and images of drug packaging / labels / purity certificates.
"""

from typing import List, Optional
import io
import logging
import os
import shutil

from PIL import Image, ImageEnhance, ImageFilter

from config import settings

logger = logging.getLogger("ocr_processor")

try:
    import pytesseract
except ImportError:
    pytesseract = None

# The Windows installer does not add itself to PATH, so a working engine still
# looks missing. These are the standard install locations.
_WINDOWS_CANDIDATES = [
    "C:/Program Files/Tesseract-OCR/tesseract.exe",
    "C:/Program Files (x86)/Tesseract-OCR/tesseract.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""),
                 "Programs", "Tesseract-OCR", "tesseract.exe"),
]


def find_tesseract() -> Optional[str]:
    """
    Locate the Tesseract binary.

    Order: explicit configuration, then PATH, then the standard install
    locations. Without this the module silently returned empty strings for
    every image, which is indistinguishable from an image containing no text.
    """
    if settings.TESSERACT_CMD and os.path.exists(settings.TESSERACT_CMD):
        return settings.TESSERACT_CMD

    on_path = shutil.which("tesseract")
    if on_path:
        return on_path

    for candidate in _WINDOWS_CANDIDATES:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


class OCRProcessor:
    """Extracts text and drug brand labels from images."""

    def __init__(self, tesseract_cmd: Optional[str] = None):
        self.engine_path: Optional[str] = None
        if pytesseract:
            self.engine_path = tesseract_cmd or find_tesseract()
            if self.engine_path:
                pytesseract.pytesseract.tesseract_cmd = self.engine_path
                logger.info("Tesseract OCR engine found at %s", self.engine_path)
            else:
                logger.warning(
                    "Tesseract binary not found. OCR will return empty text for "
                    "every image. Install it, or set TESSERACT_CMD to its path.")

    @property
    def available(self) -> bool:
        """True when an OCR engine is actually usable."""
        return bool(pytesseract and self.engine_path)

    def extract_text_from_bytes(self, image_bytes: bytes) -> str:
        """Preprocess an image and extract any text it contains."""
        if not self.available:
            return ""

        try:
            image = Image.open(io.BytesIO(image_bytes))
            # Preprocessing for higher OCR accuracy
            # 1. Convert to grayscale
            gray = image.convert("L")
            # 2. Increase contrast
            enhancer = ImageEnhance.Contrast(gray)
            enhanced = enhancer.enhance(1.8)
            # 3. Median filter to denoise
            denoised = enhanced.filter(ImageFilter.MedianFilter())

            # Perform OCR (support English + Hindi/Punjabi if language packs installed)
            text = pytesseract.image_to_string(denoised, config="--psm 6")
            return text.strip()

        except Exception as e:
            logger.error(f"OCR processing failed: {e}")
            return ""


ocr_processor = OCRProcessor()
