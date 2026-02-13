# import json
# import os
# import re
# from typing import Optional
# from openai import OpenAI
#
# """
# Experience Extractor - Structure raw responses into JSON
# Uses LLM only for final structuring (not conversation control)
# """
# import logging
#
# logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG)
#
# # Initialize OpenAI client (lazy / safe if key missing)
# openai_client = None
# try:
#     if os.getenv("OPENAI_API_KEY"):
#         openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
# except Exception as e:
#     logger.warning(f"OpenAI client not initialized for experience extractor: {e}")
#
# STRUCTURING_PROMPT = """You are a data extraction expert for blue-collar and grey-collar workers.
# Extract and structure work experience information from raw responses in Hindi, Hinglish, or English.
#
# IMPORTANT RULES:
# 1. Translate all values to clean English
# 2. Extract job title/profession from primary_skill (e.g., "mai electrician ka" → "Electrician")
# 3. Extract years of experience as integer
# 4. Separate skills and tools into distinct arrays
# 5. **LOCATION EXTRACTION (CRITICAL)**: Extract ONLY the city/location name. Remove ALL extra words.
#    - Examples: "delhi me mujhe karna hai" → "Delhi"
#    - "noida ke pass mai kaam karna chahta hu" → "Noida"
#    - "mumbai mein" → "Mumbai"
#    - Remove words like: "me", "mein", "ke pass", "mujhe", "karna", "chahta", "hai", "hu", etc.
#    - Return ONLY the city name in proper case (e.g., "Delhi", "Noida", "Mumbai")
# 6. Extract availability if mentioned
# 7. Return ONLY valid JSON, no additional text
#
# Raw responses:
# {responses}
#
# Return JSON in this exact format:
# {{
#     "job_title": "Clean job title in English",
#     "total_experience": "X years",
#     "skills": ["skill1", "skill2", "skill3"],
#     "tools": ["tool1", "tool2"],
#     "preferred_location": "City name only (e.g., Delhi, Noida, Mumbai)",
#     "availability": "Immediate" or "Available from date" or "Not specified"
# }}"""
#
#
# def extract_from_responses(responses: dict) -> dict:
#     """
#     Extract structured experience data from collected responses.
#     Uses rule-based parsing first, then OpenAI for complex cases.
#
#     responses: {
#         "primary_skill": "raw response",
#         "experience_years": "raw response",
#         "skills": "raw response",
#         "preferred_location": "raw response"
#     }
#     """
#     logger.info("[EXTRACTION] Starting extract_from_responses()")
#     logger.info(f"[EXTRACTION] Input fields: {list(responses.keys())}")
#
#     result = {
#         "primary_skill": "",
#         "experience_years": 0,
#         "skills": [],
#         "tools": [],
#         "preferred_location": ""
#     }
#
#     # Primary skill
#     logger.info("[EXTRACTION] Extracting primary_skill...")
#     if "primary_skill" in responses:
#         skill_text = responses["primary_skill"]
#         if isinstance(skill_text, str) and len(skill_text) > 0:
#             # Extract first meaningful phrase
#             words = skill_text.split()
#             result["primary_skill"] = " ".join(words[:3]).strip()
#             logger.info(f"[EXTRACTION]   ✓ Primary skill: {result['primary_skill']}")
#
#     # Experience years
#     logger.info("[EXTRACTION] Extracting experience_years...")
#     if "experience_years" in responses:
#         exp_text = responses["experience_years"]
#         try:
#             # Try to extract number
#             numbers = re.findall(r'\d+', str(exp_text))
#             if numbers:
#                 result["experience_years"] = int(numbers[0])
#                 logger.info(f"[EXTRACTION]   ✓ Years of experience: {result['experience_years']}")
#         except:
#             logger.warning(f"[EXTRACTION]   ⚠ Failed to parse experience_years: {exp_text}")
#             pass
#
#     # Skills
#     logger.info("[EXTRACTION] Extracting skills...")
#     if "skills" in responses:
#         skills_text = responses["skills"]
#         if isinstance(skills_text, str):
#             # Split by common delimiters
#             skills = [s.strip() for s in skills_text.split(',')]
#             result["skills"] = [s for s in skills if len(s) > 2][:5]
#             logger.info(f"[EXTRACTION]   ✓ Skills extracted: {len(result['skills'])} items - {result['skills']}")
#
#     # Tools
#     logger.info("[EXTRACTION] Extracting tools...")
#     if "tools" in responses:
#         tools_text = responses["tools"]
#         if isinstance(tools_text, str):
#             # Split by common delimiters
#             tools = [t.strip() for t in tools_text.split(',')]
#             result["tools"] = [t for t in tools if len(t) > 2][:5]
#             logger.info(f"[EXTRACTION]   ✓ Tools extracted: {len(result['tools'])} items - {result['tools']}")
#
#     # Preferred location - clean location name
#     logger.info("[EXTRACTION] Extracting preferred_location...")
#     if "preferred_location" in responses:
#         loc_text = responses["preferred_location"]
#         if isinstance(loc_text, str):
#             # Rule-based location cleaning (fallback)
#             cleaned_location = clean_location_name(loc_text)
#             result["preferred_location"] = cleaned_location
#             logger.info(f"[EXTRACTION]   ✓ Location: {cleaned_location}")
#
#     # Try OpenAI for better structuring if available
#     if openai_client:
#         logger.info("[EXTRACTION] Attempting OpenAI-based structuring...")
#         openai_result = structure_with_openai(responses)
#         if openai_result:
#             logger.info("[EXTRACTION]   ✓ OpenAI structuring succeeded")
#             logger.info(f"[EXTRACTION]   Result: {openai_result}")
#             return openai_result
#         else:
#             logger.info("[EXTRACTION]   ⚠ OpenAI structuring returned None, using fallback")
#
#     # Fallback to rule-based if LLM not available
#     logger.info("[EXTRACTION] Using rule-based extraction (fallback)")
#     logger.info(f"[EXTRACTION] Final result:")
#     logger.info(f"[EXTRACTION]   - primary_skill: {result['primary_skill']}")
#     logger.info(f"[EXTRACTION]   - experience_years: {result['experience_years']}")
#     logger.info(f"[EXTRACTION]   - skills: {result['skills']}")
#     logger.info(f"[EXTRACTION]   - tools: {result['tools']}")
#     logger.info(f"[EXTRACTION]   - preferred_location: {result['preferred_location']}")
#
#     return result
#     if "tools" in responses:
#         tools_text = responses["tools"]
#         if isinstance(tools_text, str):
#             # Split by common delimiters
#             tools = [t.strip() for t in tools_text.split(',')]
#             result["tools"] = [t for t in tools if len(t) > 2][:5]
#
#     # Preferred location - clean location name
#     if "preferred_location" in responses:
#         loc_text = responses["preferred_location"]
#         if isinstance(loc_text, str):
#             # Rule-based location cleaning (fallback)
#             cleaned_location = clean_location_name(loc_text)
#             result["preferred_location"] = cleaned_location
#
#     # Try OpenAI for better structuring if available
#     if openai_client:
#         openai_result = structure_with_openai(responses)
#         if openai_result:
#             return openai_result
#
#     # Fallback to rule-based if LLM not available
#     return result
#
#
# def clean_location_name(location_text: str) -> str:
#     """
#     Clean location name - extract only city name from raw text.
#     Removes common Hindi/Hinglish words and phrases.
#     """
#     if not location_text:
#         return ""
#
#     text_lower = location_text.lower().strip()
#
#     # Common Indian cities (check for these first)
#     cities = [
#         "delhi", "mumbai", "bangalore", "bengaluru", "hyderabad", "pune",
#         "kolkata", "chennai", "ahmedabad", "indore", "nagpur", "jaipur",
#         "lucknow", "kanpur", "patna", "bhopal", "visakhapatnam", "vadodara",
#         "noida", "gurgaon", "gurugram", "faridabad", "ghaziabad", "greater noida",
#         "thane", "navi mumbai", "howrah", "pimpri-chinchwad", "allahabad", "meerut"
#     ]
#
#     # Check if any city name is in the text
#     for city in cities:
#         if city in text_lower:
#             # Return city name in proper case
#             return city.title()
#
#     # If no city found, try to extract first meaningful word
#     # Remove common Hindi/Hinglish words
#     words_to_remove = [
#         "me", "mein", "ke", "pass", "mujhe", "karna", "chahta", "hai", "hu", "hain",
#         "aur", "kab", "se", "kaam", "shuru", "kar", "sakte", "hain", "area", "mien"
#     ]
#
#     words = text_lower.split()
#     cleaned_words = [w for w in words if w not in words_to_remove and len(w) > 2]
#
#     if cleaned_words:
#         # Return first meaningful word in proper case
#         return cleaned_words[0].title()
#
#     # Fallback: return original text stripped
#     return location_text.strip()
#
#
# def get_llm_structuring_prompt(responses: dict) -> str:
#     """Generate LLM prompt for experience structuring"""
#     responses_str = json.dumps(responses, indent=2)
#     return STRUCTURING_PROMPT.format(responses=responses_str)
#
#
# def structure_with_openai(responses: dict) -> Optional[dict]:
#     """Structure experience data using OpenAI API - Returns clean structured JSON"""
#     try:
#         logger.info("[LLM_STRUCT] Starting OpenAI structuring...")
#
#         if not openai_client or not os.getenv("OPENAI_API_KEY"):
#             logger.warning("[LLM_STRUCT] OpenAI client not available or API key missing")
#             return None
#
#         prompt = get_llm_structuring_prompt(responses)
#         logger.info(f"[LLM_STRUCT] LLM model: {os.getenv('LLM_MODEL', 'gpt-4o-mini')}")
#         logger.info(f"[LLM_STRUCT] Prompt length: {len(prompt)} chars")
#
#         # Try with JSON mode first (for supported models)
#         try:
#             logger.info("[LLM_STRUCT] Attempting with JSON mode...")
#             response = openai_client.chat.completions.create(
#                 model=os.getenv("LLM_MODEL", "gpt-4o-mini"),  # Cost-effective and accurate
#                 messages=[
#                     {"role": "system",
#                      "content": "You are a professional data extraction expert. Extract and structure work experience data for blue-collar workers. Always return valid JSON only, no markdown, no code blocks."},
#                     {"role": "user", "content": prompt}
#                 ],
#                 temperature=0.1,
#                 max_tokens=500,
#                 response_format={"type": "json_object"}
#             )
#             logger.info("[LLM_STRUCT] ✓ JSON mode request succeeded")
#         except Exception as e:
#             # Fallback for models that don't support JSON mode
#             logger.warning(f"[LLM_STRUCT] JSON mode not supported, falling back: {str(e)}")
#             response = openai_client.chat.completions.create(
#                 model=os.getenv("LLM_MODEL", "gpt-4o-mini"),  # Cost-effective and accurate
#                 messages=[
#                     {"role": "system",
#                      "content": "You are a professional data extraction expert. Extract and structure work experience data for blue-collar workers. Always return valid JSON only, no markdown, no code blocks."},
#                     {"role": "user", "content": prompt}
#                 ],
#                 temperature=0.1,
#                 max_tokens=500
#             )
#             logger.info("[LLM_STRUCT] ✓ Standard mode request succeeded")
#
#         response_text = response.choices[0].message.content
#         logger.info(f"[LLM_STRUCT] LLM response length: {len(response_text)} chars")
#
#         # Try to parse as JSON directly
#         try:
#             logger.info("[LLM_STRUCT] Parsing LLM response as JSON...")
#             data = json.loads(response_text)
#             logger.info("[LLM_STRUCT] ✓ Direct JSON parsing succeeded")
#         except:
#             # Fallback: extract JSON from text
#             logger.info("[LLM_STRUCT] Direct parsing failed, extracting JSON from text...")
#             json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
#             if json_match:
#                 data = json.loads(json_match.group(0))
#                 logger.info("[LLM_STRUCT] ✓ Extracted JSON from text")
#             else:
#                 logger.error("[LLM_STRUCT] ✗ No JSON found in response")
#                 return None
#
#         # Map to our expected format (backward compatible)
#         logger.info("[LLM_STRUCT] Mapping LLM output to expected format...")
#         structured = {
#             "job_title": data.get("job_title", ""),
#             "total_experience": data.get("total_experience", ""),
#             "skills": data.get("skills", []),
#             "tools": data.get("tools", []),
#             "preferred_location": data.get("preferred_location", ""),
#             "availability": data.get("availability", "Not specified")
#         }
#
#         logger.info(f"[LLM_STRUCT] Structured data:")
#         logger.info(f"[LLM_STRUCT]   - job_title: {structured['job_title']}")
#         logger.info(f"[LLM_STRUCT]   - total_experience: {structured['total_experience']}")
#         logger.info(f"[LLM_STRUCT]   - skills: {structured['skills']}")
#         logger.info(f"[LLM_STRUCT]   - tools: {structured['tools']}")
#         logger.info(f"[LLM_STRUCT]   - location: {structured['preferred_location']}")
#
#         # Also maintain backward compatibility fields
#         if structured["job_title"]:
#             structured["primary_skill"] = structured["job_title"]
#         if structured["total_experience"]:
#             # Extract years from "X years" format
#             years_match = re.search(r'(\d+)', structured["total_experience"])
#             if years_match:
#                 structured["experience_years"] = int(years_match.group(1))
#                 logger.info(f"[LLM_STRUCT]   - experience_years: {structured['experience_years']}")
#
#         # Combine skills and tools for backward compatibility
#         all_skills = structured.get("skills", []) + structured.get("tools", [])
#         structured["skills_combined"] = all_skills
#
#         logger.info(f"[LLM_STRUCT] ✓ OpenAI structuring completed successfully")
#         return structured
#     except Exception as e:
#         logger.error(f"[LLM_STRUCT] ✗ OpenAI structuring error: {str(e)}", exc_info=True)
#
#     return None
#
#
# def validate_extracted_experience(data: dict) -> bool:
#     """Validate extracted experience data"""
#     # At least primary skill or experience years should be present
#     return (
#             (data.get("primary_skill") and len(str(data.get("primary_skill", "")).strip()) > 0) or
#             (data.get("experience_years", 0) > 0) or
#             (data.get("skills") and len(data.get("skills", [])) > 0)
#     )
#
#
# # NEW: System prompt-based extraction for comprehensive data collection
# SYSTEM_PROMPT_EXTRACTION_PROMPT = """You are a data extraction expert for blue-collar and grey-collar workers.
# Extract ALL information from the voice call transcript following the system prompt structure.
#
# The transcript follows this question flow:
# 1. Type of Work (primary_skill)
# 2. Previous Workplace(s) - may have multiple workplaces
# 3. Work Location(s) - corresponding to each workplace
# 4. Work Duration(s) - corresponding to each workplace
# 5. Total Experience Duration
# 6. Skills/Tasks
# 7. Tools/Machines
# 8. Current Location (where worker currently lives)
# 9. Job Location Preference (where worker wants to work)
# 10. Availability/Timing
#
# RULES:
# 1. Translate all values to clean English.
# 2. Extract ALL workplaces with their corresponding locations and durations.
# 3. primary_skill: job title/role (e.g. House Help, Electrician, Painter).
# 4. experience_years: total years as integer (from Question 5).
# 5. skills: list of skills/tasks from Question 6.
# 6. tools: list of tools/machines from Question 7.
# 7. current_location: city where worker currently lives (from Question 8, first part).
# 8. preferred_location: city where worker wants to work (from Question 8, second part).
# 9. availability: when worker can start (from Question 9).
# 10. workplaces: array of objects, each with workplace_name, work_location, work_duration.
# 11. Return ONLY valid JSON, no extra text.
#
# Transcript:
# {transcript}
#
# Return JSON in this exact format:
# {{
#     "primary_skill": "Job title in English",
#     "experience_years": 0,
#     "skills": ["skill1", "skill2"],
#     "tools": ["tool1", "tool2"],
#     "current_location": "City where worker currently lives",
#     "preferred_location": "City where worker wants to work",
#     "availability": "Immediate" or "Available from date" or "Not specified",
#     "workplaces": [
#         {{
#             "workplace_name": "Name or type of workplace",
#             "work_location": "City/area where work was done",
#             "work_duration": "Duration (e.g., 6 months, 1 year, 2 years)"
#         }}
#     ]
# }}"""
#
# # OLD: Simple extraction prompt (kept for backward compatibility)
# TRANSCRIPT_EXTRACTION_PROMPT = """You are a data extraction expert for blue-collar and grey-collar workers.
# From the following voice call transcript (may be in Hindi, Hinglish, or English), extract structured work experience.
#
# RULES:
# 1. Translate all values to clean English.
# 2. primary_skill: job title/role (e.g. House Help, Electrician, Painter).
# 3. experience_years: total years as integer.
# 4. skills: list of skills/tasks (e.g. vacuuming, cleaning, cooking).
# 5. tools: list of tools, machines, or equipment (e.g. tester, drill machine, spanner, welding machine, vacuum cleaner, pressure cooker).
# 6. preferred_location: city/area only (e.g. Delhi, Mayur Vihar, NCR).
# 7. Return ONLY valid JSON, no extra text.
#
# Transcript:
# {transcript}
#
# Return JSON in this exact format:
# {{
#     "primary_skill": "Job title in English",
#     "experience_years": 0,
#     "skills": ["skill1", "skill2"],
#     "tools": ["tool1", "tool2"],
#     "preferred_location": "City or area name"
# }}"""
#
#
# def extract_from_transcript_comprehensive(transcript: str) -> dict:
#     """
#     NEW: Extract comprehensive structured experience from full voice call transcript using system prompt.
#     Extracts all details including multiple workplaces, current location, preferred location, availability.
#     Uses LLM when OPENAI_API_KEY is set; otherwise rule-based fallback.
#     Returns dict with all fields including workplaces array.
#     """
#     if not transcript or len(transcript.strip()) < 10:
#         return {
#             "primary_skill": "",
#             "experience_years": 0,
#             "skills": [],
#             "tools": [],
#             "current_location": "",
#             "preferred_location": "",
#             "availability": "Not specified",
#             "workplaces": []
#         }
#
#     result = {
#         "primary_skill": "",
#         "experience_years": 0,
#         "skills": [],
#         "tools": [],
#         "current_location": "",
#         "preferred_location": "",
#         "availability": "Not specified",
#         "workplaces": []
#     }
#
#     # Rule-based fallback: try to get numbers for years
#     numbers = re.findall(r"\d+", transcript)
#     if numbers:
#         result["experience_years"] = min(int(numbers[0]), 50)
#
#     # Try OpenAI for comprehensive extraction
#     try:
#         if openai_client and os.getenv("OPENAI_API_KEY"):
#             prompt = SYSTEM_PROMPT_EXTRACTION_PROMPT.format(
#                 transcript=transcript.strip()[:6000])  # Increased limit for comprehensive data
#             # Try with JSON mode first (for supported models)
#             try:
#                 response = openai_client.chat.completions.create(
#                     model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
#                     messages=[
#                         {"role": "system",
#                          "content": "Extract comprehensive work experience from transcript following system prompt structure. Return only valid JSON."},
#                         {"role": "user", "content": prompt}
#                     ],
#                     temperature=0.1,
#                     max_tokens=1500,  # Increased for multiple workplaces
#                     response_format={"type": "json_object"}
#                 )
#             except Exception:
#                 # Fallback for models that don't support JSON mode
#                 response = openai_client.chat.completions.create(
#                     model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
#                     messages=[
#                         {"role": "system",
#                          "content": "Extract comprehensive work experience from transcript following system prompt structure. Return only valid JSON."},
#                         {"role": "user", "content": prompt}
#                     ],
#                     temperature=0.1,
#                     max_tokens=1500
#                 )
#             text = response.choices[0].message.content.strip()
#             json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
#             if json_match:
#                 data = json.loads(json_match.group(0))
#                 result["primary_skill"] = (data.get("primary_skill") or "").strip()
#                 result["experience_years"] = int(data.get("experience_years") or 0)
#                 result["skills"] = data.get("skills") or []
#                 if isinstance(result["skills"], str):
#                     result["skills"] = [s.strip() for s in result["skills"].split(",") if s.strip()]
#                 result["tools"] = data.get("tools") or []
#                 if isinstance(result["tools"], str):
#                     result["tools"] = [t.strip() for t in result["tools"].split(",") if t.strip()]
#                 result["current_location"] = (data.get("current_location") or "").strip()
#                 result["preferred_location"] = (data.get("preferred_location") or "").strip()
#                 result["availability"] = (data.get("availability") or "Not specified").strip()
#                 result["workplaces"] = data.get("workplaces") or []
#                 # Ensure workplaces is a list
#                 if not isinstance(result["workplaces"], list):
#                     result["workplaces"] = []
#                 logger.info(f"✓ Comprehensive extraction successful: {len(result['workplaces'])} workplaces found")
#                 return result
#     except Exception as e:
#         logger.warning(f"Comprehensive transcript extraction error: {e}")
#
#     # Fallback to old extraction if comprehensive fails
#     logger.warning("Comprehensive extraction failed, falling back to simple extraction")
#     return extract_from_transcript(transcript)
#
#
# def extract_from_transcript(transcript: str) -> dict:
#     """
#     OLD: Extract structured experience from full voice call transcript (backward compatibility).
#     Uses LLM when OPENAI_API_KEY is set; otherwise rule-based fallback.
#     Returns dict with primary_skill, experience_years, skills, tools, preferred_location for save_experience.
#     """
#     if not transcript or len(transcript.strip()) < 10:
#         return {"primary_skill": "", "experience_years": 0, "skills": [], "tools": [], "preferred_location": ""}
#     result = {"primary_skill": "", "experience_years": 0, "skills": [], "tools": [], "preferred_location": ""}
#     # Rule-based: try to get numbers for years
#     numbers = re.findall(r"\d+", transcript)
#     if numbers:
#         result["experience_years"] = min(int(numbers[0]), 50)
#     # Try OpenAI for full extraction
#     try:
#         if openai_client and os.getenv("OPENAI_API_KEY"):
#             prompt = TRANSCRIPT_EXTRACTION_PROMPT.format(transcript=transcript.strip()[:4000])
#             # Try with JSON mode first (for supported models)
#             try:
#                 response = openai_client.chat.completions.create(
#                     model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
#                     messages=[
#                         {"role": "system",
#                          "content": "Extract work experience from transcript. Return only valid JSON."},
#                         {"role": "user", "content": prompt}
#                     ],
#                     temperature=0.1,
#                     max_tokens=500,
#                     response_format={"type": "json_object"}
#                 )
#             except Exception:
#                 # Fallback for models that don't support JSON mode
#                 response = openai_client.chat.completions.create(
#                     model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
#                     messages=[
#                         {"role": "system",
#                          "content": "Extract work experience from transcript. Return only valid JSON."},
#                         {"role": "user", "content": prompt}
#                     ],
#                     temperature=0.1,
#                     max_tokens=500
#                 )
#             text = response.choices[0].message.content.strip()
#             json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
#             if json_match:
#                 data = json.loads(json_match.group(0))
#                 result["primary_skill"] = (data.get("primary_skill") or "").strip()
#                 result["experience_years"] = int(data.get("experience_years") or 0)
#                 result["skills"] = data.get("skills") or []
#                 if isinstance(result["skills"], str):
#                     result["skills"] = [s.strip() for s in result["skills"].split(",") if s.strip()]
#                 result["tools"] = data.get("tools") or []
#                 if isinstance(result["tools"], str):
#                     result["tools"] = [t.strip() for t in result["tools"].split(",") if t.strip()]
#                 result["preferred_location"] = (data.get("preferred_location") or "").strip()
#                 return result
#     except Exception as e:
#         logger.warning(f"Transcript extraction error: {e}")
#     return result

