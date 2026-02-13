# import json
# import os
# from pathlib import Path
# from typing import Optional
# import logging
# import subprocess
# import tempfile
#
# # Get logger (logging configured in main)
# logger = logging.getLogger(__name__)
#
# # RAW OCR TEXT IS DISCARDED AFTER PROCESSING
# # ONLY EXTRACTED DATA IS STORED
#
# # Disable OneDNN/MKLDNN to avoid "OneDnnContext does not have the input Filter" on some Windows/CPU setups
# os.environ.setdefault("FLAGS_use_mkldnn", "0")
#
# # Try importing PaddleOCR
# try:
#     from paddleocr import PaddleOCR
#
#     PADDLEOCR_AVAILABLE = True
#     logger.info("PaddleOCR module imported successfully")
# except ImportError as e:
#     PADDLEOCR_AVAILABLE = False
#     logger.warning(f"PaddleOCR import failed: {e}. Will try Tesseract as fallback.")
#
# # Try importing pytesseract (fallback)
# try:
#     import pytesseract
#     from PIL import Image
#
#     PYTESSERACT_AVAILABLE = True
#     logger.info("Pytesseract module imported successfully")
#
#     # Check if Tesseract binary is available (pytesseract can be installed but binary missing)
#     try:
#         pytesseract.get_tesseract_version()
#         logger.info("Tesseract binary is available and accessible")
#     except pytesseract.TesseractNotFoundError:
#         logger.warning("⚠ WARNING: pytesseract Python library is installed, but Tesseract binary is not found in PATH")
#         logger.warning("  Install Tesseract binary: apt-get install tesseract-ocr (Ubuntu/Debian) or yum install tesseract (CentOS/RHEL)")
#     except Exception as e:
#         logger.warning(f"Could not verify Tesseract binary: {e}")
# except ImportError as e:
#     PYTESSERACT_AVAILABLE = False
#     logger.warning(f"Pytesseract import failed: {e}")
#
# # Global OCR instance to avoid reinitialization
# _ocr_instance = None
# # Set to True after first Paddle OneDNN/runtime error so we skip Paddle for rest of process
# _paddle_ocr_disabled = False
#
#
# def get_ocr_instance():
#     """Get or create OCR instance (lazy loading)"""
#     global _ocr_instance
#     if _ocr_instance is None and PADDLEOCR_AVAILABLE:
#         try:
#             logger.info("Initializing PaddleOCR...")
#             _ocr_instance = PaddleOCR(use_angle_cls=True, lang='en')
#             logger.info("PaddleOCR initialized successfully")
#         except Exception as e:
#             logger.error(f"Failed to initialize PaddleOCR: {e}")
#             _ocr_instance = None
#     return _ocr_instance
#
#
# def extract_text_paddle(image_path: str) -> str:
#     """Extract text from image using PaddleOCR"""
#     global _paddle_ocr_disabled
#     if not PADDLEOCR_AVAILABLE:
#         logger.warning("PaddleOCR not available, skipping PaddleOCR extraction")
#         return ""
#     if _paddle_ocr_disabled:
#         return ""
#
#     try:
#         logger.info(f"Attempting PaddleOCR extraction from: {image_path}")
#         ocr = get_ocr_instance()
#
#         if ocr is None:
#             logger.error("OCR instance initialization failed")
#             return ""
#
#         result = ocr.ocr(image_path, cls=True)
#
#         if not result or not result[0]:
#             logger.warning(f"No text detected by PaddleOCR in: {image_path}")
#             return ""
#
#         text = ""
#         for line in result:
#             if line:
#                 for word_info in line:
#                     # word_info structure: [bbox, (text, confidence)]
#                     if len(word_info) >= 2:
#                         text += word_info[1][0] + " "
#
#         cleaned_text = text.strip()
#         logger.info(f"PaddleOCR: Successfully extracted {len(cleaned_text)} characters")
#         return cleaned_text
#     except Exception as e:
#         err_str = str(e)
#         if "OneDnnContext" in err_str or "fused_conv2d" in err_str:
#             _paddle_ocr_disabled = True
#             logger.warning("PaddleOCR OneDNN backend failed; using Tesseract only for this process.")
#             return ""
#         logger.error(f"PaddleOCR extraction error: {str(e)}", exc_info=True)
#         return ""
#
#
# def extract_text_tesseract(image_path: str) -> str:
#     """Extract text from image using Pytesseract (fallback)"""
#     if not PYTESSERACT_AVAILABLE:
#         logger.warning("Pytesseract not available, skipping Tesseract extraction")
#         return ""
#
#     try:
#         logger.info(f"Attempting Pytesseract extraction from: {image_path}")
#         image = Image.open(image_path)
#         text = pytesseract.image_to_string(image)
#
#         if not text or len(text.strip()) < 10:
#             logger.warning(f"Tesseract extracted minimal text from: {image_path}")
#             return text.strip()
#
#         logger.info(f"Tesseract: Successfully extracted {len(text)} characters")
#         return text.strip()
#     except pytesseract.TesseractNotFoundError as e:
#         error_msg = str(e)
#         logger.error("=" * 80)
#         logger.error("✗ CRITICAL: Tesseract binary not found!")
#         logger.error(f"  Error: {error_msg}")
#         logger.error("")
#         logger.error("  SOLUTION: Install Tesseract OCR binary:")
#         logger.error("    Ubuntu/Debian: sudo apt-get install tesseract-ocr")
#         logger.error("    CentOS/RHEL:   sudo yum install tesseract")
#         logger.error("    macOS:         brew install tesseract")
#         logger.error("")
#         logger.error("  After installation, verify:")
#         logger.error("    tesseract --version")
#         logger.error("")
#         logger.error("  NOTE: pytesseract (Python library) is installed, but the")
#         logger.error("        Tesseract binary executable is missing from PATH.")
#         logger.error("=" * 80)
#         return ""
#     except Exception as e:
#         error_msg = str(e)
#         logger.error(f"Pytesseract extraction error: {error_msg}")
#         # Check if it's a PATH issue
#         if "tesseract is not installed" in error_msg.lower() or "not in your path" in error_msg.lower():
#             logger.error("=" * 80)
#             logger.error("✗ CRITICAL: Tesseract binary not found in PATH!")
#             logger.error("")
#             logger.error("  SOLUTION: Install Tesseract OCR binary:")
#             logger.error("    Ubuntu/Debian: sudo apt-get install tesseract-ocr")
#             logger.error("    CentOS/RHEL:   sudo yum install tesseract")
#             logger.error("    macOS:         brew install tesseract")
#             logger.error("")
#             logger.error("  After installation, verify:")
#             logger.error("    tesseract --version")
#             logger.error("=" * 80)
#         return ""
#
#
# def extract_text_from_image(image_path: str) -> str:
#     """Extract text from image using multiple OCR methods"""
#     logger.info(f"=== Starting OCR extraction for image ===")
#     logger.info(f"Image path: {image_path}")
#
#     # Verify file exists
#     if not os.path.exists(image_path):
#         logger.error(f"Image file does not exist: {image_path}")
#         return ""
#
#     file_size = os.path.getsize(image_path)
#     logger.info(f"Image file size: {file_size} bytes")
#
#     if file_size == 0:
#         logger.error(f"Image file is empty: {image_path}")
#         return ""
#
#     # Try PaddleOCR first
#     logger.info("Attempting OCR extraction with PaddleOCR...")
#     text = extract_text_paddle(image_path)
#     if text and len(text) > 50:
#         logger.info(f"PaddleOCR extraction successful: {len(text)} characters extracted")
#         return text
#     elif text:
#         logger.warning(f"PaddleOCR extracted minimal text ({len(text)} chars), trying Tesseract...")
#
#     # Fallback to Tesseract
#     logger.info("Attempting OCR extraction with Tesseract (fallback)...")
#     text = extract_text_tesseract(image_path)
#     if text and len(text) > 50:
#         logger.info(f"Tesseract extraction successful: {len(text)} characters extracted")
#         return text
#     elif text:
#         logger.warning(f"Tesseract extracted minimal text ({len(text)} chars)")
#
#     # If both fail, return combined results if any text was extracted
#     if text:
#         logger.warning(f"Returning minimal OCR results: {len(text)} characters")
#         return text
#
#     logger.error("All OCR methods failed to extract sufficient text from image")
#     logger.error(f"File path: {image_path}, File exists: {os.path.exists(image_path)}, File size: {file_size}")
#     return ""
#
#
# def extract_text_from_pdf(pdf_path: str) -> str:
#     """Extract text from PDF using pdfplumber or PyPDF2"""
#     logger.info(f"Extracting text from PDF: {pdf_path}")
#
#     # Try pdfplumber first (better for complex PDFs)
#     try:
#         import pdfplumber
#         logger.info("Using pdfplumber for PDF extraction")
#         text = ""
#         with pdfplumber.open(pdf_path) as pdf:
#             for page_num, page in enumerate(pdf.pages, 1):
#                 page_text = page.extract_text()
#                 if page_text:
#                     text += page_text + "\n"
#                     logger.debug(f"Extracted {len(page_text)} characters from page {page_num}")
#
#         if text and len(text.strip()) > 10:
#             logger.info(f"pdfplumber: Successfully extracted {len(text)} characters from PDF")
#             return text.strip()
#         else:
#             logger.warning(f"pdfplumber: Extracted minimal text ({len(text)} chars), trying PyPDF2...")
#     except ImportError:
#         logger.info("pdfplumber not available, trying PyPDF2...")
#     except Exception as e:
#         logger.warning(f"pdfplumber extraction failed: {e}, trying PyPDF2...")
#
#     # Fallback to PyPDF2
#     try:
#         import PyPDF2
#         logger.info("Using PyPDF2 for PDF extraction")
#         text = ""
#         with open(pdf_path, 'rb') as file:
#             pdf_reader = PyPDF2.PdfReader(file)
#             for page_num, page in enumerate(pdf_reader.pages, 1):
#                 page_text = page.extract_text()
#                 if page_text:
#                     text += page_text + "\n"
#                     logger.debug(f"Extracted {len(page_text)} characters from page {page_num}")
#
#         if text and len(text.strip()) > 10:
#             logger.info(f"PyPDF2: Successfully extracted {len(text)} characters from PDF")
#             return text.strip()
#         else:
#             logger.warning(f"PyPDF2: Extracted minimal text ({len(text)} chars)")
#     except ImportError:
#         logger.error("Neither pdfplumber nor PyPDF2 is installed. Install one: pip install pdfplumber OR pip install PyPDF2")
#         return ""
#     except Exception as e:
#         logger.error(f"PyPDF2 extraction error: {str(e)}", exc_info=True)
#         return ""
#
#     # If PDF has no extractable text (scanned PDF), try OCR on first page
#     logger.warning("PDF has no extractable text (may be scanned PDF). Attempting OCR on first page...")
#     try:
#         from pdf2image import convert_from_path
#         images = convert_from_path(pdf_path, first_page=1, last_page=1, dpi=300)
#         if images:
#             import tempfile
#             with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
#                 images[0].save(tmp_file.name, 'PNG')
#                 # Use image OCR extraction
#                 ocr_text = extract_text_from_image(tmp_file.name)
#                 os.unlink(tmp_file.name)  # Clean up temp file
#                 if ocr_text and len(ocr_text.strip()) > 10:
#                     logger.info(f"OCR on PDF first page: Extracted {len(ocr_text)} characters")
#                     return ocr_text.strip()
#     except ImportError:
#         logger.warning("pdf2image not available. For scanned PDFs, install: pip install pdf2image poppler")
#     except Exception as e:
#         logger.warning(f"OCR on PDF failed: {e}")
#
#     logger.error(f"Failed to extract text from PDF: {pdf_path}")
#     return ""
#
#
# def ocr_to_text(file_path: str) -> str:
#     """Convert document to raw text"""
#     try:
#         # Handle both absolute and relative paths
#         # For absolute paths (like /mnt/...), use as-is
#         # For relative paths, resolve them
#         if os.path.isabs(file_path):
#             path = Path(file_path)
#             resolved_path = path
#         else:
#             path = Path(file_path)
#             resolved_path = path.resolve()
#
#         logger.info(f"=== OCR Service: Processing file ===")
#         logger.info(f"File path (input): {file_path}")
#         logger.info(f"Path type: {'absolute' if os.path.isabs(file_path) else 'relative'}")
#         logger.info(f"Resolved path: {resolved_path}")
#         logger.info(f"Path exists: {resolved_path.exists()}")
#
#         # Verify file exists using resolved path
#         if not resolved_path.exists():
#             logger.error(f"File does not exist: {file_path}")
#             logger.error(f"Resolved path: {resolved_path}")
#             logger.error(f"Current working directory: {os.getcwd()}")
#             # Try to check if parent directory exists
#             if resolved_path.parent.exists():
#                 logger.error(f"Parent directory exists but file not found")
#                 logger.error(f"Files in parent directory: {list(resolved_path.parent.iterdir())[:10]}")
#             else:
#                 logger.error(f"Parent directory does not exist: {resolved_path.parent}")
#             return ""
#
#         # Verify file is readable
#         if not resolved_path.is_file():
#             logger.error(f"Path is not a file: {file_path} (resolved: {resolved_path})")
#             if resolved_path.is_dir():
#                 logger.error(f"Path is a directory, not a file")
#             return ""
#
#         # Check file permissions
#         if not os.access(str(resolved_path), os.R_OK):
#             logger.error(f"File is not readable (permission denied): {file_path}")
#             logger.error(f"File permissions: {oct(resolved_path.stat().st_mode)}")
#             return ""
#
#         # Check file size
#         file_size = resolved_path.stat().st_size
#         logger.info(f"File size: {file_size} bytes")
#
#         if file_size == 0:
#             logger.error(f"File is empty: {file_path}")
#             return ""
#
#         # Check file extension
#         file_ext = resolved_path.suffix.lower()
#         logger.info(f"File extension: {file_ext}")
#
#         # Process based on file type - use resolved path for actual file operations
#         if file_ext in ['.jpg', '.jpeg', '.png', '.bmp']:
#             logger.info(f"Processing as image file: {file_ext}")
#             # Use string path for OCR libraries (they expect string paths)
#             result = extract_text_from_image(str(resolved_path))
#             logger.info(f"Image OCR result: {len(result) if result else 0} characters extracted")
#             return result
#         elif file_ext == '.pdf':
#             logger.info(f"Processing as PDF file")
#             result = extract_text_from_pdf(str(resolved_path))
#             logger.info(f"PDF OCR result: {len(result) if result else 0} characters extracted")
#             return result
#         else:
#             logger.error(f"Unsupported file format: {file_ext}. Supported: .jpg, .jpeg, .png, .bmp, .pdf")
#             return ""
#     except Exception as e:
#         logger.error(f"Error in ocr_to_text: {str(e)}", exc_info=True)
#         logger.error(f"File path that caused error: {file_path}")
#         return ""

