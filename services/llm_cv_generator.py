import json
import os
import re
from typing import Optional, Dict
from openai import OpenAI
import logging

logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None


def clean_location_for_cv(location_text: str) -> str:
    """
    Clean location name for CV display - extract only city name.
    """
    if not location_text:
        return ""

    text_lower = location_text.lower().strip()

    # Common Indian cities
    cities = [
        "delhi", "mumbai", "bangalore", "bengaluru", "hyderabad", "pune",
        "kolkata", "chennai", "ahmedabad", "indore", "nagpur", "jaipur",
        "lucknow", "kanpur", "patna", "bhopal", "visakhapatnam", "vadodara",
        "noida", "gurgaon", "gurugram", "faridabad", "ghaziabad", "greater noida",
        "thane", "navi mumbai", "howrah", "pimpri-chinchwad", "allahabad", "meerut"
    ]

    # Check if any city name is in the text
    for city in cities:
        if city in text_lower:
            return city.title()

    # Remove common Hindi/Hinglish words
    words_to_remove = [
        "me", "mein", "ke", "pass", "mujhe", "karna", "chahta", "hai", "hu", "hain",
        "aur", "kab", "se", "kaam", "shuru", "kar", "sakte", "hain", "area", "mien"
    ]

    words = text_lower.split()
    cleaned_words = [w for w in words if w not in words_to_remove and len(w) > 2]

    if cleaned_words:
        return cleaned_words[0].title()

    return location_text.strip()


CV_GENERATION_PROMPT = """You are a professional CV/resume generator for blue-collar and grey-collar workers in India.

Generate a professional, one-page HTML CV based on the provided worker data. The CV should be:
- Clean and professional
- Easy to read
- Suitable for blue-collar/grey-collar job applications
- Include all relevant sections including Personal Information (DOB, Phone, Address, Location)
- Display name with proper spacing: First Name and Last Name on separate lines with margin between them
- Use proper HTML structure with inline CSS

**CRITICAL REQUIREMENTS:**
1. Name: Display first and last names on SEPARATE LINES with proper spacing (8-10px margin-bottom)
2. Personal Details Section: Must include Date of Birth, Contact Number, Current Location, and Address
3. All sections properly formatted and easy to read
4. Print-friendly design

Worker Data:
{worker_data}

Generate a complete HTML CV. Return ONLY the HTML code, no markdown, no code blocks, just the HTML."""

CV_TEMPLATE_PROMPT = """You are a professional CV/resume generator specializing in blue-collar and grey-collar worker CVs for the Indian job market.

Generate a professional, one-page HTML CV with the following structure and styling:

**REQUIRED STRUCTURE:**
1. **Header Section** (Centered, prominent)
   - Full Name: Display FIRST NAME and LAST NAME on SEPARATE LINES with proper spacing (margin-bottom: 8px between them)
   - Name should be large and bold (28-32px), with each name part on its own line
   - Below name: Contact Information showing DOB, Phone Number, Preferred Location, Address
   - **IMPORTANT**: Preferred Location must be ONLY the city name (e.g., "Delhi", "Noida", "Mumbai") - NO extra words
   - Subtle border-bottom separator

2. **Professional Summary** (2-3 sentences)
   - Highlight job title, years of experience, key skills
   - Professional tone, suitable for job applications
   - Example: "Experienced [Job Title] with [X] years of professional experience specializing in [key skills]. Proficient in [tools/equipment]. Available for work in [location]."

3. **Personal Information Section** (Right panel or dedicated area)
   - Date of Birth (label: "Date of Birth:")
   - Contact Number (label: "Contact Number:" or "Phone Number:")
   - Current Location (label: "Current Location:")
   - Address (label: "Address:" - show full address from data)

4. **Work Experience Section**
   - Job Title/Profession (bold)
   - Total Experience Duration (calculated from all workplaces in years and months)
   - Work Experience Breakdown (if multiple workplaces):
     * Company Name
     * Duration at each workplace
   - Key Skills (bullet points or comma-separated)
   - Tools & Equipment (if available)

5. **Education Section** (if available)
   - Qualification
   - Board/University
   - School/College Name
   - Year of Passing
   - Marks/Percentage

6. **Skills & Tools Section**
   - Comprehensive list of skills
   - Tools and equipment expertise

**STYLING REQUIREMENTS:**
- Clean, professional design suitable for Indian job market
- Use Arial or similar sans-serif fonts
- Color scheme: Professional blue (#1E3A8A) for headers, black for text
- Section headers with background color (#f0f0f0)
- Proper spacing and margins
- One-page format (8.5 x 11 inches)
- Print-friendly design
- Inline CSS only (no external stylesheets)

**CRITICAL DATA CLEANING:**
- Preferred Location: Display ONLY the city name (e.g., "Delhi", "Noida", "Mumbai")
- Remove ALL extra words like "me", "mein", "ke pass", "mujhe karna", etc.
- If location contains phrases like "delhi me mujhe karna hai", extract only "Delhi"
- Job Title: Clean professional title (e.g., "Electrician", "Plumber", "Driver")

**Worker Data (JSON):**
{worker_data}

Generate complete, valid HTML with inline CSS. Return ONLY the HTML code, no markdown, no code blocks, no explanations. The HTML should be ready to convert to PDF."""

