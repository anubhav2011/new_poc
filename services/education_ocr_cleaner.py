import json
import re
import os
from typing import Optional
import logging
from openai import OpenAI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# RAW OCR TEXT IS DISCARDED AFTER PROCESSING
# ONLY EXTRACTED FIELDS ARE STORED

EDUCATION_EXTRACTION_PROMPT = """You are given OCR text from an educational document (marksheet, certificate, etc.) from India.

Extract ALL of these fields carefully and completely:

CRITICAL FIELDS (MUST EXTRACT FOR VERIFICATION):
1. name: Student's full name EXACTLY as printed on document. Search in:
   - Student/Candidate name field
   - Roll number row (often has name)
   - Candidate information section
   - Any header with student details
   DO NOT leave blank if name is visible in document

2. dob: Date of birth in DD-MM-YYYY format. Search in:
   - DOB/D.O.B field
   - Date of Birth row
   - Birth date section
   - Enrollment/admission info showing birth date
   DO NOT leave blank if DOB is visible in document

EDUCATIONAL FIELDS:
3. Qualification: The degree/qualification name (e.g., "Bachelor of Science", "Diploma", "Class 12", "Class 10", etc.)
4. Board: The board name (e.g., "CBSE", "ICSE", "State Board", etc.)
5. Year of Passing: Year of completion (in YYYY format)
6. School Name: Name of the school/college/university
7. Stream: The stream or specialization (e.g., "Science", "Commerce", "Arts", "Computer Science", etc.)
8. Marks Type: Specify as either "Percentage" or "CGPA" (look for % or CGPA in document)
9. Marks: The marks value with % or CGPA format (e.g., "62%", "3.5 CGPA")

Important Rules:
- ALWAYS search the entire document for name and DOB - these are CRITICAL for verification
- For name: Copy EXACTLY as printed, preserve capitalization. If multiple name fields, use student's name (not teacher/examiner names)
- For DOB: Normalize to DD-MM-YYYY format. If you see "12/01/1987" convert to "12-01-1987"
- Do NOT infer or guess missing information
- If field is not found on document, set to empty string ""
- Return ONLY valid JSON, no extra text, no markdown
- Handle OCR errors like 'O' for '0' and 'l' for '1'
- For marks_type, choose between "Percentage" or "CGPA" based on the document
- For marks, include the symbol (% or CGPA)

Input OCR text:
{ocr_text}

Return this JSON format exactly (ALL fields required):
{{
    "name": "",
    "dob": "",
    "qualification": "",
    "board": "",
    "year_of_passing": "",
    "school_name": "",
    "stream": "",
    "marks_type": "",
    "marks": ""
}}"""

# OpenAI client: lazy init so OPENAI_API_KEY is read after load_dotenv() (avoids "api_key must be set" at import)
_openai_client_education = None


def get_openai_client_education():
    """Get or create OpenAI client for education extraction. Uses OPENAI_API_KEY from env at call time."""
    global _openai_client_education
    if _openai_client_education is not None:
        return _openai_client_education
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        logger.warning("OPENAI_API_KEY not set; education LLM fallback will be skipped (rule-based only).")
        return None
    try:
        _openai_client_education = OpenAI(api_key=api_key)
        logger.info("OpenAI client initialized for education extraction")
        return _openai_client_education
    except Exception as e:
        logger.warning(f"Failed to initialize OpenAI client for education: {e}")
        return None


