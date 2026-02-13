"""
Conversation Engine - Backend controls all conversation flow
AI does NOT ask questions - it only extracts structured data
"""

from typing import Tuple

# RAW OCR AND VOICE TEXT ARE DISCARDED
# Backend controls all logic

CONVERSATION_STEPS = {
    0: "primary_skill",
    1: "experience_years",
    2: "skills",
    3: "preferred_location"
}

STEP_NAMES = {
    0: "Primary Skill",
    1: "Experience Years",
    2: "Skills",
    3: "Preferred Location"
}

def get_next_step(current_step: int) -> int:
    """Get next step in conversation"""
    return min(current_step + 1, 4)

def is_conversation_complete(current_step: int) -> bool:
    """Check if conversation is complete"""
    return current_step >= 4

def get_conversation_field(step: int) -> str:
    """Get the field being collected in this step"""
    return CONVERSATION_STEPS.get(step, "")

def get_step_description(step: int) -> str:
    """Get human-readable description of step"""
    return STEP_NAMES.get(step, "Unknown")

def parse_skill_response(speech_text: str) -> str:
    """
    Parse response for primary skill.
    Extract occupation/skill from speech.
    """
    # Simple extraction - in production, use LLM
    text_lower = speech_text.lower()
    
    skills_keywords = {
        "painter": "painter",
        "plumber": "plumber",
        "electrician": "electrician",
        "carpenter": "carpenter",
        "laborer": "laborer",
        "mason": "mason",
        "welder": "welder",
        "mechanic": "mechanic",
        "driver": "driver",
        "chef": "chef",
    }
    
    for keyword, skill in skills_keywords.items():
        if keyword in text_lower:
            return skill
    
    # Return first few words if no keyword match
    words = speech_text.split()
    return " ".join(words[:2]) if words else "unspecified"

def parse_experience_response(speech_text: str) -> int:
    """
    Parse response for experience years.
    Extract number from speech.
    """
    import re
    
    text_lower = speech_text.lower()
    
    # Common patterns
    patterns = {
        r'(\d+)\s*saal': 1,  # "5 saal"
        r'(\d+)\s*year': 1,
        r'(\d+)\s*sal': 1,
        r'(\d+)': 0,
    }
    
    for pattern, group_idx in patterns.items():
        match = re.search(pattern, text_lower)
        if match:
            try:
                return int(match.group(group_idx + 1))
            except (IndexError, ValueError):
                pass
    
    return 0

def parse_skills_response(speech_text: str) -> list:
    """
    Parse response for skills.
    Extract list of skills from speech.
    """
    text_lower = speech_text.lower()
    
    common_skills = [
        "painting", "electrical", "plumbing", "carpentry", "welding",
        "tiling", "masonry", "installation", "repair", "maintenance",
        "construction", "demolition", "cleaning", "finishing"
    ]
    
    found_skills = []
    for skill in common_skills:
        if skill in text_lower:
            found_skills.append(skill)
    
    # If no skills found, split response into chunks
    if not found_skills:
        words = speech_text.split(',')
        found_skills = [w.strip() for w in words if len(w.strip()) > 2]
    
    return found_skills[:5]  # Max 5 skills

def parse_location_response(speech_text: str) -> str:
    """
    Parse response for preferred location.
    Extract location from speech.
    """
    text_lower = speech_text.lower()
    
    # Common Indian cities/locations
    locations = [
        "delhi", "mumbai", "bangalore", "hyderabad", "pune",
        "delhi ncr", "gurgaon", "noida", "faridabad", "greater noida",
        "kolkata", "chennai", "ahmedabad", "indore", "nagpur"
    ]
    
    for loc in locations:
        if loc in text_lower:
            return loc.title()
    
    # Return raw text if no match
    return speech_text.strip()

def determine_next_step(current_step: int, response: str) -> Tuple[bool, int]:
    """
    Determine if response is valid and return next step.
    Returns (is_valid, next_step)
    """
    if not response or len(response) < 2:
        return False, current_step  # Ask again
    
    return True, get_next_step(current_step)
