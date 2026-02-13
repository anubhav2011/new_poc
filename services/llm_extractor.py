import json
import os
import re
from typing import Optional, Dict
from openai import OpenAI
import logging

logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None


def normalize_date_format(date_str: str) -> str:
    """
    Normalize various date formats to DD-MM-YYYY.

    Handles:
    - DD/MM/YYYY -> DD-MM-YYYY
    - DD.MM.YYYY -> DD-MM-YYYY
    - YYYY-MM-DD -> DD-MM-YYYY
    - D-M-YYYY -> DD-MM-YYYY (add leading zeros)
    """
    if not date_str:
        return ""

    date_str = str(date_str).strip()

    # Replace common separators with hyphen
    date_str = date_str.replace('/', '-').replace('.', '-').replace(' ', '-')

    # Split by hyphen
    parts = date_str.split('-')

    if len(parts) != 3:
        return date_str  # Return as-is if format is unexpected

    # Check if format is YYYY-MM-DD
    if len(parts[0]) == 4 and parts[0].isdigit():
        # YYYY-MM-DD -> DD-MM-YYYY
        year, month, day = parts
        return f"{day.zfill(2)}-{month.zfill(2)}-{year}"

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

    return f"{day}-{month}-{year}"


def call_llm_with_retry(prompt: str, system_prompt: str, max_retries: int = 3) -> Optional[Dict]:
    """
    Call OpenAI API with retry logic and JSON parsing.

    Args:
        prompt: User prompt with instructions
        system_prompt: System role instructions
        max_retries: Maximum retry attempts

    Returns:
        Parsed JSON dict or None if failed
    """
    if not openai_client:
        logger.error("OpenAI API key not set. Cannot extract data with LLM.")
        return None

    for attempt in range(max_retries):
        try:
            logger.info(f"LLM extraction attempt {attempt + 1}/{max_retries}")

            response = openai_client.chat.completions.create(
                model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # Low temperature for consistent extraction
                max_tokens=2000
            )

            content = response.choices[0].message.content.strip()
            logger.info(f"LLM response received: {len(content)} characters")

            # Remove markdown code blocks if present
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'```\s*', '', content)
            content = content.strip()

            # Parse JSON
            try:
                data = json.loads(content)
                logger.info(f"Successfully parsed JSON response: {list(data.keys())}")

                # Validate that response is a dict
                if not isinstance(data, dict):
                    logger.error(f"LLM response is not a dict: {type(data)}")
                    if attempt < max_retries - 1:
                        logger.info("Retrying LLM call...")
                        continue
                    else:
                        return None

                return data
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse error on attempt {attempt + 1}: {e}")
                logger.warning(f"Response content: {content[:500]}")

                # Try to extract JSON from text if it's embedded
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    try:
                        data = json.loads(json_match.group())
                        logger.info("Successfully extracted JSON from response text")
                        return data
                    except json.JSONDecodeError:
                        pass

                if attempt < max_retries - 1:
                    logger.info("Retrying LLM call...")
                    continue
                else:
                    logger.error(f"Failed to parse JSON after {max_retries} attempts")
                    return None

        except Exception as e:
            logger.error(f"LLM API call error on attempt {attempt + 1}: {str(e)}", exc_info=True)
            if attempt < max_retries - 1:
                logger.info("Retrying LLM call...")
                continue
            else:
                logger.error(f"LLM API call failed after {max_retries} attempts")
                return None

    return None