def extract_cgpa_value(ocr_text: str) -> str:
    """Extract CGPA value from OCR text with comprehensive pattern matching and logging"""
    logger.debug("Extracting CGPA value...")
    logger.debug(f"[CGPA DEBUG] OCR text preview: {ocr_text[:200]}")

    # Check if CGPA-related keywords exist in text
    if 'cgpa' not in ocr_text.lower() and 'grade point' not in ocr_text.lower():
        logger.debug("[CGPA DEBUG] No CGPA or Grade Point keywords found in text")
        return ""

    logger.debug("[CGPA DEBUG] CGPA-related keywords found, attempting extraction...")

    # Pattern 1: Most flexible - look for "CGPA" followed by digits (handles "CGPA07.4", "CGPA 07.4", "CGPA:07.4")
    # This is the primary pattern that should catch most cases
    pattern1 = r'CGPA[\s:]*(\d+(?:\.\d+)?)'
    match1 = re.search(pattern1, ocr_text, re.IGNORECASE)
    if match1:
        value = match1.group(1)
        logger.info(f"[CGPA DEBUG] Found CGPA via pattern1 (CGPA keyword): {value}")
        return value + " CGPA"
    logger.debug("[CGPA DEBUG] Pattern1 (CGPA keyword) did not match")

    # Pattern 2: Handle "Cumulative Grade Point Average" followed by digits
    # Handles spaces or no spaces between words
    pattern2 = r'Cumulative\s*Grade\s*Point[s]?\s*Average\s*:?\s*(\d+(?:\.\d+)?)'
    match2 = re.search(pattern2, ocr_text, re.IGNORECASE)
    if match2:
        value = match2.group(1)
        logger.info(f"[CGPA DEBUG] Found CGPA via pattern2 (Cumulative Grade Point Average): {value}")
        return value + " CGPA"
    logger.debug("[CGPA DEBUG] Pattern2 (Cumulative Grade Point Average) did not match")

    # Pattern 3: Handle case where CGPA comes after Average without clear separator
    # "...PointAverageCGPA07.4" or "PointAverageCGPA07.4"
    pattern3 = r'(?:Point|Average).*?CGPA\s*(\d+(?:\.\d+)?)'
    match3 = re.search(pattern3, ocr_text, re.IGNORECASE)
    if match3:
        value = match3.group(1)
        logger.info(f"[CGPA DEBUG] Found CGPA via pattern3 (Point/Average context): {value}")
        return value + " CGPA"
    logger.debug("[CGPA DEBUG] Pattern3 (Point/Average context) did not match")

    # Pattern 4: Number before CGPA keyword
    # "07.4 CGPA" or "07.4CGPA" or "07.4  CGPA"
    pattern4 = r'(\d+(?:\.\d+)?)\s*CGPA'
    match4 = re.search(pattern4, ocr_text, re.IGNORECASE)
    if match4:
        value = match4.group(1)
        logger.info(f"[CGPA DEBUG] Found CGPA via pattern4 (number before CGPA): {value}")
        return value + " CGPA"
    logger.debug("[CGPA DEBUG] Pattern4 (number before CGPA) did not match")

    # Pattern 5: Look for GPA/Grade Point followed by number
    pattern5 = r'(?:Grade\s+Point|GPA)\s*:?\s*(\d+(?:\.\d+)?)'
    match5 = re.search(pattern5, ocr_text, re.IGNORECASE)
    if match5:
        value = match5.group(1)
        logger.info(f"[CGPA DEBUG] Found CGPA via pattern5 (Grade Point/GPA): {value}")
        return value + " CGPA"
    logger.debug("[CGPA DEBUG] Pattern5 (Grade Point/GPA) did not match")

    # Pattern 6: Last resort - look for any number that appears to be a GPA score (between 0-10)
    # after any mention of CGPA, GPA, or Grade
    pattern6 = r'(?:CGPA|GPA|Grade Point Average)[^\d]*(\d+(?:\.\d+)?)'
    match6 = re.search(pattern6, ocr_text, re.IGNORECASE)
    if match6:
        value = match6.group(1)
        try:
            # Only return if it's a reasonable GPA value (0-10 range for most systems)
            float_val = float(value)
            if 0 <= float_val <= 10:
                logger.info(f"[CGPA DEBUG] Found CGPA via pattern6 (fallback): {value}")
                return value + " CGPA"
        except ValueError:
            logger.debug(f"[CGPA DEBUG] Pattern6 matched but value '{value}' is not a valid number")
    logger.debug("[CGPA DEBUG] Pattern6 (fallback) did not match or value out of range")

    logger.warning("[CGPA DEBUG] Could not extract CGPA - no patterns matched")
    return ""


def extract_percentage(ocr_text: str) -> str:
    """Extract percentage marks from OCR text"""
    logger.debug("Extracting percentage...")

    # Look for pattern like "62%" or "62.5%"
    pattern = r'([0-9]{1,3}(?:\.[0-9]{1,2})?)\s*%'
    match = re.search(pattern, ocr_text)
    if match:
        value = match.group(0)
        logger.info(f"Found percentage: {value}")
        return value

    logger.debug("Could not extract percentage")
    return ""


