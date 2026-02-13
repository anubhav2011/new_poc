import json
import re
import os
from typing import Optional
import logging

# Get logger (logging configured in main)
logger = logging.getLogger(__name__)

# RAW OCR TEXT IS DISCARDED AFTER PROCESSING
# ONLY EXTRACTED FIELDS ARE STORED

EXTRACTION_PROMPT = """You are given OCR text from an Indian identity document (Aadhaar, PAN, Passport, Voter ID, etc.).

Extract ONLY these fields:
1. Name: Full name of the person
2. Date of Birth: In DD/MM/YYYY format
3. Address: Full residential address

Important Rules:
- Do NOT infer or guess missing information
- Do NOT include document numbers, reference numbers, or IDs
- If field is not found, use empty string ""
- Return ONLY valid JSON, no extra text
- Handle OCR errors like 'O' for '0' and 'l' for '1'

Input OCR text:
{ocr_text}

Return this JSON format exactly:
{{
    "name": "",
    "dob": "",
    "address": ""
}}"""

# Initialize OpenAI client (lazy loading)
openai_client = None


def get_openai_client():
    """Get or initialize OpenAI client (lazy loading with error handling)"""
    global openai_client
    if openai_client is None:
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("OPENAI_API_KEY not set. LLM fallback will be skipped.")
                return None
            from openai import OpenAI
            openai_client = OpenAI(api_key=api_key)
            logger.info("OpenAI client initialized successfully")
        except ImportError:
            logger.warning("OpenAI library not installed. Install with: pip install openai")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            return None
    return openai_client


def _normalize_name(name: str) -> str:
    """Strip OCR artifacts from name (e.g. leading/trailing quotes: 'BABU KHAN -> BABU KHAN). Handles ASCII and Unicode/smart quotes."""
    if not name:
        return name
    s = str(name).strip()
    # ASCII quotes + common Unicode quotation marks (e.g. smart quotes from OCR/Word)
    quote_chars = "'\"\t \u2018\u2019\u201c\u201d\u00ab\u00bb"
    return s.strip(quote_chars).strip()