import json
import os
import re
from typing import Optional
from openai import OpenAI

"""
Experience Extractor - Structure raw responses into JSON
Uses LLM only for final structuring (not conversation control)
"""
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Initialize OpenAI client (lazy / safe if key missing)
openai_client = None
try:
    if os.getenv("OPENAI_API_KEY"):
        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception as e:
    logger.warning(f"OpenAI client not initialized for experience extractor: {e}")

STRUCTURING_PROMPT = """You are a data extraction expert for blue-collar and grey-collar workers.
Extract and structure work experience information from raw responses in Hindi, Hinglish, or English.

IMPORTANT RULES:
1. Translate all values to clean English
2. Extract job title/profession from primary_skill (e.g., "mai electrician ka" → "Electrician")
3. Extract years of experience as integer
4. Separate skills and tools into distinct arrays
5. **LOCATION EXTRACTION (CRITICAL)**: Extract ONLY the city/location name. Remove ALL extra words.
   - Examples: "delhi me mujhe karna hai" → "Delhi"
   - "noida ke pass mai kaam karna chahta hu" → "Noida"
   - "mumbai mein" → "Mumbai"
   - Remove words like: "me", "mein", "ke pass", "mujhe", "karna", "chahta", "hai", "hu", etc.
   - Return ONLY the city name in proper case (e.g., "Delhi", "Noida", "Mumbai")
6. Extract availability if mentioned
7. Return ONLY valid JSON, no additional text

Raw responses:
{responses}

Return JSON in this exact format:
{{
    "job_title": "Clean job title in English",
    "total_experience": "X years",
    "skills": ["skill1", "skill2", "skill3"],
    "tools": ["tool1", "tool2"],
    "preferred_location": "City name only (e.g., Delhi, Noida, Mumbai)",
    "availability": "Immediate" or "Available from date" or "Not specified"
}}"""


