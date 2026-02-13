import re
import logging
from typing import Dict, List, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


def normalize_name(name: str) -> str:
    """
    Normalize name for comparison.

    Steps:
    1. Convert to uppercase
    2. Remove extra spaces
    3. Remove special characters (keep only letters and spaces)
    4. Handle common OCR errors

    Args:
        name: Raw name string

    Returns:
        Normalized name string
    """
    if not name:
        return ""

    # Convert to uppercase
    normalized = name.upper().strip()

    # Remove special characters but keep spaces
    normalized = re.sub(r'[^A-Z\s]', '', normalized)

    # Remove extra spaces
    normalized = re.sub(r'\s+', ' ', normalized)

    # Handle common OCR errors (optional - can be expanded)
    # Example: O -> 0, I -> 1, etc.
    # For names, we typically don't need this, but keeping for reference

    return normalized.strip()


def fuzzy_match_names(name1: str, name2: str, threshold: float = 0.85) -> Tuple[bool, float]:
    """
    Compare two names using fuzzy matching (Levenshtein distance via SequenceMatcher).

    Args:
        name1: First name (from personal document)
        name2: Second name (from educational document)
        threshold: Similarity threshold (0.0 to 1.0), default 0.85 = 85% similar

    Returns:
        Tuple of (match: bool, similarity_score: float)
    """
    if not name1 or not name2:
        logger.warning(f"Empty name comparison: name1='{name1}', name2='{name2}'")
        return False, 0.0

    # Normalize both names
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)

    logger.info(f"Comparing names: '{norm1}' vs '{norm2}'")

    # Exact match check first
    if norm1 == norm2:
        logger.info("✓ Names match exactly")
        return True, 1.0

    # Calculate similarity ratio
    similarity = SequenceMatcher(None, norm1, norm2).ratio()

    logger.info(f"Name similarity score: {similarity:.2%} (threshold: {threshold:.2%})")

    match = similarity >= threshold

    if match:
        logger.info(f"✓ Names match with {similarity:.2%} similarity")
    else:
        logger.warning(f"✗ Names don't match: {similarity:.2%} < {threshold:.2%}")

    return match, similarity


def normalize_date(date_str: str) -> str:
    """
    Normalize date string to DD-MM-YYYY format.

    Handles:
    - DD/MM/YYYY -> DD-MM-YYYY
    - DD.MM.YYYY -> DD-MM-YYYY
    - YYYY-MM-DD -> DD-MM-YYYY
    - DD-M-YYYY -> DD-MM-YYYY (add leading zeros)

    Args:
        date_str: Date string in various formats

    Returns:
        Normalized date string in DD-MM-YYYY format
    """
    if not date_str:
        return ""

    date_str = str(date_str).strip()

    # Replace common separators with hyphen
    date_str = date_str.replace('/', '-').replace('.', '-').replace(' ', '-')

    # Split by hyphen
    parts = date_str.split('-')

    if len(parts) != 3:
        logger.warning(f"Invalid date format (expected 3 parts): {date_str}")
        return date_str  # Return as-is if format is unexpected

    # Check if format is YYYY-MM-DD
    if len(parts[0]) == 4 and parts[0].isdigit():
        # YYYY-MM-DD -> DD-MM-YYYY
        year, month, day = parts
        normalized = f"{day.zfill(2)}-{month.zfill(2)}-{year}"
        logger.debug(f"Converted YYYY-MM-DD to DD-MM-YYYY: {date_str} -> {normalized}")
        return normalized

    # Assume DD-MM-YYYY format
    day, month, year = parts

    # Add leading zeros if needed
    day = day.zfill(2)
    month = month.zfill(2)

    # Handle 2-digit year (e.g., 87 -> 1987)
    if len(year) == 2:
        year_int = int(year)
        # Assume 1900s for years > 50, 2000s for years <= 50
        year = f"19{year}" if year_int > 50 else f"20{year}"
        logger.debug(f"Converted 2-digit year: {parts[2]} -> {year}")

    normalized = f"{day}-{month}-{year}"

    if normalized != date_str:
        logger.debug(f"Normalized date: {date_str} -> {normalized}")

    return normalized