CV_TEMPLATE_PROMPT_WITH_TRANSCRIPT = """You are a professional CV/resume generator specializing in blue-collar and grey-collar worker CVs for the Indian job market.

Generate a professional, one-page HTML CV with the following structure and styling:

**REQUIRED STRUCTURE:**
1. **Header Section** (Centered, prominent)
   - Full Name: Display FIRST NAME and LAST NAME on SEPARATE LINES with proper spacing (margin-bottom: 8px between them)
   - Name should be large and bold (28-32px), with each name part on its own line
   - Below name: Contact Information showing DOB, Phone Number, Preferred Location, Address
   - **IMPORTANT**: Preferred Location must be ONLY the city name (e.g., "Delhi", "Noida", "Mumbai") - NO extra words
   - Subtle border-bottom separator

2. **Professional Summary** (2-3 sentences)
   - Highlight job title, years of experience, key skills
   - Use details from the conversation transcript to make it more personalized and authentic
   - Professional tone, suitable for job applications
   - Example: "Experienced [Job Title] with [X] years of professional experience specializing in [key skills]. Proficient in [tools/equipment]. Available for work in [location]."

3. **Personal Information Section** (Right panel or dedicated area)
   - Date of Birth (label: "Date of Birth:")
   - Contact Number (label: "Contact Number:" or "Phone Number:")
   - Current Location (label: "Current Location:")
   - Address (label: "Address:" - show full address from data)

4. **Work Experience Section**
   - Job Title/Profession (bold)
   - Total Experience Duration (calculated from all workplaces in years and months)
   - Work Experience Breakdown (if multiple workplaces):
     * Company Name
     * Duration at each workplace
   - Key Skills (bullet points or comma-separated)
   - Tools & Equipment (if available)
   - **Use conversation transcript to add specific details about work experience, projects, or achievements mentioned**

5. **Education Section** (if available)
   - Qualification
   - Board/University
   - School/College Name
   - Year of Passing
   - Marks/Percentage

6. **Skills & Tools Section**
   - Comprehensive list of skills
   - Tools and equipment expertise
   - **Extract additional skills mentioned in the conversation transcript**

**STYLING REQUIREMENTS:**
- Clean, professional design suitable for Indian job market
- Use Arial or similar sans-serif fonts
- Color scheme: Professional blue (#1E3A8A) for headers, black for text
- Section headers with background color (#f0f0f0)
- Proper spacing and margins
- One-page format (8.5 x 11 inches)
- Print-friendly design
- Inline CSS only (no external stylesheets)

**CRITICAL DATA CLEANING:**
- Preferred Location: Display ONLY the city name (e.g., "Delhi", "Noida", "Mumbai")
- Remove ALL extra words like "me", "mein", "ke pass", "mujhe karna", etc.
- If location contains phrases like "delhi me mujhe karna hai", extract only "Delhi"
- Job Title: Clean professional title (e.g., "Electrician", "Plumber", "Driver")

**Worker Data (JSON):**
{worker_data}

**Conversation Transcript (for additional context):**
{transcript}

**IMPORTANT:** Use the conversation transcript to:
- Add specific details about work experience mentioned in conversation
- Include any achievements, projects, or special skills mentioned
- Make the professional summary more personalized and authentic
- Extract any additional skills or tools not captured in structured data
- Add context about work style, reliability, or other positive attributes mentioned

Generate complete, valid HTML with inline CSS. Return ONLY the HTML code, no markdown, no code blocks, no explanations. The HTML should be ready to convert to PDF."""