def extract_driving_license_data(ocr_text: str) -> Optional[dict]:
    """
    Specialized extraction for Indian Driving License documents.
    Handles DL-specific field layouts and patterns.
    """
    if not ocr_text or len(ocr_text.strip()) < 20:
        logger.warning("OCR text too short for DL extraction")
        return None

    result = {
        "name": "",
        "dob": "",
        "address": ""
    }

    lines = [line.strip() for line in ocr_text.split('\n') if line.strip()]
    text_upper = ocr_text.upper()

    logger.info(f"Extracting from {len(lines)} lines of OCR text")

    # ============ DOB EXTRACTION ============
    # Pattern: DOB : DD-MM-YYYY or DOB: DD/MM/YYYY
    dob_patterns = [
        r'DOB\s*:?\s*(\d{1,2})[/-](\d{1,2})[/-](\d{4})',  # DOB : 01-12-1987
        r'Date\s+of\s+Birth\s*:?\s*(\d{1,2})[/-](\d{1,2})[/-](\d{4})',
        r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b'  # Fallback: just date pattern
    ]

    for pattern in dob_patterns:
        dob_match = re.search(pattern, ocr_text, re.IGNORECASE)
        if dob_match:
            day, month, year = dob_match.groups()[:3]
            result["dob"] = f"{day}-{month}-{year}"
            logger.info(f"Found DOB: {result['dob']}")
            break

    # ============ NAME EXTRACTION ============
    # Reject candidates that are form labels or document text, not person names
    name_reject_keywords = [
        'AUTHORISATION', 'RULE', 'CLASS', 'DRIVE', 'FOLLOWING', 'VEHICLE', 'MOTOR',
        'MAHARASHTRA', 'DRIVING', 'LICENCE', 'UNION', 'INDIA', 'VALID', 'SIGNATURE',
        'HOLDER', 'ENDORSEMENT', 'FORM', 'MCWG', 'LMV', 'TRANSPORT', 'THROUGHOUT'
    ]

    def strip_name_label(text: str) -> str:
        """Remove leading 'Name ', 'Name:', 'Name \'' etc. from extracted name."""
        if not text:
            return text
        t = text.strip()
        for prefix in (r"Name\s*['\"]?", "Name\s*:\s*", "Name\s+"):
            t = re.sub(r"^(?i)" + prefix, "", t).strip()
        # Strip OCR artifacts: leading/trailing quotes (e.g. 'BABU KHAN)
        t = t.strip("'\" \t")
        return t

    def is_valid_name(candidate: str) -> bool:
        if not candidate or len(candidate) < 3 or len(candidate) > 100:
            return False
        alpha_ratio = sum(c.isalpha() or c.isspace() for c in candidate) / len(candidate)
        if alpha_ratio <= 0.8:
            return False
        upper = candidate.upper()
        if any(kw in upper for kw in name_reject_keywords):
            return False
        # Name should look like "First Last" (no digits, no parentheses like "RULE 16 (2)")
        if re.search(r'\d|\(\d|\)', candidate):
            return False
        # Reject abbreviation-like names: "COV Dol", "S D", "A B" (two short words)
        words = candidate.split()
        if len(words) >= 2 and all(len(w) <= 3 for w in words):
            return False
        # Reject if every word is very short (e.g. "COV Dol" - at least one word should be 4+ chars)
        if words and not any(len(w) >= 4 for w in words):
            return False
        # Reject common OCR misreads of "S/D of" or labels
        if upper.strip() in ('COV DOL', 'S/D', 'S D', 'DOL', 'OF'):
            return False
        return True

    # Pattern: "Name :" or "Name:" followed by the name (until S/D, Father, or newline)
    name_patterns = [
        r'Name\s*:?\s*([A-Z][A-Za-z\s]+?)(?=\s*S/D|\s*S\.D|Father|Father\'s|\n|$)',
        r'Name\s*:?\s*([A-Z][A-Za-z\s]+?)(?:\n|$)',
    ]

    for pattern in name_patterns:
        name_match = re.search(pattern, ocr_text, re.IGNORECASE | re.MULTILINE)
        if name_match:
            candidate_name = name_match.group(1).strip()
            candidate_name = re.sub(r'\s+', ' ', candidate_name)
            candidate_name = strip_name_label(candidate_name)
            if is_valid_name(candidate_name):
                result["name"] = candidate_name
                logger.info(f"Found Name: {result['name']}")
                break

    # Fallback: First significant text line that looks like a name (exclude form labels)
    if not result["name"]:
        for line in lines:
            candidate = strip_name_label(line.strip())
            if is_valid_name(candidate) and 4 < len(candidate) < 80:
                result["name"] = candidate
                logger.info(f"Found Name (fallback): {result['name']}")
                break

    # ============ ADDRESS EXTRACTION ============
    # Pattern: "Add" or "Address:" followed by full address (may span multiple lines until PIN)
    # Include all lines until PIN Code / PIN: so we get "GOVANDI, MUMBAI" etc.
    addr_patterns = [
        r'Add(?:ress)?\s*:?\s*([A-Z][A-Z0-9\s,\-\.]+(?:\s*\n\s*[A-Z][A-Z0-9\s,\-\.]+)*)\s*(?=PIN|$)',
        r'Add(?:ress)?\s*:?\s*([A-Z][A-Z0-9\s,\-\.]+?)(?:\n|PIN)',
    ]

    for pattern in addr_patterns:
        addr_match = re.search(pattern, ocr_text, re.IGNORECASE | re.DOTALL)
        if addr_match:
            address = addr_match.group(1).strip()
            address = re.sub(r'\s+', ' ', address)  # Normalize spaces and newlines
            address = re.sub(r',\s*,', ',', address).strip()
            if len(address) > 5:
                result["address"] = address
                logger.info(f"Found Address: {result['address'][:50]}...")
                break

    # Fallback: Collect longer lines that look like address
    if not result["address"]:
        address_lines = []
        skip_keywords = ['Name', 'DOB', 'DL NO', 'DL No', 'Valid', 'Maharashtra', 'Driving',
                         'Licence', 'Authorisation', 'Class', 'Signature', 'PIN', 'Issued']

        for line in lines:
            # Skip short lines and header lines
            if len(line) > 15 and not any(kw in line for kw in skip_keywords):
                # Prefer lines with more text (address-like)
                if any(c.isalpha() for c in line):
                    address_lines.append(line)

        # Join first few address-like lines
        if address_lines:
            result["address"] = " ".join(address_lines[:2])
            logger.info(f"Found Address (fallback): {result['address'][:50]}...")

    return result


