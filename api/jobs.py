from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import json

from ..db import crud
from ..services.job_matcher import match_worker_to_job, generate_sample_jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.get("/seed")
async def seed_sample_jobs():
    """
    Seed database with sample job listings.
    Run once during initialization.
    """
    
    jobs = generate_sample_jobs()
    
    for job in jobs:
        job_id = crud.save_job_listing(
            job["title"],
            job["description"],
            job["required_skills"],
            job["location"]
        )
        
        if not job_id:
            raise HTTPException(status_code=500, detail=f"Failed to save job: {job['title']}")
    
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": f"Seeded {len(jobs)} sample jobs",
            "count": len(jobs)
        }
    )

@router.get("/match")
async def match_worker_to_jobs(worker_id: str):
    """
    Match worker to suitable jobs.
    Returns top matching jobs with scores.
    
    GET /jobs/match?worker_id=UUID
    """
    
    # Get worker data
    worker = crud.get_worker(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    
    # Get worker experience
    experience = crud.get_experience(worker_id)
    if not experience:
        raise HTTPException(status_code=400, detail="Experience data not found")
    
    # Get all jobs
    jobs = crud.get_all_jobs()
    
    # Match worker to each job
    matches = []
    
    for job in jobs:
        match_data = match_worker_to_job(
            worker_id,
            experience.get("skills", []),
            experience.get("experience_years", 0),
            experience.get("preferred_location", ""),
            job.get("title", ""),
            job.get("description", ""),
            job.get("required_skills", []),
            job.get("location", "")
        )
        
        matches.append({
            "job_id": job.get("id") or job.get("job_id"),
            "title": job.get("title"),
            "location": job.get("location"),
            "match_score": match_data["match_score"],
            "explanation": match_data["explanation"],
            "skill_match": match_data["skill_score"],
            "location_match": match_data["location_score"],
        })
    
    # Sort by match score
    matches.sort(key=lambda x: x["match_score"], reverse=True)
    
    # Return top 10
    top_matches = matches[:10]
    
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "worker_id": worker_id,
            "worker_name": worker.get("name", "Unknown"),
            "total_jobs": len(jobs),
            "matches": top_matches
        }
    )

@router.get("/all")
async def get_all_jobs():
    """Get all job listings"""
    
    jobs = crud.get_all_jobs()
    
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "count": len(jobs),
            "jobs": jobs
        }
    )

@router.get("/{job_id}")
async def get_job_details(job_id: int):
    """Get specific job details"""
    
    jobs = crud.get_all_jobs()
    
    job = None
    for j in jobs:
        if j.get("job_id") == job_id or j.get("id") == job_id:
            job = j
            break
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "job": job
        }
    )