def extract_from_responses(responses: dict) -> dict:
    """
    Extract structured experience data from collected responses.
    Uses rule-based parsing first, then OpenAI for complex cases.

    responses: {
        "primary_skill": "raw response",
        "experience_years": "raw response",
        "skills": "raw response",
        "preferred_location": "raw response"
    }
    """
    logger.info("[EXTRACTION] Starting extract_from_responses()")
    logger.info(f"[EXTRACTION] Input fields: {list(responses.keys())}")

    result = {
        "primary_skill": "",
        "experience_years": 0,
        "skills": [],
        "tools": [],
        "preferred_location": ""
    }

    # Primary skill
    logger.info("[EXTRACTION] Extracting primary_skill...")
    if "primary_skill" in responses:
        skill_text = responses["primary_skill"]
        if isinstance(skill_text, str) and len(skill_text) > 0:
            # Extract first meaningful phrase
            words = skill_text.split()
            result["primary_skill"] = " ".join(words[:3]).strip()
            logger.info(f"[EXTRACTION]   ✓ Primary skill: {result['primary_skill']}")

    # Experience years
    logger.info("[EXTRACTION] Extracting experience_years...")
    if "experience_years" in responses:
        exp_text = responses["experience_years"]
        try:
            # Try to extract number
            numbers = re.findall(r'\d+', str(exp_text))
            if numbers:
                result["experience_years"] = int(numbers[0])
                logger.info(f"[EXTRACTION]   ✓ Years of experience: {result['experience_years']}")
        except:
            logger.warning(f"[EXTRACTION]   ⚠ Failed to parse experience_years: {exp_text}")
            pass

    # Skills
    logger.info("[EXTRACTION] Extracting skills...")
    if "skills" in responses:
        skills_text = responses["skills"]
        if isinstance(skills_text, str):
            # Split by common delimiters
            skills = [s.strip() for s in skills_text.split(',')]
            result["skills"] = [s for s in skills if len(s) > 2][:5]
            logger.info(f"[EXTRACTION]   ✓ Skills extracted: {len(result['skills'])} items - {result['skills']}")

    # Tools
    logger.info("[EXTRACTION] Extracting tools...")
    if "tools" in responses:
        tools_text = responses["tools"]
        if isinstance(tools_text, str):
            # Split by common delimiters
            tools = [t.strip() for t in tools_text.split(',')]
            result["tools"] = [t for t in tools if len(t) > 2][:5]
            logger.info(f"[EXTRACTION]   ✓ Tools extracted: {len(result['tools'])} items - {result['tools']}")

    # Preferred location - clean location name
    logger.info("[EXTRACTION] Extracting preferred_location...")
    if "preferred_location" in responses:
        loc_text = responses["preferred_location"]
        if isinstance(loc_text, str):
            # Rule-based location cleaning (fallback)
            cleaned_location = clean_location_name(loc_text)
            result["preferred_location"] = cleaned_location
            logger.info(f"[EXTRACTION]   ✓ Location: {cleaned_location}")

    # Try OpenAI for better structuring if available
    if openai_client:
        logger.info("[EXTRACTION] Attempting OpenAI-based structuring...")
        openai_result = structure_with_openai(responses)
        if openai_result:
            logger.info("[EXTRACTION]   ✓ OpenAI structuring succeeded")
            logger.info(f"[EXTRACTION]   Result: {openai_result}")
            return openai_result
        else:
            logger.info("[EXTRACTION]   ⚠ OpenAI structuring returned None, using fallback")

    # Fallback to rule-based if LLM not available
    logger.info("[EXTRACTION] Using rule-based extraction (fallback)")
    logger.info(f"[EXTRACTION] Final result:")
    logger.info(f"[EXTRACTION]   - primary_skill: {result['primary_skill']}")
    logger.info(f"[EXTRACTION]   - experience_years: {result['experience_years']}")
    logger.info(f"[EXTRACTION]   - skills: {result['skills']}")
    logger.info(f"[EXTRACTION]   - tools: {result['tools']}")
    logger.info(f"[EXTRACTION]   - preferred_location: {result['preferred_location']}")

    return result
    if "tools" in responses:
        tools_text = responses["tools"]
        if isinstance(tools_text, str):
            # Split by common delimiters
            tools = [t.strip() for t in tools_text.split(',')]
            result["tools"] = [t for t in tools if len(t) > 2][:5]

    # Preferred location - clean location name
    if "preferred_location" in responses:
        loc_text = responses["preferred_location"]
        if isinstance(loc_text, str):
            # Rule-based location cleaning (fallback)
            cleaned_location = clean_location_name(loc_text)
            result["preferred_location"] = cleaned_location

    # Try OpenAI for better structuring if available
    if openai_client:
        openai_result = structure_with_openai(responses)
        if openai_result:
            return openai_result

    # Fallback to rule-based if LLM not available
    return result