def extract_school_name(ocr_text: str) -> str:
    """Extract school/college/institution name from OCR text"""
    logger.debug("Extracting school name...")

    # Split into lines and filter
    lines = [line.strip() for line in ocr_text.split('\n') if line.strip()]

    # Keywords that indicate institution name
    institution_keywords = ['college', 'school', 'university', 'institute', 'institution', 'academy', 'convent',
                            'don bosco']

    # Lines that are exam titles, not school names - exclude these
    exam_title_patterns = [
        r'^SECONDARY\s+SCHOOL\s+EXAMINATION',
        r'^HIGHER\s+SECONDARY\s+EXAMINATION',
        r'EXAMINATION\s*\(?\s*YEAR\s*:',
        r'YEAR\s*:\s*\d{4}\s*\)',
        r'has performed',
        r'grade sheet cum certificate',
        r'certificate of performance',
    ]

    def is_exam_title(text: str) -> bool:
        upper = text.upper().strip()
        return any(re.search(p, upper, re.IGNORECASE) for p in exam_title_patterns)

    def normalize_school_name(s: str) -> str:
        """Strip leading label noise (e.g. 'fuea School ') and fix common OCR typos."""
        if not s or len(s) < 5:
            return s
        # If string contains CBSE-style "CODE-SCHOOL NAME", use only that part (drops 'fuea School ' etc.)
        code_school = re.search(r'\b(\d{4,5}\s*-\s*[A-Z][A-Z0-9\s\-\.!]+)', s)
        if code_school:
            s = code_school.group(1).strip()
        s = re.sub(r'\s+', ' ', s)
        # Common OCR: ! read as I (e.g. KHER! -> KHERI)
        s = re.sub(r'!', 'I', s)
        # Strip leading CBSE-style code (e.g. 08679-) for cleaner display; rest of logic unchanged
        s = re.sub(r'^\d{4,5}-\s*', '', s)
        return s.strip()

    # Strategy 1 (CBSE-style): "08679-ST DON BOSCO COLLEGE LAKHIMPUR KHERI UP" - code hyphen school name
    # Capture the full segment: digits-hyphen-school name (until next section or newline)
    cbse_pattern = r'\b(\d{4,5}\s*-\s*[A-Z][A-Z0-9\s\-\.]+)(?=\s*\n|Roll|Mother|Father|Registration|Registration\s+No|$)'
    match = re.search(cbse_pattern, ocr_text, re.IGNORECASE)
    if match:
        potential_school = match.group(1).strip()
        potential_school = re.sub(r'\s+', ' ', potential_school)
        if len(potential_school) > 10 and not is_exam_title(potential_school):
            if any(kw in potential_school.lower() for kw in institution_keywords):
                logger.info(f"Found school name (Strategy 1 - CBSE pattern): {potential_school}")
                return normalize_school_name(potential_school)
        # Even without keyword, use if it looks like "CODE - SCHOOL NAME" (e.g. ST DON BOSCO COLLEGE...)
        if len(potential_school) > 15 and re.search(r'[A-Z]{2,}\s+[A-Z]', potential_school):
            logger.info(f"Found school name (Strategy 1 - code-school): {potential_school}")
            return normalize_school_name(potential_school)

    # Strategy 2: Look for pattern "number-school name" (generic)
    pattern = r'\b\d+[-\s]+([A-Z][A-Z\s\-]+?)(?:\s{2,}|has performed|$)'
    match = re.search(pattern, ocr_text)
    if match:
        potential_school = match.group(1).strip()
        potential_school = re.sub(r'\s+', ' ', potential_school)
        if (len(potential_school) > 5 and not is_exam_title(potential_school) and
                any(keyword in potential_school.lower() for keyword in institution_keywords)):
            logger.info(f"Found school name (Strategy 2 - Pattern match): {potential_school}")
            return normalize_school_name(potential_school)

    # Strategy 3: Find lines with institution keywords (exclude exam titles)
    for line in lines:
        line_lower = line.lower()
        if len(line) < 8:
            continue
        if is_exam_title(line):
            continue
        if any(keyword in line_lower for keyword in institution_keywords):
            cleaned = re.sub(r'^[0-9\-/\.\s]+', '', line).strip()
            cleaned = re.sub(r'\s+', ' ', cleaned)
            cleaned = re.sub(r'[fF]{2,}', ' ', cleaned)
            cleaned = cleaned.strip()
            if len(cleaned) > 8 and not is_exam_title(cleaned) and any(
                    keyword in cleaned.lower() for keyword in institution_keywords):
                logger.info(f"Found school name (Strategy 3 - Line match): {cleaned}")
                return normalize_school_name(cleaned)

    # Strategy 4: Extract text after "School" / "विद्यालय School" (e.g. "08679-ST DON BOSCO...")
    pattern = r'(?:School|school|विद्यालय)\s*:?\s*(\d{4,5}[-\s]+[A-Z][A-Z0-9\s\-\.]+?)(?=\s*\n|Roll|Mother|$)'
    match = re.search(pattern, ocr_text, re.IGNORECASE)
    if match:
        potential_school = match.group(1).strip()
        potential_school = re.sub(r'\s+', ' ', potential_school)
        if len(potential_school) > 5 and not is_exam_title(potential_school):
            logger.info(f"Found school name (Strategy 4 - After School keyword): {potential_school}")
            return normalize_school_name(potential_school)

    logger.warning("Could not extract school name - using empty string")
    return ""