import json
import os
from pathlib import Path
from typing import Optional
import logging
import subprocess
import tempfile

# Get logger (logging configured in main)
logger = logging.getLogger(__name__)

# RAW OCR TEXT IS DISCARDED AFTER PROCESSING
# ONLY EXTRACTED DATA IS STORED

# Disable OneDNN/MKLDNN to avoid "OneDnnContext does not have the input Filter" on some Windows/CPU setups
os.environ.setdefault("FLAGS_use_mkldnn", "0")

# Try importing PaddleOCR
try:
    from paddleocr import PaddleOCR

    PADDLEOCR_AVAILABLE = True
    logger.info("PaddleOCR module imported successfully")
except ImportError as e:
    PADDLEOCR_AVAILABLE = False
    logger.warning(f"PaddleOCR import failed: {e}. Will try Tesseract as fallback.")

# Try importing pytesseract (fallback)
try:
    import pytesseract
    from PIL import Image

    PYTESSERACT_AVAILABLE = True
    logger.info("Pytesseract module imported successfully")

    # Check if Tesseract binary is available (pytesseract can be installed but binary missing)
    try:
        pytesseract.get_tesseract_version()
        logger.info("Tesseract binary is available and accessible")
    except pytesseract.TesseractNotFoundError:
        logger.warning("⚠ WARNING: pytesseract Python library is installed, but Tesseract binary is not found in PATH")
        logger.warning(
            "  Install Tesseract binary: apt-get install tesseract-ocr (Ubuntu/Debian) or yum install tesseract (CentOS/RHEL)")
    except Exception as e:
        logger.warning(f"Could not verify Tesseract binary: {e}")