def clean_location_name(location_text: str) -> str:
    """
    Clean location name - extract only city name from raw text.
    Removes common Hindi/Hinglish words and phrases.
    """
    if not location_text:
        return ""

    text_lower = location_text.lower().strip()

    # Common Indian cities (check for these first)
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
            # Return city name in proper case
            return city.title()

    # If no city found, try to extract first meaningful word
    # Remove common Hindi/Hinglish words
    words_to_remove = [
        "me", "mein", "ke", "pass", "mujhe", "karna", "chahta", "hai", "hu", "hain",
        "aur", "kab", "se", "kaam", "shuru", "kar", "sakte", "hain", "area", "mien"
    ]

    words = text_lower.split()
    cleaned_words = [w for w in words if w not in words_to_remove and len(w) > 2]

    if cleaned_words:
        # Return first meaningful word in proper case
        return cleaned_words[0].title()

    # Fallback: return original text stripped
    return location_text.strip()


def get_llm_structuring_prompt(responses: dict) -> str:
    """Generate LLM prompt for experience structuring"""
    responses_str = json.dumps(responses, indent=2)
    return STRUCTURING_PROMPT.format(responses=responses_str)


def structure_with_openai(responses: dict) -> Optional[dict]:
    """Structure experience data using OpenAI API - Returns clean structured JSON"""
    try:
        logger.info("[LLM_STRUCT] Starting OpenAI structuring...")

        if not openai_client or not os.getenv("OPENAI_API_KEY"):
            logger.warning("[LLM_STRUCT] OpenAI client not available or API key missing")
            return None

        prompt = get_llm_structuring_prompt(responses)
        logger.info(f"[LLM_STRUCT] LLM model: {os.getenv('LLM_MODEL', 'gpt-4o-mini')}")
        logger.info(f"[LLM_STRUCT] Prompt length: {len(prompt)} chars")

        # Try with JSON mode first (for supported models)
        try:
            logger.info("[LLM_STRUCT] Attempting with JSON mode...")
            response = openai_client.chat.completions.create(
                model=os.getenv("LLM_MODEL", "gpt-4o-mini"),  # Cost-effective and accurate
                messages=[
                    {"role": "system",
                     "content": "You are a professional data extraction expert. Extract and structure work experience data for blue-collar workers. Always return valid JSON only, no markdown, no code blocks."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500,
                response_format={"type": "json_object"}
            )
            logger.info("[LLM_STRUCT] ✓ JSON mode request succeeded")
        except Exception as e:
            # Fallback for models that don't support JSON mode
            logger.warning(f"[LLM_STRUCT] JSON mode not supported, falling back: {str(e)}")
            response = openai_client.chat.completions.create(
                model=os.getenv("LLM_MODEL", "gpt-4o-mini"),  # Cost-effective and accurate
                messages=[
                    {"role": "system",
                     "content": "You are a professional data extraction expert. Extract and structure work experience data for blue-collar workers. Always return valid JSON only, no markdown, no code blocks."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500
            )
            logger.info("[LLM_STRUCT] ✓ Standard mode request succeeded")

        response_text = response.choices[0].message.content
        logger.info(f"[LLM_STRUCT] LLM response length: {len(response_text)} chars")

        # Try to parse as JSON directly
        try:
            logger.info("[LLM_STRUCT] Parsing LLM response as JSON...")
            data = json.loads(response_text)
            logger.info("[LLM_STRUCT] ✓ Direct JSON parsing succeeded")
        except:
            # Fallback: extract JSON from text
            logger.info("[LLM_STRUCT] Direct parsing failed, extracting JSON from text...")
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                logger.info("[LLM_STRUCT] ✓ Extracted JSON from text")
            else:
                logger.error("[LLM_STRUCT] ✗ No JSON found in response")
                return None

        # Map to our expected format (backward compatible)
        logger.info("[LLM_STRUCT] Mapping LLM output to expected format...")
        structured = {
            "job_title": data.get("job_title", ""),
            "total_experience": data.get("total_experience", ""),
            "skills": data.get("skills", []),
            "tools": data.get("tools", []),
            "preferred_location": data.get("preferred_location", ""),
            "availability": data.get("availability", "Not specified")
        }

        logger.info(f"[LLM_STRUCT] Structured data:")
        logger.info(f"[LLM_STRUCT]   - job_title: {structured['job_title']}")
        logger.info(f"[LLM_STRUCT]   - total_experience: {structured['total_experience']}")
        logger.info(f"[LLM_STRUCT]   - skills: {structured['skills']}")
        logger.info(f"[LLM_STRUCT]   - tools: {structured['tools']}")
        logger.info(f"[LLM_STRUCT]   - location: {structured['preferred_location']}")

        # Also maintain backward compatibility fields
        if structured["job_title"]:
            structured["primary_skill"] = structured["job_title"]
        if structured["total_experience"]:
            # Extract years from "X years" format
            years_match = re.search(r'(\d+)', structured["total_experience"])
            if years_match:
                structured["experience_years"] = int(years_match.group(1))
                logger.info(f"[LLM_STRUCT]   - experience_years: {structured['experience_years']}")

        # Combine skills and tools for backward compatibility
        all_skills = structured.get("skills", []) + structured.get("tools", [])
        structured["skills_combined"] = all_skills

        logger.info(f"[LLM_STRUCT] ✓ OpenAI structuring completed successfully")
        return structured
    except Exception as e:
        logger.error(f"[LLM_STRUCT] ✗ OpenAI structuring error: {str(e)}", exc_info=True)

    return None


def validate_extracted_experience(data: dict) -> bool:
    """Validate extracted experience data"""
    # At least primary skill or experience years should be present
    return (
            (data.get("primary_skill") and len(str(data.get("primary_skill", "")).strip()) > 0) or
            (data.get("experience_years", 0) > 0) or
            (data.get("skills") and len(data.get("skills", [])) > 0)
    )


# NEW: System prompt-based extraction for comprehensive data collection
SYSTEM_PROMPT_EXTRACTION_PROMPT = """You are a data extraction expert for blue-collar and grey-collar workers.
Extract ALL information from the voice call transcript following the system prompt structure.

The transcript follows this question flow:
1. Type of Work (primary_skill)
2. Previous Workplace(s) - may have multiple workplaces
3. Work Location(s) - corresponding to each workplace
4. Work Duration(s) - corresponding to each workplace
5. Total Experience Duration
6. Skills/Tasks
7. Tools/Machines
8. Current Location (where worker currently lives)
9. Job Location Preference (where worker wants to work)
10. Availability/Timing

RULES:
1. Translate all values to clean English.
2. Extract ALL workplaces with their corresponding locations and durations.
3. primary_skill: job title/role (e.g. House Help, Electrician, Painter).
4. experience_years: total years as integer (from Question 5).
5. skills: list of skills/tasks from Question 6.
6. tools: list of tools/machines from Question 7.
7. current_location: city where worker currently lives (from Question 8, first part).
8. preferred_location: city where worker wants to work (from Question 8, second part).
9. availability: when worker can start (from Question 9).
10. workplaces: array of objects, each with workplace_name, work_location, work_duration.
11. Return ONLY valid JSON, no extra text.

Transcript:
{transcript}

Return JSON in this exact format:
{{
    "primary_skill": "Job title in English",
    "experience_years": 0,
    "skills": ["skill1", "skill2"],
    "tools": ["tool1", "tool2"],
    "current_location": "City where worker currently lives",
    "preferred_location": "City where worker wants to work",
    "availability": "Immediate" or "Available from date" or "Not specified",
    "workplaces": [
        {{
            "workplace_name": "Name or type of workplace",
            "work_location": "City/area where work was done",
            "work_duration": "Duration (e.g., 6 months, 1 year, 2 years)"
        }}
    ]
}}"""

# OLD: Simple extraction prompt (kept for backward compatibility)
TRANSCRIPT_EXTRACTION_PROMPT = """You are a data extraction expert for blue-collar and grey-collar workers.
From the following voice call transcript (may be in Hindi, Hinglish, or English), extract structured work experience.

RULES:
1. Translate all values to clean English.
2. primary_skill: job title/role (e.g. House Help, Electrician, Painter).
3. experience_years: total years as integer.
4. skills: list of skills/tasks (e.g. vacuuming, cleaning, cooking).
5. tools: list of tools, machines, or equipment (e.g. tester, drill machine, spanner, welding machine, vacuum cleaner, pressure cooker).
6. preferred_location: city/area only (e.g. Delhi, Mayur Vihar, NCR).
7. Return ONLY valid JSON, no extra text.

Transcript:
{transcript}

Return JSON in this exact format:
{{
    "primary_skill": "Job title in English",
    "experience_years": 0,
    "skills": ["skill1", "skill2"],
    "tools": ["tool1", "tool2"],
    "preferred_location": "City or area name"
}}"""


def extract_from_transcript_comprehensive(transcript: str) -> dict:
    """
    NEW: Extract comprehensive structured experience from full voice call transcript using system prompt.
    Extracts all details including multiple workplaces, current location, preferred location, availability.
    Uses LLM when OPENAI_API_KEY is set; otherwise rule-based fallback.
    Returns dict with all fields including workplaces array.
    """
    if not transcript or len(transcript.strip()) < 10:
        return {
            "primary_skill": "",
            "experience_years": 0,
            "skills": [],
            "tools": [],
            "current_location": "",
            "preferred_location": "",
            "availability": "Not specified",
            "workplaces": []
        }

    result = {
        "primary_skill": "",
        "experience_years": 0,
        "skills": [],
        "tools": [],
        "current_location": "",
        "preferred_location": "",
        "availability": "Not specified",
        "workplaces": []
    }

    # Rule-based fallback: try to get numbers for years
    numbers = re.findall(r"\d+", transcript)
    if numbers:
        result["experience_years"] = min(int(numbers[0]), 50)

    # Try OpenAI for comprehensive extraction
    try:
        if openai_client and os.getenv("OPENAI_API_KEY"):
            prompt = SYSTEM_PROMPT_EXTRACTION_PROMPT.format(
                transcript=transcript.strip()[:6000])  # Increased limit for comprehensive data
            # Try with JSON mode first (for supported models)
            try:
                response = openai_client.chat.completions.create(
                    model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
                    messages=[
                        {"role": "system",
                         "content": "Extract comprehensive work experience from transcript following system prompt structure. Return only valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=1500,  # Increased for multiple workplaces
                    response_format={"type": "json_object"}
                )
            except Exception:
                # Fallback for models that don't support JSON mode
                response = openai_client.chat.completions.create(
                    model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
                    messages=[
                        {"role": "system",
                         "content": "Extract comprehensive work experience from transcript following system prompt structure. Return only valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=1500
                )
            text = response.choices[0].message.content.strip()
            json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                result["primary_skill"] = (data.get("primary_skill") or "").strip()
                result["experience_years"] = int(data.get("experience_years") or 0)
                result["skills"] = data.get("skills") or []
                if isinstance(result["skills"], str):
                    result["skills"] = [s.strip() for s in result["skills"].split(",") if s.strip()]
                result["tools"] = data.get("tools") or []
                if isinstance(result["tools"], str):
                    result["tools"] = [t.strip() for t in result["tools"].split(",") if t.strip()]
                result["current_location"] = (data.get("current_location") or "").strip()
                result["preferred_location"] = (data.get("preferred_location") or "").strip()
                result["availability"] = (data.get("availability") or "Not specified").strip()
                result["workplaces"] = data.get("workplaces") or []
                # Ensure workplaces is a list
                if not isinstance(result["workplaces"], list):
                    result["workplaces"] = []
                logger.info(f"✓ Comprehensive extraction successful: {len(result['workplaces'])} workplaces found")
                return result
    except Exception as e:
        logger.warning(f"Comprehensive transcript extraction error: {e}")

    # Fallback to old extraction if comprehensive fails
    logger.warning("Comprehensive extraction failed, falling back to simple extraction")
    return extract_from_transcript(transcript)


def extract_from_transcript(transcript: str) -> dict:
    """
    OLD: Extract structured experience from full voice call transcript (backward compatibility).
    Uses LLM when OPENAI_API_KEY is set; otherwise rule-based fallback.
    Returns dict with primary_skill, experience_years, skills, tools, preferred_location for save_experience.
    """
    if not transcript or len(transcript.strip()) < 10:
        return {"primary_skill": "", "experience_years": 0, "skills": [], "tools": [], "preferred_location": ""}
    result = {"primary_skill": "", "experience_years": 0, "skills": [], "tools": [], "preferred_location": ""}
    # Rule-based: try to get numbers for years
    numbers = re.findall(r"\d+", transcript)
    if numbers:
        result["experience_years"] = min(int(numbers[0]), 50)
    # Try OpenAI for full extraction
    try:
        if openai_client and os.getenv("OPENAI_API_KEY"):
            prompt = TRANSCRIPT_EXTRACTION_PROMPT.format(transcript=transcript.strip()[:4000])
            # Try with JSON mode first (for supported models)
            try:
                response = openai_client.chat.completions.create(
                    model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
                    messages=[
                        {"role": "system",
                         "content": "Extract work experience from transcript. Return only valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=500,
                    response_format={"type": "json_object"}
                )
            except Exception:
                # Fallback for models that don't support JSON mode
                response = openai_client.chat.completions.create(
                    model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
                    messages=[
                        {"role": "system",
                         "content": "Extract work experience from transcript. Return only valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=500
                )
            text = response.choices[0].message.content.strip()
            json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                result["primary_skill"] = (data.get("primary_skill") or "").strip()
                result["experience_years"] = int(data.get("experience_years") or 0)
                result["skills"] = data.get("skills") or []
                if isinstance(result["skills"], str):
                    result["skills"] = [s.strip() for s in result["skills"].split(",") if s.strip()]
                result["tools"] = data.get("tools") or []
                if isinstance(result["tools"], str):
                    result["tools"] = [t.strip() for t in result["tools"].split(",") if t.strip()]
                result["preferred_location"] = (data.get("preferred_location") or "").strip()
                return result
    except Exception as e:
        logger.warning(f"Transcript extraction error: {e}")
    return result