def extract_personal_data_llm(raw_ocr_text: str) -> Optional[Dict]:
    """
    Extract structured personal document data using LLM.

    Args:
        raw_ocr_text: Complete OCR text from personal document (Aadhaar, PAN, etc.)

    Returns:
        Dict with extracted data:
        {
            "name": "BABU KHAN",
            "dob": "01-12-1987",
            "address": "KAMLA RAMAN NAGAR...",
            "mobile": "7905285898"
        }
    """
    logger.info("=== Starting LLM extraction for PERSONAL document ===")
    logger.info(f"OCR text length: {len(raw_ocr_text)} characters")

    system_prompt = """You are an expert data extraction assistant specializing in Indian identity documents (Aadhaar, PAN Card, Voter ID, etc.).

Your task is to extract structured information from OCR text and return ONLY a valid JSON object. Do not include any explanations or markdown formatting."""

    user_prompt = f"""Extract the following information from this personal identity document OCR text:

Required fields:
- name: Full name of the person (as printed on document)
- dob: Date of birth in DD-MM-YYYY format (extract and convert if needed)
- address: Complete address as printed on document
- mobile: Mobile number (if present on document, otherwise null)

Important instructions:
1. Extract the EXACT name as printed on the document
2. Convert date of birth to DD-MM-YYYY format (e.g., "01-12-1987")
3. If any field is not found or unclear, set it to null
4. Return ONLY a JSON object with these exact field names
5. Do not include any explanations or markdown

OCR Text:
\"\"\"
{raw_ocr_text}
\"\"\"

Return ONLY the JSON object:"""

    result = call_llm_with_retry(user_prompt, system_prompt)

    if result:
        # Validate required fields exist
        required_personal_fields = ["name", "dob", "address", "mobile"]
        missing_fields = [f for f in required_personal_fields if f not in result]
        if missing_fields:
            logger.warning(f"[PERSONAL-LLM] Missing fields in LLM response: {missing_fields}")
            for field in missing_fields:
                result[field] = None

        # Normalize date format
        if result.get('dob'):
            result['dob'] = normalize_date_format(result['dob'])

        logger.info(f"✓ Personal data extracted successfully: name={result.get('name')}, dob={result.get('dob')}")
        return result
    else:
        logger.error("✗ Failed to extract personal data with LLM")
        return None