def exact_match_dob(dob1: str, dob2: str) -> Tuple[bool, str]:
    """
    Compare two dates of birth for exact match.

    Args:
        dob1: First DOB (from personal document)
        dob2: Second DOB (from educational document)

    Returns:
        Tuple of (match: bool, message: str)
    """
    if not dob1 or not dob2:
        logger.warning(f"Empty DOB comparison: dob1='{dob1}', dob2='{dob2}'")
        return False, "One or both DOBs are missing"

    # Normalize both dates
    norm1 = normalize_date(dob1)
    norm2 = normalize_date(dob2)

    logger.info(f"Comparing DOBs: '{norm1}' vs '{norm2}'")

    # Exact match
    match = norm1 == norm2

    if match:
        logger.info("✓ DOBs match exactly")
        return True, "DOBs match"
    else:
        logger.warning(f"✗ DOBs don't match: '{norm1}' != '{norm2}'")
        return False, f"DOB mismatch: {norm1} vs {norm2}"


def verify_documents(personal_name: str, personal_dob: str,
                     educational_documents: List[Dict]) -> Dict:
    """
    Verify that personal document data matches educational document data.

    Args:
        personal_name: Name from personal document
        personal_dob: DOB from personal document
        educational_documents: List of educational document data dicts, each containing:
            - id: Document ID
            - extracted_name: Name from educational document
            - extracted_dob: DOB from educational document
            - qualification: e.g., "Class 10"

    Returns:
        Verification result dict:
        {
            "status": "verified" | "failed" | "pending",
            "verified_count": int,
            "total_count": int,
            "comparisons": [
                {
                    "document_id": int,
                    "qualification": str,
                    "name_match": bool,
                    "name_similarity": float,
                    "dob_match": bool,
                    "overall_match": bool
                }
            ],
            "mismatches": [
                {
                    "document_id": int,
                    "qualification": str,
                    "field": "name" | "dob",
                    "personal_value": str,
                    "document_value": str,
                    "match": bool,
                    "reason": str
                }
            ]
        }
    """
    logger.info("=" * 80)
    logger.info("=== DOCUMENT VERIFICATION STARTED ===")
    logger.info(f"Personal document data: name='{personal_name}', dob='{personal_dob}'")
    logger.info(f"Educational documents to verify: {len(educational_documents)}")
    logger.info("=" * 80)

    if not personal_name or not personal_dob:
        logger.error("Personal document data incomplete - cannot verify")
        return {
            "status": "pending",
            "verified_count": 0,
            "total_count": len(educational_documents),
            "comparisons": [],
            "mismatches": [],
            "error": "Personal document data incomplete"
        }

    if not educational_documents:
        logger.warning("No educational documents to verify")
        return {
            "status": "pending",
            "verified_count": 0,
            "total_count": 0,
            "comparisons": [],
            "mismatches": [],
            "error": "No educational documents found"
        }

    comparisons = []
    mismatches = []
    verified_count = 0

    for edu_doc in educational_documents:
        doc_id = edu_doc.get('id')
        qualification = edu_doc.get('qualification', 'Unknown')
        edu_name = edu_doc.get('extracted_name')
        edu_dob = edu_doc.get('extracted_dob')

        logger.info(f"\n--- Verifying Document ID: {doc_id} ({qualification}) ---")
        logger.info(f"Educational doc data: name='{edu_name}', dob='{edu_dob}'")

        # Compare name
        name_match, name_similarity = fuzzy_match_names(personal_name, edu_name)

        # Compare DOB
        dob_match, dob_message = exact_match_dob(personal_dob, edu_dob)

        # Overall match: both name and DOB must match
        overall_match = name_match and dob_match

        if overall_match:
            verified_count += 1
            logger.info(f"✓ Document {doc_id} verified successfully")
        else:
            logger.warning(f"✗ Document {doc_id} verification FAILED")

        # Record comparison
        comparison = {
            "document_id": doc_id,
            "qualification": qualification,
            "name_match": name_match,
            "name_similarity": round(name_similarity, 3),
            "dob_match": dob_match,
            "overall_match": overall_match
        }
        comparisons.append(comparison)

        # Record mismatches
        if not name_match:
            mismatches.append({
                "document_id": doc_id,
                "qualification": qualification,
                "field": "name",
                "personal_value": personal_name,
                "document_value": edu_name or "Not found",
                "match": False,
                "similarity": round(name_similarity, 3),
                "reason": f"Name similarity {name_similarity:.2%} below threshold"
            })

        if not dob_match:
            mismatches.append({
                "document_id": doc_id,
                "qualification": qualification,
                "field": "dob",
                "personal_value": personal_dob,
                "document_value": edu_dob or "Not found",
                "match": False,
                "reason": dob_message
            })

    # Determine overall status
    total_count = len(educational_documents)

    if verified_count == total_count:
        status = "verified"
        logger.info(f"\n{'=' * 80}")
        logger.info(f"✓✓✓ VERIFICATION SUCCESSFUL ✓✓✓")
        logger.info(f"All {verified_count}/{total_count} documents verified")
        logger.info(f"{'=' * 80}\n")
    else:
        status = "failed"
        logger.warning(f"\n{'=' * 80}")
        logger.warning(f"✗✗✗ VERIFICATION FAILED ✗✗✗")
        logger.warning(f"Only {verified_count}/{total_count} documents verified")
        logger.warning(f"Mismatches found: {len(mismatches)}")
        logger.warning(f"{'=' * 80}\n")

    result = {
        "status": status,
        "verified_count": verified_count,
        "total_count": total_count,
        "comparisons": comparisons,
        "mismatches": mismatches
    }

    return result


