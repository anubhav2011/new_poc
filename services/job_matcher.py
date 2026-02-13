import json
import os
import logging
from typing import List

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

"""
Job Matcher - Match worker skills against job listings
"""


def calculate_skill_match(worker_skills: List[str], job_skills: List[str]) -> float:
    """
    Calculate match score between worker and job skills.
    Returns score between 0 and 1.
    """

    if not worker_skills or not job_skills:
        return 0.5

    worker_skills_lower = [s.lower() for s in worker_skills]
    job_skills_lower = [s.lower() for s in job_skills]

    # Count matches
    matches = 0
    for skill in job_skills_lower:
        for worker_skill in worker_skills_lower:
            if skill in worker_skill or worker_skill in skill:
                matches += 1
                break

    # Score calculation
    if not job_skills_lower:
        return 0.5

    score = matches / len(job_skills_lower)
    return min(score, 1.0)


def calculate_location_match(worker_location: str, job_location: str) -> float:
    """
    Calculate location match.
    Returns 1.0 if same, 0.8 if nearby, 0.5 otherwise.
    """

    if not worker_location or not job_location:
        return 0.5

    w_loc = worker_location.lower().strip()
    j_loc = job_location.lower().strip()

    if w_loc == j_loc:
        return 1.0

    # Nearby locations (NCR region example)
    nearby_groups = [
        ["delhi", "gurgaon", "noida", "faridabad", "greater noida"],
        ["mumbai", "pune"],
        ["bangalore", "hyderabad"],
    ]

    for group in nearby_groups:
        if w_loc in group and j_loc in group:
            return 0.8

    return 0.5


def match_worker_to_job(
        worker_id: str,
        worker_skills: List[str],
        worker_experience_years: int,
        worker_location: str,
        job_title: str,
        job_description: str,
        job_required_skills: List[str],
        job_location: str
) -> dict:
    """
    Match worker to job and generate score with explanation.
    """

    # Skill match (50% weight)
    skill_score = calculate_skill_match(worker_skills, job_required_skills)

    # Location match (30% weight)
    location_score = calculate_location_match(worker_location, job_location)

    # Experience match (20% weight)
    # Assume each job needs 1+ years experience
    exp_score = min(worker_experience_years / max(1, worker_experience_years),
                    1.0) if worker_experience_years > 0 else 0.5

    # Final score
    final_score = (skill_score * 0.5) + (location_score * 0.3) + (exp_score * 0.2)

    # Generate explanation
    explanation_parts = []

    if skill_score > 0.7:
        explanation_parts.append(f"Strong skill match ({int(skill_score * 100)}%)")
    elif skill_score > 0.3:
        explanation_parts.append(f"Moderate skill match ({int(skill_score * 100)}%)")
    else:
        explanation_parts.append(f"Limited skill match ({int(skill_score * 100)}%)")

    if location_score == 1.0:
        explanation_parts.append("Location match")
    elif location_score > 0.7:
        explanation_parts.append("Nearby location")
    else:
        explanation_parts.append("Location mismatch")

    if worker_experience_years > 0:
        explanation_parts.append(f"{worker_experience_years} years experience")

    explanation = ". ".join(explanation_parts)

    return {
        "match_score": round(final_score, 2),
        "explanation": explanation,
        "skill_score": round(skill_score, 2),
        "location_score": round(location_score, 2),
        "experience_score": round(exp_score, 2),
    }


def generate_sample_jobs() -> List[dict]:
    """Generate sample job listings for testing"""

    jobs = [
        {
            "title": "Painter",
            "description": "Experienced painter for residential and commercial work",
            "required_skills": ["painting", "color matching", "surface preparation"],
            "location": "Delhi"
        },
        {
            "title": "Electrician",
            "description": "Licensed electrician for installation and maintenance",
            "required_skills": ["electrical", "wiring", "maintenance", "safety"],
            "location": "Delhi NCR"
        },
        {
            "title": "Plumber",
            "description": "Professional plumber for pipe fitting and repair",
            "required_skills": ["plumbing", "pipe fitting", "repair", "installation"],
            "location": "Gurgaon"
        },
        {
            "title": "Carpenter",
            "description": "Skilled carpenter for furniture and structural work",
            "required_skills": ["carpentry", "woodwork", "finishing", "installation"],
            "location": "Noida"
        },
        {
            "title": "Welder",
            "description": "Experienced welder for metal fabrication",
            "required_skills": ["welding", "fabrication", "safety", "inspection"],
            "location": "Greater Noida"
        },
        {
            "title": "Mason",
            "description": "Skilled mason for construction and finishing",
            "required_skills": ["masonry", "tiling", "plastering", "construction"],
            "location": "Faridabad"
        },
        {
            "title": "Mechanic",
            "description": "General mechanic for equipment repair",
            "required_skills": ["mechanical repair", "troubleshooting", "maintenance"],
            "location": "Delhi"
        },
        {
            "title": "Construction Laborer",
            "description": "General construction work and material handling",
            "required_skills": ["construction", "labor", "material handling"],
            "location": "Delhi NCR"
        },
        {
            "title": "HVAC Technician",
            "description": "HVAC installation and maintenance specialist",
            "required_skills": ["hvac", "installation", "maintenance", "troubleshooting"],
            "location": "Gurgaon"
        },
        {
            "title": "Tiles & Flooring Specialist",
            "description": "Specialist for tile and flooring work",
            "required_skills": ["tiling", "flooring", "finishing", "installation"],
            "location": "Noida"
        },
        {
            "title": "General Maintenance Worker",
            "description": "Multi-skilled maintenance worker",
            "required_skills": ["maintenance", "repair", "cleaning", "general labor"],
            "location": "Delhi"
        },
        {
            "title": "Concrete Specialist",
            "description": "Concrete work for construction projects",
            "required_skills": ["concrete", "construction", "finishing"],
            "location": "Greater Noida"
        },
        {
            "title": "Painter - Decorative",
            "description": "Decorative and interior painting specialist",
            "required_skills": ["painting", "design", "color", "finishing"],
            "location": "Delhi NCR"
        },
        {
            "title": "Plumbing Supervisor",
            "description": "Senior plumber for project supervision",
            "required_skills": ["plumbing", "supervision", "inspection", "planning"],
            "location": "Gurgaon"
        },
        {
            "title": "Building Maintenance",
            "description": "Comprehensive building maintenance services",
            "required_skills": ["maintenance", "repair", "safety", "inspection"],
            "location": "Noida"
        },
    ]

    return jobs