def extract_educational_data_llm(raw_ocr_text: str) -> Optional[Dict]:
    """
    Extract structured educational document data using LLM.
    MANDATORY: name and dob MUST be extracted.

    Args:
        raw_ocr_text: Complete OCR text from educational document (marksheet)

    Returns:
        Dict with extracted data including MANDATORY name and dob fields
    """
    logger.info("=== Starting LLM extraction for EDUCATIONAL document ===")
    logger.info(f"OCR text length: {len(raw_ocr_text)} characters")

    system_prompt = """You are an expert document extraction specialist for Indian educational documents.

Your PRIMARY task is to EXTRACT the student's NAME and DATE OF BIRTH from the document.
These are MANDATORY fields. If they exist anywhere on the document, you MUST find them.
Return a valid JSON object with exact extracted data."""

    user_prompt = f"""MANDATORY EXTRACTION REQUIRED:

You MUST extract these CRITICAL fields from the educational document OCR text:

1. **name** (MANDATORY): Student's full name - Search EVERYWHERE:
   - Top of page in name field
   - Next to roll number
   - In candidate information section
   - In header "Name of Student"
   - Return EXACTLY as printed on document
   - Do NOT return null unless absolutely not on document

2. **dob** (MANDATORY): Date of birth - Search EVERYWHERE:
   - DOB field / Date of Birth field
   - D.O.B or D/O/B notation
   - Birth date in any format
   - Return in DD-MM-YYYY format ONLY
   - Do NOT return null unless absolutely not on document

3. **qualification**: Class 10 or Class 12 (e.g., "Class 10", "Class 12", "Standard 12")
4. **board**: Board name (CBSE, ICSE, State Board, UP Board, etc.)
5. **year_of_passing**: Year in YYYY format
6. **school_name**: School/College name  
7. **stream**: Science/Commerce/Arts (null for Class 10)
8. **marks_type**: "Percentage" or "CGPA"
9. **marks**: Value with unit (e.g., "7.4 CGPA", "85%")
10. **document_type**: Always "marksheet"

CRITICAL RULES:
- name and dob are NON-NEGOTIABLE. Search the ENTIRE document
- If name/dob is visible ANYWHERE on the page, you MUST extract it
- Return null ONLY if genuinely not present after thorough search
- All other fields can be null if not found

OCR Text:
\"\"\"
{raw_ocr_text}
\"\"\"

Return ONLY this JSON format (ALL fields required):
{{
    "name": "EXTRACTED_NAME_HERE",
    "dob": "DD-MM-YYYY",
    "qualification": "Class 10",
    "board": "CBSE",
    "year_of_passing": "2017",
    "school_name": "SCHOOL_NAME",
    "stream": null,
    "marks_type": "CGPA",
    "marks": "7.4 CGPA",
    "document_type": "marksheet"
}}

NO explanations, NO markdown, ONLY JSON."""

    logger.info(f"[EDU-LLM] Sending MANDATORY extraction prompt to LLM...")
    logger.info(f"[EDU-LLM] Prompt emphasizes name and dob are MANDATORY fields")

    result = call_llm_with_retry(user_prompt, system_prompt)

    if result:
        logger.info(f"[EDU-LLM] [STEP 1] LLM returned result with keys: {list(result.keys())}")
        logger.info(f"[EDU-LLM] [STEP 1] name={repr(result.get('name'))}, dob={repr(result.get('dob'))}")

        # Validate required fields exist
        required_edu_fields = ["name", "dob", "qualification", "board", "year_of_passing", "school_name", "stream",
                               "marks_type", "marks", "document_type"]
        missing_fields = [f for f in required_edu_fields if f not in result]
        if missing_fields:
            logger.warning(f"[EDU-LLM] Missing fields in LLM response: {missing_fields}")
            for field in missing_fields:
                result[field] = None

        # CRITICAL: Ensure name and dob exist (even if None)
        if "name" not in result:
            logger.warning(f"[EDU-LLM] ✗ 'name' field missing from LLM response, setting to None")
            result["name"] = None

        if "dob" not in result:
            logger.warning(f"[EDU-LLM] ✗ 'dob' field missing from LLM response, setting to None")
            result["dob"] = None

        # Clean and normalize name
        name_value = result.get("name")
        if name_value and isinstance(name_value, str):
            name_value = name_value.strip()
            if name_value.lower() in ["null", "none", "", "n/a"]:
                result["name"] = None
                logger.warning(f"[EDU-LLM] Name is empty/null string, setting to None")
            else:
                result["name"] = name_value
                logger.info(f"[EDU-LLM] ✓ Name extracted: {repr(result['name'])}")
        else:
            logger.warning(f"[EDU-LLM] Name field is None or not string")

        # Clean and normalize DOB
        dob_value = result.get("dob")
        if dob_value and isinstance(dob_value, str):
            dob_value = dob_value.strip()
            if dob_value.lower() in ["null", "none", "", "n/a"]:
                result["dob"] = None
                logger.warning(f"[EDU-LLM] DOB is empty/null string, setting to None")
            else:
                # Normalize DOB format
                result["dob"] = normalize_date_format(dob_value)
                logger.info(f"[EDU-LLM] ✓ DOB extracted & normalized: {repr(result['dob'])}")
        else:
            logger.warning(f"[EDU-LLM] DOB field is None or not string")

        # Normalize qualification
        if result.get('qualification'):
            qual = result['qualification'].upper()
            if 'X' in qual and '12' not in qual and 'XII' not in qual:
                result['qualification'] = 'Class 10'
            elif 'XII' in qual or '12' in qual:
                result['qualification'] = 'Class 12'

        logger.info(f"[EDU-LLM] [FINAL] Educational data extracted:")
        logger.info(f"[EDU-LLM]   name={repr(result.get('name'))}")
        logger.info(f"[EDU-LLM]   dob={repr(result.get('dob'))}")
        logger.info(f"[EDU-LLM]   qualification={result.get('qualification')}")
        logger.info(f"[EDU-LLM]   board={result.get('board')}")
        logger.info(f"[EDU-LLM]   school_name={result.get('school_name')}")

        return result
    else:
        logger.error("✗ Failed to extract educational data with LLM")
        return None


def extract_data_with_fallback(raw_ocr_text: str, document_type: str) -> Optional[Dict]:
    """
    Extract data with LLM, with fallback to empty structure if LLM unavailable.

    Args:
        raw_ocr_text: Complete OCR text
        document_type: "personal" or "educational"

    Returns:
        Extracted data dict or None
    """
    if document_type == "personal":
        return extract_personal_data_llm(raw_ocr_text)
    elif document_type == "educational":
        return extract_educational_data_llm(raw_ocr_text)
    else:
        logger.error(f"Unknown document type: {document_type}")
        return None