except ImportError as e:
    PYTESSERACT_AVAILABLE = False
    logger.warning(f"Pytesseract import failed: {e}")

# Global OCR instance to avoid reinitialization
_ocr_instance = None
# Set to True after first Paddle OneDNN/runtime error so we skip Paddle for rest of process
_paddle_ocr_disabled = False


def get_ocr_instance():
    """Get or create OCR instance (lazy loading)"""
    global _ocr_instance
    if _ocr_instance is None and PADDLEOCR_AVAILABLE:
        try:
            logger.info("Initializing PaddleOCR...")
            _ocr_instance = PaddleOCR(use_angle_cls=True, lang='en')
            logger.info("PaddleOCR initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize PaddleOCR: {e}")
            _ocr_instance = None
    return _ocr_instance


def extract_text_paddle(image_path: str) -> str:
    """Extract text from image using PaddleOCR"""
    global _paddle_ocr_disabled
    if not PADDLEOCR_AVAILABLE:
        logger.warning("PaddleOCR not available, skipping PaddleOCR extraction")
        return ""
    if _paddle_ocr_disabled:
        return ""

    try:
        logger.info(f"Attempting PaddleOCR extraction from: {image_path}")
        ocr = get_ocr_instance()

        if ocr is None:
            logger.error("OCR instance initialization failed")
            return ""

        result = ocr.ocr(image_path, cls=True)

        if not result or not result[0]:
            logger.warning(f"No text detected by PaddleOCR in: {image_path}")
            return ""

        text = ""
        for line in result:
            if line:
                for word_info in line:
                    # word_info structure: [bbox, (text, confidence)]
                    if len(word_info) >= 2:
                        text += word_info[1][0] + " "

        cleaned_text = text.strip()
        logger.info(f"PaddleOCR: Successfully extracted {len(cleaned_text)} characters")
        return cleaned_text
    except Exception as e:
        err_str = str(e)
        if "OneDnnContext" in err_str or "fused_conv2d" in err_str:
            _paddle_ocr_disabled = True
            logger.warning("PaddleOCR OneDNN backend failed; using Tesseract only for this process.")
            return ""
        logger.error(f"PaddleOCR extraction error: {str(e)}", exc_info=True)
        return ""


