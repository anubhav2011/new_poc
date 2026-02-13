from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uuid
import json
import logging
from typing import Optional, Dict

from ..db import crud
from ..services.experience_extractor import extract_from_responses, validate_extracted_experience

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/experience", tags=["experience"])

# System prompt questions (following the provided system prompt)
SYSTEM_QUESTIONS = {
    0: {
        "question": "Namaste! Main Job Support Team se bol raha hoon.\nAapne e-Shram portal par job ke liye apply kiya tha.\nAapka profile complete karne ke liye main aapse kuch sawal poochna chahta hoon.\nKya aap abhi baat kar sakte hain?",
        "field": "consent",
        "next_question": 1
    },
    1: {
        "question": "Aap kaunsa kaam karte hain?\nJaise electrician, plumber, driver, painter, helper, ya koi aur kaam.",
        "field": "primary_skill",
        "next_question": 2
    },
    2: {
        "question": "Is kaam mein aapko lagbhag kitne saal ka experience hai?\nJaise 1 saal, 3 saal, ya 5 saal.",
        "field": "experience_years",
        "next_question": 3
    },
    3: {
        "question": "Is kaam mein aap kya-kya kaam kar lete hain?\nJaise wiring, fitting, repair, loading-unloading, ya cleaning.",
        "field": "skills",
        "next_question": 4
    },
    4: {
        "question": "Aap kaunse tools ya machine ka use karte hain?\nJaise tester, drill machine, spanner, welding machine.",
        "field": "tools",
        "next_question": 5
    },
    5: {
        "question": "Aap kis area mein kaam karna chahte hain aur kab se kaam shuru kar sakte hain?\nJaise apne sheher mein, paas ke area mein, ya turant join kar sakte hain.",
        "field": "preferred_location",
        "next_question": -1  # End of conversation
    }
}

CLOSING_MESSAGE = "Dhanyavaad!\nAapke jawab ke base par hum aapka profile aur resume banaenge.\nAgar koi suitable job hogi, toh aapse sampark kiya jayega.\nAapka din shubh ho."


class StartSessionRequest(BaseModel):
    worker_id: str


class ChatMessageRequest(BaseModel):
    session_id: str
    message: str


class ExtractRequest(BaseModel):
    session_id: str


