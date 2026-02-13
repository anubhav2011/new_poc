"""
Language Renderer for Hinglish Voice Output
Deterministic English → Hinglish mapping
No AI usage - pure dictionary-based translation
"""

# Deterministic Hinglish mappings
ENGLISH_TO_HINGLISH = {
    # Questions
    "What kind of work do you do?": "Aap kis tarah ka kaam karte ho?",
    "How many years of experience do you have?": "Aapke paas kitne saal ka experience hai?",
    "What are your skills or tools you work with?": "Aapke paas kaun-kaun se skills ya tools hain?",
    "What is your preferred work location?": "Aap kaunse location par kaam karna pasand karte ho?",
    
    # Confirmations
    "Let me confirm, you said": "Main confirm karta hoon, aapne kaha tha",
    "Is that correct?": "Kya yeh sahi hai?",
    "Thank you for the information": "Aapki jankari ke liye shukriya",
    
    # Transitions
    "Moving to the next question": "Ab hum agale prashna par chalte hain",
    "Please wait while I process your information": "Kripaya intezaar karein jab main aapki jankari process karta hoon",
    
    # Keywords
    "experience": "anubhav",
    "skill": "maharat",
    "work": "kaam",
    "location": "sthan",
    "prefer": "pasand karte hain",
}

VOICE_OUTPUT_TEMPLATE = {
    0: "Namaste! Hum aapko welcome karte hain. Aap kis tarah ka kaam karte ho?",  # Initial greeting + Q1
    1: "Dhanyavaad! Aapke paas kitne saal ka experience hai?",  # Q2
    2: "Shukriya! Aapke paas kaun-kaun se skills hain?",  # Q3
    3: "Aur ab, aap kaunse location par kaam karna pasand karte ho?",  # Q4
    4: "Bahut badiya! Maine aapki saari jankari note kar li. Thank you for your time!"  # Completion
}

def translate_to_hinglish(english_text: str) -> str:
    """
    Translate English text to Hinglish using deterministic mapping.
    No AI - pure lookup and substitution.
    """
    # Direct mapping first
    if english_text in ENGLISH_TO_HINGLISH:
        return ENGLISH_TO_HINGLISH[english_text]
    
    # Word-by-word replacement for partial matches
    hinglish = english_text
    for eng, hindi in ENGLISH_TO_HINGLISH.items():
        if eng.lower() in english_text.lower():
            # Case-insensitive replacement
            hinglish = hinglish.replace(eng, hindi)
    
    return hinglish

def get_voice_prompt(step: int) -> str:
    """
    Get pre-written Hinglish voice prompt for conversation step.
    Steps: 0 (greeting + Q1), 1 (Q2), 2 (Q3), 3 (Q4), 4 (completion)
    """
    return VOICE_OUTPUT_TEMPLATE.get(step, "Kripaya dobara boliye. Samajh nahi aya.")

def render_voice_response(user_input: str, next_step: int) -> str:
    """
    Render voice response for webhook.
    Returns Hinglish prompt for next step.
    """
    # RAW SPEECH TEXT IS NOT STORED
    # Backend controls the conversation flow
    
    if next_step > 4:
        return "Dhanyavaad! Aapki jankari successfully store ho gayi. Hum aapke saath jald hi sambandh karenge. Goodbye!"
    
    return get_voice_prompt(next_step)

def get_conversation_steps():
    """Return all conversation steps"""
    return {
        0: "Initial greeting + Primary skill question",
        1: "Experience years question",
        2: "Skills and tools question",
        3: "Preferred location question",
        4: "Completion message"
    }