def extract_text_tesseract(image_path: str) -> str:
    """Extract text from image using Pytesseract (fallback)"""
    if not PYTESSERACT_AVAILABLE:
        logger.warning("Pytesseract not available, skipping Tesseract extraction")
        return ""

    try:
        logger.info(f"Attempting Pytesseract extraction from: {image_path}")
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image)

        if not text or len(text.strip()) < 10:
            logger.warning(f"Tesseract extracted minimal text from: {image_path}")
            return text.strip()

        logger.info(f"Tesseract: Successfully extracted {len(text)} characters")
        return text.strip()
    except pytesseract.TesseractNotFoundError as e:
        error_msg = str(e)
        logger.error("=" * 80)
        logger.error("✗ CRITICAL: Tesseract binary not found!")
        logger.error(f"  Error: {error_msg}")
        logger.error("")
        logger.error("  SOLUTION: Install Tesseract OCR binary:")
        logger.error("    Ubuntu/Debian: sudo apt-get install tesseract-ocr")
        logger.error("    CentOS/RHEL:   sudo yum install tesseract")
        logger.error("    macOS:         brew install tesseract")
        logger.error("")
        logger.error("  After installation, verify:")
        logger.error("    tesseract --version")
        logger.error("")
        logger.error("  NOTE: pytesseract (Python library) is installed, but the")
        logger.error("        Tesseract binary executable is missing from PATH.")
        logger.error("=" * 80)
        return ""
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Pytesseract extraction error: {error_msg}")
        # Check if it's a PATH issue
        if "tesseract is not installed" in error_msg.lower() or "not in your path" in error_msg.lower():
            logger.error("=" * 80)
            logger.error("✗ CRITICAL: Tesseract binary not found in PATH!")
            logger.error("")
            logger.error("  SOLUTION: Install Tesseract OCR binary:")
            logger.error("    Ubuntu/Debian: sudo apt-get install tesseract-ocr")
            logger.error("    CentOS/RHEL:   sudo yum install tesseract")
            logger.error("    macOS:         brew install tesseract")
            logger.error("")
            logger.error("  After installation, verify:")
            logger.error("    tesseract --version")
            logger.error("=" * 80)
        return ""


