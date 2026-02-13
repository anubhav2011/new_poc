import re
import logging

logger = logging.getLogger(__name__)


def validate_mobile_number(mobile: str) -> bool:
    """
    Validate Indian mobile number format.
    Must be 10 digits.
    """
    try:
        if not mobile:
            logger.warning("Mobile number is empty")
            return False

        # Remove any spaces or special characters
        mobile_clean = re.sub(r'\D', '', mobile)

        # Check if exactly 10 digits
        is_valid = len(mobile_clean) == 10 and mobile_clean.isdigit()

        if not is_valid:
            logger.warning(
                f"Invalid mobile number format: {mobile} (cleaned: {mobile_clean}, length: {len(mobile_clean)})")
        else:
            logger.debug(f"Valid mobile number: {mobile_clean}")

        return is_valid
    except Exception as e:
        logger.error(f"Error validating mobile number: {str(e)}", exc_info=True)
        return False


def validate_consent(consent: bool) -> bool:
    """Validate consent checkbox"""
    return consent is True


def validate_document_upload(file_path: str) -> bool:
    """Validate uploaded document format"""
    try:
        from pathlib import Path

        path = Path(file_path)

        # Check if file exists
        if not path.exists():
            logger.error(f"Document file does not exist: {file_path}")
            return False

        # Check file size (max 10MB)
        file_size = path.stat().st_size
        max_size = 10 * 1024 * 1024
        if file_size > max_size:
            logger.error(f"Document file too large: {file_size} bytes (max: {max_size})")
            return False

        # Check file type
        allowed_extensions = {'.pdf', '.jpg', '.jpeg', '.png', '.bmp'}
        is_valid = path.suffix.lower() in allowed_extensions

        if not is_valid:
            logger.error(f"Invalid document type: {path.suffix}")
        else:
            logger.debug(f"Valid document: {path.name} ({file_size} bytes)")

        return is_valid
    except Exception as e:
        logger.error(f"Error validating document: {str(e)}", exc_info=True)
        return False


def validate_form_submission(mobile_number: str, consent: bool) -> tuple[bool, str]:
    """
    Validate complete form submission.
    Returns (is_valid, error_message)
    """

    # POC ONLY — MOBILE NUMBER IS SELF-DECLARED VIA FORM

    try:
        logger.info("Starting form submission validation")

        if not validate_mobile_number(mobile_number):
            logger.warning(f"Form validation failed: Invalid mobile number")
            return False, "Invalid mobile number. Please enter a 10-digit number."

        if not validate_consent(consent):
            logger.warning(f"Form validation failed: Consent not provided")
            return False, "Please accept the consent checkbox."

        logger.info(f"Form validation successful for mobile: {mobile_number}")
        return True, ""
    except Exception as e:
        logger.error(f"Error during form validation: {str(e)}", exc_info=True)
        return False, "An unexpected error occurred during validation. Please try again."