def extract_year_of_passing(ocr_text: str) -> str:
    """Extract year of passing from OCR text"""
    logger.debug("Extracting year of passing...")

    # Look for 4-digit year pattern (1900-2099) - use non-capturing group
    pattern = r'\b(?:19|20)\d{2}\b'
    matches = re.findall(pattern, ocr_text)

    if matches:
        # Return the last year found (usually the passing year)
        year = matches[-1]
        logger.info(f"Found year of passing: {year}")
        return year

    logger.warning("Could not find year of passing")
    return ""


def extract_qualification(ocr_text: str) -> str:
    """Extract qualification from OCR text"""
    logger.debug("Extracting qualification...")

    ocr_lower = ocr_text.lower()

    # Check for Class X/XII first (most specific and common in Indian education)
    class_patterns = [
        (r'\bclass\s+x\b', 'Class 10'),
        (r'\bclass\s+10\b', 'Class 10'),
        (r'\b10th\b', 'Class 10'),
        (r'\bsecondary\s+school\s+examination\b', 'Class 10'),
        (r'\bclass\s+xii\b', 'Class 12'),
        (r'\bclass\s+12\b', 'Class 12'),
        (r'\b12th\b', 'Class 12'),
        (r'\bhigher\s+secondary\b', 'Class 12'),
    ]

    for pattern, name in class_patterns:
        if re.search(pattern, ocr_lower):
            logger.info(f"Found qualification: {name}")
            return name

    # Check for degree qualifications
    degree_patterns = [
        (r'\bb\.?\s*tech\b', 'B.Tech'),
        (r'\bm\.?\s*tech\b', 'M.Tech'),
        (r'\bb\.?\s*sc\b|\bbachelor\s+of\s+science\b', 'Bachelor of Science'),
        (r'\bb\.?\s*a\b|\bbachelor\s+of\s+arts\b', 'Bachelor of Arts'),
        (r'\bb\.?\s*com\b|\bbachelor\s+of\s+commerce\b', 'Bachelor of Commerce'),
        (r'\bm\.?\s*sc\b|\bmaster\s+of\s+science\b', 'Master of Science'),
        (r'\bm\.?\s*a\b|\bmaster\s+of\s+arts\b', 'Master of Arts'),
        (r'\bbca\b', 'BCA'),
        (r'\bmca\b', 'MCA'),
        (r'\bdiploma\b', 'Diploma'),
    ]

    for pattern, name in degree_patterns:
        if re.search(pattern, ocr_lower):
            logger.info(f"Found qualification: {name}")
            return name

    logger.warning("Could not extract qualification")
    return ""


def extract_board(ocr_text: str) -> str:
    """Extract board from OCR text"""
    logger.debug("Extracting board...")

    ocr_lower = ocr_text.lower()

    board_patterns = [
        (r'\bcentral\s+board\b', 'CBSE'),
        (r'\bcbse\b', 'CBSE'),
        (r'\bicse\b', 'ICSE'),
        (r'\bisc\b', 'ISC'),
        (r'\bstate\s+board\b', 'State Board'),
        (r'\bhsc\b', 'HSC'),
    ]

    for pattern, name in board_patterns:
        if re.search(pattern, ocr_lower):
            logger.info(f"Found board: {name}")
            return name

    logger.debug("Could not extract board")
    return ""