def rule_based_extraction(ocr_text: str) -> Optional[dict]:
    """
    Rule-based extraction without LLM.
    Uses pattern matching for common formats found in Indian IDs.
    Tries DL-specific extraction first, then falls back to generic.
    """
    if not ocr_text or len(ocr_text.strip()) < 20:
        logger.warning("OCR text too short for extraction")
        return None

    # Try DL-specific extraction first
    result = extract_driving_license_data(ocr_text)

    if result and (result.get("name") or result.get("dob") or result.get("address")):
        logger.info("DL-specific extraction successful")
        return result

    # Fallback to generic extraction if DL extraction had no results
    logger.info("DL-specific extraction had limited results, trying generic extraction")
    result = {
        "name": "",
        "dob": "",
        "address": ""
    }

    lines = [line.strip() for line in ocr_text.split('\n') if line.strip()]

    # Generic DOB pattern matching
    dob_pattern = r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b'
    dob_match = re.search(dob_pattern, ocr_text)
    if dob_match:
        result["dob"] = dob_match.group(0)
        logger.info(f"Found DOB (generic): {result['dob']}")

    # Generic Name extraction
    for line in lines:
        clean_line = re.sub(r'[0-9@#$%^&*()_+=\[\]{};:,.<>?/\\-]', '', line).strip()
        if len(clean_line) > 3 and len(clean_line) < 100:
            alpha_ratio = sum(c.isalpha() or c.isspace() for c in clean_line) / len(clean_line)
            if alpha_ratio > 0.7:
                result["name"] = clean_line
                logger.info(f"Found Name (generic): {result['name']}")
                break

    # Generic Address extraction
    address_candidates = []
    for line in lines:
        if len(line) > 15 and line not in [result.get("name"), result.get("dob")]:
            if not re.match(r'^(document|id|number|ref|date)', line, re.IGNORECASE):
                address_candidates.append(line)

    if address_candidates:
        result["address"] = " ".join(address_candidates[:3])
        logger.info(f"Found Address (generic): {result['address'][:50]}...")

    return result


def parse_extraction_response(response_text: str) -> Optional[dict]:
    """Parse JSON response from LLM extraction"""
    try:
        # Find JSON in response - match balanced braces
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            logger.debug(f"Extracted JSON: {json_str}")
            data = json.loads(json_str)

            # Validate required fields exist
            if isinstance(data, dict) and all(key in data for key in ["name", "dob", "address"]):
                return {
                    "name": _normalize_name(data.get("name", "")),
                    "dob": str(data.get("dob", "")).strip(),
                    "address": str(data.get("address", "")).strip()
                }
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
    except Exception as e:
        logger.error(f"Error parsing extraction response: {e}")

    return None


def extract_with_openai(ocr_text: str) -> Optional[dict]:
    """Extract data using OpenAI API with fallback"""
    client = get_openai_client()
    if not client:
        logger.warning("OpenAI client not available. Skipping LLM extraction.")
        return None

    try:
        logger.info("Attempting OpenAI extraction...")
        prompt = EXTRACTION_PROMPT.format(ocr_text=ocr_text)

        response = client.chat.completions.create(
            model=os.getenv("LLM_MODEL", "gpt-3.5-turbo"),
            messages=[
                {
                    "role": "system",
                    "content": "You are a data extraction expert. Return ONLY valid JSON, no markdown, no extra text."
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=300
        )

        response_text = response.choices[0].message.content
        logger.info(f"OpenAI response: {response_text[:100]}...")
        result = parse_extraction_response(response_text)

        if result:
            logger.info("Successfully extracted data from OpenAI")
            return result
    except Exception as e:
        logger.error(f"OpenAI extraction error: {str(e)}", exc_info=True)

    return None


def clean_ocr_extraction(ocr_text: str) -> dict:
    """
    Clean OCR text and extract only necessary fields.
    Try rule-based first, then fallback to OpenAI if needed.
    """
    logger.info("=== Starting OCR extraction ===")
    logger.info(f"OCR text length: {len(ocr_text)} characters")
    logger.debug(f"First 200 chars: {ocr_text[:200]}")

    if not ocr_text or len(ocr_text.strip()) < 10:
        logger.error("OCR text is empty or too short")
        return {
            "name": "",
            "dob": "",
            "address": ""
        }

    # Rule-based extraction first (deterministic, no LLM)
    result = rule_based_extraction(ocr_text)

    if result and (result.get("name") or result.get("dob") or result.get("address")):
        # Found at least some data via rule-based extraction
        logger.info(
            f"Rule-based extraction successful. Found: name={bool(result.get('name'))}, dob={bool(result.get('dob'))}, address={bool(result.get('address'))}")
        return {
            "name": _normalize_name(result.get("name", "")),
            "dob": result.get("dob", ""),
            "address": result.get("address", "")
        }

    # If rule-based extraction fails or incomplete, try OpenAI fallback
    logger.info("Rule-based extraction incomplete, attempting OpenAI extraction...")
    openai_result = extract_with_openai(ocr_text)
    if openai_result:
        logger.info("OpenAI extraction successful")
        return {
            "name": _normalize_name(openai_result.get("name", "")),
            "dob": openai_result.get("dob", ""),
            "address": openai_result.get("address", "")
        }

    logger.error("All extraction methods failed")
    # If everything fails, return empty
    return {
        "name": "",
        "dob": "",
        "address": ""
    }