def format_verification_error_message(verification_result: Dict) -> str:
    """
    Format user-friendly error message for verification failures.

    Args:
        verification_result: Result dict from verify_documents()

    Returns:
        User-friendly error message string
    """
    if verification_result['status'] == 'verified':
        return ""

    mismatches = verification_result.get('mismatches', [])

    if not mismatches:
        return "Document verification failed. Please ensure all documents are clear, legible, and contain matching personal information."

    error_lines = ["❌ Your details are not matching. Please reupload the document.\n\n"]
    error_lines.append("Details that don't match:\n")

    # Group mismatches by document
    doc_errors = {}
    for mismatch in mismatches:
        doc_id = mismatch['document_id']
        qual = mismatch['qualification']

        if doc_id not in doc_errors:
            doc_errors[doc_id] = {
                'qualification': qual,
                'errors': []
            }

        field = mismatch['field'].upper()
        personal = mismatch['personal_value']
        document = mismatch['document_value']

        if field == 'NAME':
            error_msg = f"  • Name mismatch: Personal document shows \"{personal}\" but your {qual} shows \"{document}\""
        elif field == 'DOB':
            error_msg = f"  • Date of Birth mismatch: Personal document shows \"{personal}\" but your {qual} shows \"{document}\""
        else:
            error_msg = f"  • {field}: Personal document shows \"{personal}\" but {qual} shows \"{document}\""

        doc_errors[doc_id]['errors'].append(error_msg)

    # Format error message
    for doc_id, info in doc_errors.items():
        error_lines.append(f"\n📄 {info['qualification']}:")
        error_lines.extend(info['errors'])

    error_lines.append("\n\n📋 Action required:")
    error_lines.append("1. Make sure both documents have the same name and date of birth")
    error_lines.append("2. Check for spelling errors or OCR mistakes")
    error_lines.append("3. Upload clear, legible scans/photos of your documents")
    error_lines.append(
        "\n💡 Tip: Ensure the name and DOB are exactly the same on both your personal document (ID/Passport) and educational certificate/marksheet.")

    return "\n".join(error_lines)
