# from pydantic import BaseModel
# from typing import Optional, List, Union
#
# class SignupRequest(BaseModel):
#     """Request body for POST /form/signup. Send JSON: {\"mobile_number\": \"7905285898\"}."""
#     mobile_number: str
#
#
# class SignupResponse(BaseModel):
#     """Response from signup. Use worker_id for POST /form/submit."""
#     status: str
#     worker_id: str
#     mobile_number: str
#     name: Optional[str] = None
#     is_new_worker: bool
#     has_experience: bool
#     has_cv: bool
#
# class WorkerCreate(BaseModel):
#     mobile_number: str
#     consent: bool
#
# class WorkerData(BaseModel):
#     worker_id: str
#     name: Optional[str] = None
#     dob: Optional[str] = None
#     address: Optional[str] = None
#     mobile_number: str
#
# class WorkExperience(BaseModel):
#     worker_id: str
#     primary_skill: Optional[str] = None
#     experience_years: Optional[int] = None
#     skills: Optional[list] = None
#     preferred_location: Optional[str] = None
#
# class VoiceWebhookInput(BaseModel):
#     call_id: str
#     worker_id: Optional[str] = None  # Optional - can be resolved from phone_number
#     phone_number: Optional[str] = None  # Optional - used to lookup worker_id
#     speech_text: str
#
#
# class TranscriptSubmitRequest(BaseModel):
#     """Request body for Voice Agent submitting full conversation transcript."""
#     call_id: str
#     worker_id: Optional[str] = None  # Optional - can be resolved from phone_number
#     phone_number: Optional[str] = None  # Optional - used to lookup worker_id
#     transcript: str
#
#
# class LinkCallToWorkerRequest(BaseModel):
#     """Request to link call_id to worker_id after transcript is collected."""
#     call_id: str
#     worker_id: str
#
#
# class ExperienceConfirmRequest(BaseModel):
#     """Request body for confirming and submitting experience data for CV generation."""
#     call_id: str
#     worker_id: str
#     experience: dict  # The experience data object (can be edited or original from LLM extraction)
#
# class JobListing(BaseModel):
#     title: str
#     description: str
#     required_skills: list
#     location: str
#
# class JobMatch(BaseModel):
#     job_id: int
#     title: str
#     match_score: float
#     explanation: str
#
#
# class EducationalDocument(BaseModel):
#     worker_id: str
#     document_type: Optional[str] = None
#     qualification: Optional[str] = None
#     board: Optional[str] = None
#     stream: Optional[str] = None
#     year_of_passing: Optional[str] = None
#     school_name: Optional[str] = None
#     marks_type: Optional[str] = None
#     marks: Optional[str] = None
#     percentage: Optional[Union[str, float]] = None  # DB stores REAL
#
#
# class WorkerDataResponse(BaseModel):
#     """Response for GET /form/worker/{worker_id}/data: personal details, education, and resume status."""
#     status: str
#     worker: WorkerData
#     education: List[EducationalDocument] = []
#     has_experience: bool = False
#     has_cv: bool = False

from pydantic import BaseModel
from typing import Optional, List, Union

class SignupRequest(BaseModel):
    """Request body for POST /form/signup. Send JSON: {\"mobile_number\": \"7905285898\"}."""
    mobile_number: str


class SignupResponse(BaseModel):
    """Response from signup. Use worker_id for POST /form/submit."""
    status: str
    worker_id: str
    mobile_number: str
    name: Optional[str] = None
    is_new_worker: bool
    has_experience: bool
    has_cv: bool

class WorkerCreate(BaseModel):
    mobile_number: str
    consent: bool

class WorkerData(BaseModel):
    worker_id: str
    name: Optional[str] = None
    dob: Optional[str] = None
    address: Optional[str] = None
    mobile_number: str

class WorkExperience(BaseModel):
    worker_id: str
    primary_skill: Optional[str] = None
    experience_years: Optional[int] = None
    skills: Optional[list] = None
    preferred_location: Optional[str] = None

class VoiceWebhookInput(BaseModel):
    call_id: str
    worker_id: Optional[str] = None  # Optional - can be resolved from phone_number
    phone_number: Optional[str] = None  # Optional - used to lookup worker_id
    speech_text: str


class TranscriptSubmitRequest(BaseModel):
    """Request body for Voice Agent submitting full conversation transcript."""
    call_id: str
    worker_id: Optional[str] = None  # Optional - can be resolved from phone_number
    phone_number: Optional[str] = None  # Optional - used to lookup worker_id
    transcript: str


class LinkCallToWorkerRequest(BaseModel):
    """Request to link call_id to worker_id after transcript is collected."""
    call_id: str
    worker_id: str


class ExperienceConfirmRequest(BaseModel):
    """Request body for confirming and submitting experience data for CV generation."""
    call_id: str
    worker_id: str
    experience: dict  # The experience data object (can be edited or original from LLM extraction)

class JobListing(BaseModel):
    title: str
    description: str
    required_skills: list
    location: str

class JobMatch(BaseModel):
    job_id: int
    title: str
    match_score: float
    explanation: str


class EducationalDocument(BaseModel):
    worker_id: str
    document_type: Optional[str] = None
    qualification: Optional[str] = None
    board: Optional[str] = None
    stream: Optional[str] = None
    year_of_passing: Optional[str] = None
    school_name: Optional[str] = None
    marks_type: Optional[str] = None
    marks: Optional[str] = None
    percentage: Optional[Union[str, float]] = None  # DB stores REAL


class WorkerDataResponse(BaseModel):
    """Response for GET /form/worker/{worker_id}/data: personal details, education, and resume status."""
    status: str
    worker: WorkerData
    education: List[EducationalDocument] = []
    has_experience: bool = False
    has_cv: bool = False