@router.post("/start")
async def start_experience_session(request: StartSessionRequest):
    """
    Start a new experience collection session for a worker.
    Creates a conversation session and returns the first question.
    """
    try:
        worker_id = request.worker_id
        
        # Verify worker exists
        worker = crud.get_worker(worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found")
        
        # Create session
        session_id = str(uuid.uuid4())
        success = crud.create_experience_session(session_id, worker_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to create session")
        
        # Return first question (greeting + consent)
        first_question = SYSTEM_QUESTIONS[0]["question"]
        
        logger.info(f"Experience session started: {session_id} for worker {worker_id}")
        
        return JSONResponse(
            status_code=200,
            content={
                "session_id": session_id,
                "question": first_question,
                "question_number": 0,
                "total_questions": len(SYSTEM_QUESTIONS)
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting experience session: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/chat")
async def chat_message(request: ChatMessageRequest):
    """
    Handle a chat message from the user.
    Stores the response and returns the next question.
    Follows the system prompt strictly - one question at a time.
    """
    try:
        session_id = request.session_id
        user_message = request.message.strip()
        
        if not user_message:
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        
        # Get session
        session = crud.get_experience_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        if session["status"] != "active":
            raise HTTPException(status_code=400, detail="Session is not active")
        
        current_question = session["current_question"]
        raw_conversation = json.loads(session.get("raw_conversation", "{}"))
        
        # Store user response
        if current_question == 0:
            # Consent question - just store yes/no
            raw_conversation["consent"] = user_message
            # If user doesn't consent, end session
            if "nahi" in user_message.lower() or "no" in user_message.lower() or "nhi" in user_message.lower():
                crud.update_experience_session(session_id, current_question + 1, raw_conversation, "declined")
                return JSONResponse(
                    status_code=200,
                    content={
                        "session_id": session_id,
                        "question": "Dhanyavaad. Aap jab ready ho, phir se baat kar sakte hain.",
                        "question_number": -1,
                        "status": "declined"
                    }
                )
        else:
            # Store response for the current question
            question_info = SYSTEM_QUESTIONS.get(current_question)
            if question_info:
                field = question_info["field"]
                raw_conversation[field] = user_message
        
        # Determine next question
        next_question_num = current_question + 1
        
        if next_question_num >= len(SYSTEM_QUESTIONS):
            # All questions answered - mark as complete
            crud.update_experience_session(session_id, next_question_num, raw_conversation, "completed")
            
            return JSONResponse(
                status_code=200,
                content={
                    "session_id": session_id,
                    "question": CLOSING_MESSAGE,
                    "question_number": -1,
                    "status": "completed",
                    "message": "All questions answered. Please call /extract to structure the data."
                }
            )
        
        # Get next question
        next_question_info = SYSTEM_QUESTIONS[next_question_num]
        next_question = next_question_info["question"]
        
        # Update session
        crud.update_experience_session(session_id, next_question_num, raw_conversation, "active")
        
        logger.info(f"Chat message processed: session={session_id}, question={next_question_num}")
        
        return JSONResponse(
            status_code=200,
            content={
                "session_id": session_id,
                "question": next_question,
                "question_number": next_question_num,
                "total_questions": len(SYSTEM_QUESTIONS)
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing chat message: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/extract")
async def extract_experience(request: ExtractRequest):
    """
    Extract structured experience data from the raw conversation.
    Uses LLM to structure the responses into JSON format.
    Stores both raw conversation and structured data.
    """
    try:
        session_id = request.session_id
        
        # Get session
        session = crud.get_experience_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        if session["status"] != "completed":
            raise HTTPException(status_code=400, detail="Session must be completed before extraction")
        
        # Get raw conversation
        raw_conversation = json.loads(session.get("raw_conversation", "{}"))
        
        if not raw_conversation:
            raise HTTPException(status_code=400, detail="No conversation data found")
        
        # Extract structured data using experience extractor
        # Map the fields from system prompt to extractor format
        responses_for_extraction = {
            "primary_skill": raw_conversation.get("primary_skill", ""),
            "experience_years": raw_conversation.get("experience_years", ""),
            "skills": raw_conversation.get("skills", ""),
            "tools": raw_conversation.get("tools", ""),
            "preferred_location": raw_conversation.get("preferred_location", "")
        }
        
        structured_data = extract_from_responses(responses_for_extraction)
        
        # The extractor now handles skills and tools separately in new format
        # Keep backward compatibility
        if not structured_data.get("skills") and responses_for_extraction.get("skills"):
            if isinstance(structured_data.get("skills"), list):
                structured_data["skills"] = structured_data["skills"]
            else:
                structured_data["skills"] = [responses_for_extraction["skills"]]
        
        # Tools are now separate in new format, but combine for backward compatibility
        if structured_data.get("tools") and not structured_data.get("skills_combined"):
            all_items = structured_data.get("skills", []) + structured_data.get("tools", [])
            structured_data["skills_combined"] = all_items
        
        # Validate extracted data
        if not validate_extracted_experience(structured_data):
            logger.warning(f"Extracted experience data validation failed for session {session_id}")
        
        # Save structured experience to database
        worker_id = session["worker_id"]
        success = crud.save_experience(worker_id, structured_data)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to save experience data")
        
        # Update session with structured data
        crud.update_experience_session_with_structured_data(
            session_id, 
            json.dumps(raw_conversation, ensure_ascii=False),
            json.dumps(structured_data, ensure_ascii=False)
        )
        
        logger.info(f"Experience extracted and saved: session={session_id}, worker={worker_id}")
        
        return JSONResponse(
            status_code=200,
            content={
                "session_id": session_id,
                "worker_id": worker_id,
                "structured_data": structured_data,
                "message": "Experience data extracted and saved successfully"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting experience: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/session/{session_id}")
async def get_session_status(session_id: str):
    """Get the current status of an experience session"""
    try:
        session = crud.get_experience_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return JSONResponse(
            status_code=200,
            content={
                "session_id": session_id,
                "worker_id": session["worker_id"],
                "current_question": session["current_question"],
                "status": session["status"],
                "created_at": session["created_at"]
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session status: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