def generate_cv_with_llm(worker_data: dict, experience_data: dict, education_data: dict = None,
                         transcript: str = None) -> Optional[str]:
    """
    Generate professional CV using LLM based on complete worker data and transcript.

    Args:
        worker_data: Personal information (name, mobile, dob, address)
        experience_data: Work experience (job_title, skills, tools, etc.)
        education_data: Educational qualifications (optional)
        transcript: Full conversation transcript (optional, for richer CV content)

    Returns:
        HTML string of the CV or None if LLM unavailable
    """
    try:
        if not openai_client:
            logger.warning("OpenAI API key not set, falling back to template-based CV generation")
            return None

        # Prepare complete data structure - include all personal and professional information
        complete_data = {
            "personal": {
                "name": worker_data.get("name", "Worker"),
                "mobile_number": worker_data.get("mobile_number", ""),
                "dob": worker_data.get("dob", ""),
                "address": worker_data.get("address", ""),
                "current_location": worker_data.get("current_location", "")
            },
            "experience": {
                "job_title": experience_data.get("job_title") or experience_data.get("primary_skill", ""),
                "total_experience": experience_data.get(
                    "total_experience") or f"{experience_data.get('experience_years', 0)} years",
                "total_experience_years_float": experience_data.get("experience_years_float", experience_data.get("experience_years", 0)),
                "skills": experience_data.get("skills", []),
                "tools": experience_data.get("tools", []),
                "workplaces": experience_data.get("workplaces", []),
                "preferred_location": clean_location_for_cv(experience_data.get("preferred_location", "")),
                "current_location": experience_data.get("current_location", ""),
                "availability": experience_data.get("availability", "Not specified")
            }
        }

        if education_data:
            complete_data["education"] = {
                "qualification": education_data.get("qualification", ""),
                "board": education_data.get("board", ""),
                "school_name": education_data.get("school_name", ""),
                "year_of_passing": education_data.get("year_of_passing", ""),
                "marks": education_data.get("marks", ""),
                "percentage": education_data.get("percentage", "")
            }

        # Format data for prompt
        worker_data_json = json.dumps(complete_data, indent=2, ensure_ascii=False)

        # Prepare transcript (limit length to avoid token limits)
        transcript_text = ""
        if transcript:
            # Limit transcript to last 2000 characters to stay within token limits
            transcript_text = transcript.strip()[-2000:] if len(transcript) > 2000 else transcript.strip()

        # Use transcript-enhanced prompt if transcript available
        if transcript_text:
            prompt = CV_TEMPLATE_PROMPT_WITH_TRANSCRIPT.format(
                worker_data=worker_data_json,
                transcript=transcript_text
            )
            logger.info(f"Generating CV with transcript context (transcript length: {len(transcript_text)} chars)")
        else:
            prompt = CV_TEMPLATE_PROMPT.format(worker_data=worker_data_json)
            logger.info("Generating CV without transcript (transcript not available)")

        # Generate CV using LLM (using cost-effective gpt-4o-mini)
        response = openai_client.chat.completions.create(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),  # Cost-effective and accurate
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional CV/resume generator specializing in blue-collar and grey-collar worker CVs for the Indian job market. Generate clean, professional, one-page HTML CVs with inline CSS. Always return valid HTML only, no markdown, no code blocks, no explanations. The HTML must be complete and ready for PDF conversion."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2,  # Lower temperature for more consistent, professional output
            max_tokens=3000  # Increased for transcript-enhanced CVs
        )

        cv_html = response.choices[0].message.content.strip()

        # Clean up the response (remove markdown code blocks if present)
        cv_html = re.sub(r'```html\s*', '', cv_html)
        cv_html = re.sub(r'```\s*', '', cv_html)
        cv_html = cv_html.strip()

        # Validate it's HTML
        if not cv_html.startswith('<!DOCTYPE') and not cv_html.startswith('<html') and not cv_html.startswith('<div'):
            logger.warning("LLM response doesn't look like HTML, wrapping in basic structure")
            cv_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Resume - {complete_data['personal']['name']}</title>
</head>
<body>
{cv_html}
</body>
</html>"""

        logger.info("CV generated successfully using LLM" + (" with transcript" if transcript_text else ""))
        return cv_html

    except Exception as e:
        logger.error(f"Error generating CV with LLM: {str(e)}", exc_info=True)
        return None