def extract_text_from_image(image_path: str) -> str:
    """Extract text from image using multiple OCR methods"""
    logger.info(f"=== Starting OCR extraction for image ===")
    logger.info(f"Image path: {image_path}")

    # Verify file exists
    if not os.path.exists(image_path):
        logger.error(f"Image file does not exist: {image_path}")
        return ""

    file_size = os.path.getsize(image_path)
    logger.info(f"Image file size: {file_size} bytes")

    if file_size == 0:
        logger.error(f"Image file is empty: {image_path}")
        return ""

    # Try PaddleOCR first
    logger.info("Attempting OCR extraction with PaddleOCR...")
    text = extract_text_paddle(image_path)
    if text and len(text) > 50:
        logger.info(f"PaddleOCR extraction successful: {len(text)} characters extracted")
        logger.info(f"[RAW_OCR] PaddleOCR extracted text (first 500 chars): {text[:500]}")
        return text
    elif text:
        logger.warning(f"PaddleOCR extracted minimal text ({len(text)} chars), trying Tesseract...")

    # Fallback to Tesseract
    logger.info("Attempting OCR extraction with Tesseract (fallback)...")
    text = extract_text_tesseract(image_path)
    if text and len(text) > 50:
        logger.info(f"Tesseract extraction successful: {len(text)} characters extracted")
        logger.info(f"[RAW_OCR] Tesseract extracted text (first 500 chars): {text[:500]}")
        return text
    elif text:
        logger.warning(f"Tesseract extracted minimal text ({len(text)} chars)")

    # If both fail, return combined results if any text was extracted
    if text:
        logger.warning(f"Returning minimal OCR results: {len(text)} characters")
        logger.info(f"[RAW_OCR] Minimal text extracted (first 500 chars): {text[:500]}")
        return text

    logger.error("All OCR methods failed to extract sufficient text from image")
    logger.error(f"File path: {image_path}, File exists: {os.path.exists(image_path)}, File size: {file_size}")
    return ""


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from PDF using pdfplumber or PyPDF2"""
    logger.info(f"Extracting text from PDF: {pdf_path}")

    # Try pdfplumber first (better for complex PDFs)
    try:
        import pdfplumber
        logger.info("Using pdfplumber for PDF extraction")
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                    logger.debug(f"Extracted {len(page_text)} characters from page {page_num}")

        if text and len(text.strip()) > 10:
            logger.info(f"pdfplumber: Successfully extracted {len(text)} characters from PDF")
            logger.info(f"[RAW_OCR] PDF pdfplumber extracted text (first 500 chars): {text[:500]}")
            return text.strip()
        else:
            logger.warning(f"pdfplumber: Extracted minimal text ({len(text)} chars), trying PyPDF2...")
    except ImportError:
        logger.info("pdfplumber not available, trying PyPDF2...")
    except Exception as e:
        logger.warning(f"pdfplumber extraction failed: {e}, trying PyPDF2...")

    # Fallback to PyPDF2
    try:
        import PyPDF2
        logger.info("Using PyPDF2 for PDF extraction")
        text = ""
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page_num, page in enumerate(pdf_reader.pages, 1):
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                    logger.debug(f"Extracted {len(page_text)} characters from page {page_num}")

        if text and len(text.strip()) > 10:
            logger.info(f"PyPDF2: Successfully extracted {len(text)} characters from PDF")
            logger.info(f"[RAW_OCR] PDF PyPDF2 extracted text (first 500 chars): {text[:500]}")
            return text.strip()
        else:
            logger.warning(f"PyPDF2: Extracted minimal text ({len(text)} chars)")
    except ImportError:
        logger.error(
            "Neither pdfplumber nor PyPDF2 is installed. Install one: pip install pdfplumber OR pip install PyPDF2")
        return ""
    except Exception as e:
        logger.error(f"PyPDF2 extraction error: {str(e)}", exc_info=True)
        return ""

    # If PDF has no extractable text (scanned PDF), try OCR on first page
    logger.warning("PDF has no extractable text (may be scanned PDF). Attempting OCR on first page...")
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(pdf_path, first_page=1, last_page=1, dpi=300)
        if images:
            import tempfile
            import time

            # Create temp file that persists after context manager
            tmp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            tmp_path = tmp_file.name
            tmp_file.close()

            try:
                # Save image to temp file
                images[0].save(tmp_path, 'PNG')

                # Add small delay to ensure file is written and released
                time.sleep(0.1)

                # Use image OCR extraction
                ocr_text = extract_text_from_image(tmp_path)

                if ocr_text and len(ocr_text.strip()) > 10:
                    logger.info(f"OCR on PDF first page: Extracted {len(ocr_text)} characters")
                    logger.info(f"[RAW_OCR] PDF scanned page OCR text (first 500 chars): {ocr_text[:500]}")
                    return ocr_text.strip()
            finally:
                # Clean up temp file with retry logic
                try:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                except PermissionError:
                    logger.warning(f"Could not immediately delete temp file {tmp_path}, will be cleaned by OS")
                except Exception as e:
                    logger.warning(f"Error deleting temp file {tmp_path}: {e}")

    except ImportError:
        logger.warning("pdf2image not available. For scanned PDFs, install: pip install pdf2image poppler")
    except Exception as e:
        logger.warning(f"OCR on PDF failed: {e}")

    logger.error(f"Failed to extract text from PDF: {pdf_path}")
    return ""


def ocr_to_text(file_path: str) -> str:
    """Convert document to raw text"""
    try:
        # Handle both absolute and relative paths
        # For absolute paths (like /mnt/...), use as-is
        # For relative paths, resolve them
        if os.path.isabs(file_path):
            path = Path(file_path)
            resolved_path = path
        else:
            path = Path(file_path)
            resolved_path = path.resolve()

        logger.info(f"=== OCR Service: Processing file ===")
        logger.info(f"File path (input): {file_path}")
        logger.info(f"Path type: {'absolute' if os.path.isabs(file_path) else 'relative'}")
        logger.info(f"Resolved path: {resolved_path}")
        logger.info(f"Path exists: {resolved_path.exists()}")

        # Verify file exists using resolved path
        if not resolved_path.exists():
            logger.error(f"File does not exist: {file_path}")
            logger.error(f"Resolved path: {resolved_path}")
            logger.error(f"Current working directory: {os.getcwd()}")
            # Try to check if parent directory exists
            if resolved_path.parent.exists():
                logger.error(f"Parent directory exists but file not found")
                logger.error(f"Files in parent directory: {list(resolved_path.parent.iterdir())[:10]}")
            else:
                logger.error(f"Parent directory does not exist: {resolved_path.parent}")
            return ""

        # Verify file is readable
        if not resolved_path.is_file():
            logger.error(f"Path is not a file: {file_path} (resolved: {resolved_path})")
            if resolved_path.is_dir():
                logger.error(f"Path is a directory, not a file")
            return ""

        # Check file permissions
        if not os.access(str(resolved_path), os.R_OK):
            logger.error(f"File is not readable (permission denied): {file_path}")
            logger.error(f"File permissions: {oct(resolved_path.stat().st_mode)}")
            return ""

        # Check file size
        file_size = resolved_path.stat().st_size
        logger.info(f"File size: {file_size} bytes")

        if file_size == 0:
            logger.error(f"File is empty: {file_path}")
            return ""

        # Check file extension
        file_ext = resolved_path.suffix.lower()
        logger.info(f"File extension: {file_ext}")

        # Process based on file type - use resolved path for actual file operations
        if file_ext in ['.jpg', '.jpeg', '.png', '.bmp']:
            logger.info(f"Processing as image file: {file_ext}")
            # Use string path for OCR libraries (they expect string paths)
            result = extract_text_from_image(str(resolved_path))
            logger.info(f"Image OCR result: {len(result) if result else 0} characters extracted")
            return result
        elif file_ext == '.pdf':
            logger.info(f"Processing as PDF file")
            result = extract_text_from_pdf(str(resolved_path))
            logger.info(f"PDF OCR result: {len(result) if result else 0} characters extracted")
            return result
        else:
            logger.error(f"Unsupported file format: {file_ext}. Supported: .jpg, .jpeg, .png, .bmp, .pdf")
            return ""
    except Exception as e:
        logger.error(f"Error in ocr_to_text: {str(e)}", exc_info=True)
        logger.error(f"File path that caused error: {file_path}")
        return ""