def extract_stream(ocr_text: str) -> str:
    """Extract stream from OCR text"""
    logger.debug("Extracting stream...")

    ocr_lower = ocr_text.lower()

    stream_patterns = [
        (r'\bcomputer\s+science\b', 'Computer Science'),
        (r'\binformation\s+technology\b', 'Information Technology'),
        (r'\bengineering\b', 'Engineering'),
        (r'\bscience\b', 'Science'),
        (r'\bcommerce\b', 'Commerce'),
        (r'\barts\b', 'Arts'),
        (r'\bmedical\b', 'Medical'),
        (r'\bhumanities\b', 'Humanities'),
        (r'\bsocial\s+science\b', 'Social Science'),
    ]

    for pattern, name in stream_patterns:
        if re.search(pattern, ocr_lower):
            logger.info(f"Found stream: {name}")
            return name

    logger.debug("Could not extract stream")
    return ""


def extract_marks_and_type(ocr_text: str) -> tuple:
    """Extract marks and marks type from OCR text. Returns (marks, marks_type)"""
    logger.debug("Extracting marks and marks type...")

    # Try percentage first
    percentage = extract_percentage(ocr_text)
    if percentage and percentage.strip():  # Check if not empty
        logger.info(f"Extracted percentage marks: {percentage}")
        return percentage, "Percentage"

    # Try CGPA
    cgpa = extract_cgpa_value(ocr_text)
    if cgpa and cgpa.strip():  # Check if not empty
        logger.info(f"Extracted CGPA marks: {cgpa}")
        return cgpa, "CGPA"

    # If no marks found, return both empty
    logger.debug("Could not extract marks - returning empty values")
    return "", ""


def rule_based_education_extraction(ocr_text: str) -> dict:
    """
    Rule-based extraction for educational documents using multiple strategies.
    Now also attempts to extract name and DOB for identity verification.
    """
    if not ocr_text or len(ocr_text.strip()) < 10:
        logger.warning("OCR text too short for education extraction")
        return {
            "name": "",
            "dob": "",
            "qualification": "",
            "board": "",
            "year_of_passing": "",
            "school_name": "",
            "stream": "",
            "marks_type": "",
            "marks": ""
        }

    result = {
        "name": "",
        "dob": "",
        "qualification": extract_qualification(ocr_text),
        "board": extract_board(ocr_text),
        "year_of_passing": extract_year_of_passing(ocr_text),
        "school_name": extract_school_name(ocr_text),
        "stream": extract_stream(ocr_text),
        "marks_type": "",
        "marks": ""
    }

    # Extract marks and marks_type
    marks, marks_type = extract_marks_and_type(ocr_text)
    result["marks"] = marks
    result["marks_type"] = marks_type

    # Attempt to extract name - look for common patterns in educational documents
    logger.debug("Attempting to extract name from educational document...")
    lines = [line.strip() for line in ocr_text.split('\n') if line.strip()]

    # Pattern 1: "Name:" or "Student Name:"
    name_pattern = r'(?:Name|Student Name|Candidate Name)\s*:?\s*([A-Z][A-Za-z\s]+?)(?:\n|Roll|Father|Mother|$)'
    name_match = re.search(name_pattern, ocr_text, re.IGNORECASE)
    if name_match:
        extracted_name = name_match.group(1).strip()
        if len(extracted_name) > 3 and len(extracted_name) < 100:
            result["name"] = extracted_name
            logger.info(f"Rule-based: Found name: {result['name']}")

    # Attempt to extract DOB - look for common patterns
    logger.debug("Attempting to extract DOB from educational document...")

    # Pattern 1: "DOB:" or "Date of Birth:"
    dob_patterns = [
        r'(?:DOB|D\.O\.B|Date\s+of\s+Birth)\s*:?\s*(\d{1,2})[/-](\d{1,2})[/-](\d{4})',
        r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b',  # General date pattern
    ]

    for pattern in dob_patterns:
        dob_match = re.search(pattern, ocr_text, re.IGNORECASE)
        if dob_match:
            day, month, year = dob_match.groups()[:3]
            result["dob"] = f"{day}-{month}-{year}"
            logger.info(f"Rule-based: Found DOB: {result['dob']}")
            break

    logger.info(
        f"Rule-based extraction result: name={repr(result['name'])}, dob={repr(result['dob'])}, qualification={result['qualification']}, board={result['board']}, year={result['year_of_passing']}, school={result['school_name']}, stream={result['stream']}, marks={result['marks']}, marks_type={result['marks_type']}")
    return result


def parse_education_response(response_text: str) -> Optional[dict]:
    """Parse JSON response from LLM education extraction"""
    try:
        # Find JSON in response
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            logger.debug(f"Extracted JSON: {json_str}")
            data = json.loads(json_str)

            # Validate all fields exist (including name and dob)
            required_fields = ["name", "dob", "qualification", "board", "year_of_passing", "school_name", "stream",
                               "marks_type", "marks"]
            if isinstance(data, dict) and all(key in data for key in required_fields):
                result = {
                    "name": str(data.get("name", "")).strip(),
                    "dob": str(data.get("dob", "")).strip(),
                    "qualification": str(data.get("qualification", "")).strip(),
                    "board": str(data.get("board", "")).strip(),
                    "year_of_passing": str(data.get("year_of_passing", "")).strip(),
                    "school_name": str(data.get("school_name", "")).strip(),
                    "stream": str(data.get("stream", "")).strip(),
                    "marks_type": str(data.get("marks_type", "")).strip(),
                    "marks": str(data.get("marks", "")).strip()
                }
                logger.info(f"[PARSE] Parsed response: name={repr(result['name'])}, dob={repr(result['dob'])}")
                return result
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
    except Exception as e:
        logger.error(f"Error parsing education response: {e}")

    return None


def extract_education_with_openai(ocr_text: str) -> Optional[dict]:
    """Use OpenAI to extract education data if rule-based extraction fails"""
    openai_client = get_openai_client_education()
    if not openai_client:
        logger.debug("OpenAI client not available for education; using rule-based extraction only.")
        return None

    try:
        logger.info("Attempting OpenAI extraction for education...")
        prompt = EDUCATION_EXTRACTION_PROMPT.format(ocr_text=ocr_text)

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=500
        )

        if response.choices and len(response.choices) > 0:
            response_text = response.choices[0].message.content
            logger.info(f"OpenAI response: {response_text}")

            result = parse_education_response(response_text)
            if result:
                logger.info("OpenAI extraction successful")
                return result

    except Exception as e:
        logger.error(f"OpenAI extraction failed: {e}")

    return None


def clean_education_ocr_extraction(ocr_text: str) -> dict:
    """
    Clean OCR text from educational document and extract all necessary fields including name and DOB.
    Try rule-based first, then fallback to OpenAI if critical fields are missing.
    """
    logger.info("=== Starting Education OCR extraction ===")
    logger.debug(f"OCR text length: {len(ocr_text)} characters")
    logger.debug(f"Raw OCR text preview (first 300 chars): {ocr_text[:300]}")

    if not ocr_text or len(ocr_text.strip()) < 10:
        logger.error("OCR text is empty or too short")
        return {
            "name": "",
            "dob": "",
            "qualification": "",
            "board": "",
            "year_of_passing": "",
            "school_name": "",
            "stream": "",
            "marks_type": "",
            "marks": ""
        }

    # Rule-based extraction first (deterministic, no LLM cost)
    result = rule_based_education_extraction(ocr_text)

    logger.info(f"[RULE-BASED] Extracted: name={repr(result.get('name'))}, dob={repr(result.get('dob'))}")

    # Check if we have critical fields
    has_name = bool(result.get("name", "").strip())
    has_dob = bool(result.get("dob", "").strip())
    has_qualification = bool(result.get("qualification", "").strip())
    has_year = bool(result.get("year_of_passing", "").strip())
    has_school = bool(result.get("school_name", "").strip())

    logger.info(
        f"Rule-based extraction results - Name: {has_name}, DOB: {has_dob}, Qualification: {has_qualification}, Year: {has_year}, School: {has_school}")

    # If we're missing critical data (especially name and dob for verification), try OpenAI
    # Prioritize name and DOB since they're needed for verification
    if not (has_name and has_dob) or not (has_qualification and has_year and has_school):
        logger.info(
            "Missing critical fields (name/dob for verification or education fields), attempting OpenAI extraction...")
        openai_result = extract_education_with_openai(ocr_text)

        if openai_result:
            logger.info(
                f"[OPENAI] Extracted: name={repr(openai_result.get('name'))}, dob={repr(openai_result.get('dob'))}")
            # Merge results: use OpenAI values for empty fields
            for key in result:
                if not result[key] and openai_result.get(key):
                    result[key] = openai_result[key]
                    logger.info(f"[MERGE] Using OpenAI value for {key}: {repr(result[key])}")
            logger.info("OpenAI merged with rule-based extraction")

    logger.info(
        f"[FINAL] Education extraction result: name={repr(result.get('name'))}, dob={repr(result.get('dob'))}, qualification={result.get('qualification')}")
    return result
