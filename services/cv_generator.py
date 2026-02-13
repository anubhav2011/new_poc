import asyncio
import base64
import concurrent.futures
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

"""
CV Generator - Create one-page resume from structured data
Supports both LLM-based and template-based generation
"""


def _load_image_as_base64(image_path: Path) -> Optional[str]:
    """Load an image file and return it as a base64 data URL."""
    try:
        if image_path.exists():
            with open(image_path, "rb") as img_file:
                img_data = img_file.read()
                img_base64 = base64.b64encode(img_data).decode("utf-8")
                # Determine MIME type from extension
                ext = image_path.suffix.lower()
                mime_type = "image/png" if ext == ".png" else "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
                return f"data:{mime_type};base64,{img_base64}"
        else:
            logger.warning(f"Image not found: {image_path}")
            return None
    except Exception as e:
        logger.warning(f"Failed to load image {image_path}: {e}")
        return None


def _verified_badge_icon_html() -> str:
    """Generate verified badge icon (checkmark in circle) for personal details."""
    return '''<svg width="14" height="14" viewBox="0 0 24 24" fill="none" style="display: inline-block; margin-left: 4px; vertical-align: middle;">
        <circle cx="12" cy="12" r="11" fill="#10B981" stroke="#059669" stroke-width="1.5"/>
        <path d="M8 12l2.5 2.5L16 9" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>'''


def clean_location_for_display(location_text: str) -> str:
    """
    Clean location name for CV display - extract only city name.
    """
    if not location_text or location_text == "Not specified":
        return "Not specified"

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


def generate_cv_html(worker_data: dict, experience_data: dict, education_data_list=None) -> str:
    """
    Generate HTML CV: EXACT template matching the provided design.
    Two-column layout: Dark blue left sidebar, white right main area.

    Args:
        worker_data: Personal information dict
        experience_data: Work experience dict
        education_data_list: List of education dicts (can be None, single dict, or list)
    """
    # Handle education_data_list - can be None, single dict, or list
    if education_data_list is None:
        education_list = []
    elif isinstance(education_data_list, dict):
        education_list = [education_data_list]
    else:
        education_list = education_data_list

    # Generate verified badge icon for personal details
    verified_badge = _verified_badge_icon_html()

    # Extract name - split first and last name for proper formatting
    full_name = worker_data.get("name") or "Worker"
    name_parts = full_name.strip().split(" ", 1)
    first_name = name_parts[0] if name_parts else "Worker"
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    primary_skill = experience_data.get("primary_skill") or experience_data.get("job_title") or "Not specified"

    # Use total_experience_duration (in months) if available, otherwise fall back to experience_years
    total_duration_months = experience_data.get("total_experience_duration") or 0
    if total_duration_months:
        # Convert months to years with decimal precision
        exp_years = round(total_duration_months / 12, 1)
        logger.info(
            f"[CV GENERATOR] Using calculated experience duration: {total_duration_months} months = {exp_years} years")
    else:
        # Fallback to experience_years field if total duration not available
        exp_years = int(experience_data.get("experience_years") or 0)
        logger.info(f"[CV GENERATOR] Using experience_years field: {exp_years} years")
    raw_location = experience_data.get("preferred_location") or ""
    location = clean_location_for_display(raw_location) if raw_location else "Not specified"
    mobile = worker_data.get("mobile_number") or "Not provided"
    dob = worker_data.get("dob") or "Not provided"
    address = worker_data.get("address") or "Not specified"

    # NEW: Use current_location from experience_data if available, otherwise use address
    current_location_from_exp = experience_data.get("current_location", "")
    if current_location_from_exp:
        current_location = clean_location_for_display(current_location_from_exp)
    elif address and address != "Not specified":
        # Use full address for current location (e.g. KAMLA RAMAN NAGAR, BAIGANWADI, MUMBAI)
        current_location = ", ".join(part.strip() for part in address.split(",") if part.strip())
    else:
        current_location = location

    skills_list = experience_data.get("skills") or []
    tools_list = experience_data.get("tools") or []
    if isinstance(skills_list, str):
        skills_list = [s.strip() for s in skills_list.split(",") if s.strip()]
    if isinstance(tools_list, str):
        tools_list = [t.strip() for t in tools_list.split(",") if t.strip()]

    # Normalize to list of (name, verified) - backward compatible: string => self-reported
    def _skill_item(x):
        if isinstance(x, dict):
            name = str(x.get("name", "")).strip()
            # Capitalize first letter of skill/tool name
            name = name.capitalize() if name else ""
            return (name, bool(x.get("verified", False)))
        name = str(x).strip()
        # Capitalize first letter of skill/tool name
        name = name.capitalize() if name else ""
        return (name, False)

    # Keep skills and tools separate (skills first, then tools on left sidebar)
    norm_skills = [_skill_item(s) for s in (skills_list or []) if _skill_item(s)[0]][:15]
    norm_tools = [_skill_item(t) for t in (tools_list or []) if _skill_item(t)[0]][:15]
    # Fallback: if no skills at all, show primary_skill under Skills only
    if not norm_skills and primary_skill != "Not specified":
        norm_skills = [(primary_skill, False)]

    # ABOUT section text - include availability if available
    # Use calculated experience duration in the about text
    availability = experience_data.get("availability", "")
    if availability and availability.strip() and availability.lower() != "not specified":
        about_text = f"Experienced {primary_skill} with {exp_years} years of professional experience. Seeking opportunities in {location}. Available: {availability}."
    else:
        about_text = f"Experienced {primary_skill} with {exp_years} years of professional experience. Seeking opportunities in {location}."

    # Load logo images as base64
    BASE_DIR = Path(__file__).resolve().parent.parent
    verified_logo_path = BASE_DIR / "assets" / "logos" / "verified.png"
    self_verified_logo_path = BASE_DIR / "assets" / "logos" / "self_verified.png"
    self_declared_logo_path = BASE_DIR / "assets" / "logos" / "self_declared.png"
    check_logo_path = BASE_DIR / "assets" / "logos" / "check.png"

    verified_logo_b64 = _load_image_as_base64(verified_logo_path)
    self_verified_logo_b64 = _load_image_as_base64(self_verified_logo_path)
    self_declared_logo_b64 = _load_image_as_base64(self_declared_logo_path)
    check_logo_b64 = _load_image_as_base64(check_logo_path)

    # Yellow self-declared badge: used for skills, tools, and work experience in the CV
    def _self_declared_badge_html() -> str:
        if self_declared_logo_b64:
            return f'<span class="badge-self-reported"><img src="{self_declared_logo_b64}" class="badge-logo" alt="Self Declared" /></span>'
        return '<span class="badge-self-reported"><span class="badge-icon">👤</span></span>'

    # Green checkmark icon: used for education fields fetched from documents
    def _education_check_icon_html() -> str:
        if check_logo_b64:
            return f'<img src="{check_logo_b64}" class="edu-check-icon" alt="Verified" />'
        return '<span class="edu-check-icon">✓</span>'

    # LOCATION PREFERRED section - separate from contact
    location_preferred_html = f"""
            <div class="sidebar-row">
                <span class="sidebar-label">Location</span>
                <span class="sidebar-value">{location}</span>
            </div>"""

    # VIDEO INTRODUCTION section - moved below ABOUT
    # check_icon = _education_check_icon_html()
    video_url = (worker_data.get("video_url") or "").strip()
    video_introduction_html = ""
    if video_url and video_url.startswith("http"):
        video_introduction_html = f"""
            <div class="sidebar-row">
                <span class="sidebar-value"><a href="{video_url}" target="_blank" rel="noopener" class="video-link">Watch video</a></span>
            </div>"""

    # CONTACT section - removed, now showing only Phone Number and Current Location in left sidebar
    # (Current Location and Phone are shown in right sidebar under Personal Details instead)
    contact_html = ""

    # Build one row: "Name [icon]" on same line; always use yellow self-declared icon for skills/tools
    def _skill_row_html(name: str, verified: bool) -> str:
        badge = _self_declared_badge_html()
        return f'<div class="skill-item"><span class="skill-name">{name}</span> <span class="skill-badge">{badge}</span></div>'

    # SKILLS section - skills first
    skills_html = "".join(_skill_row_html(name, verified) for name, verified in norm_skills)
    # TOOLS section - tools after skills
    tools_html = "".join(_skill_row_html(name, verified) for name, verified in norm_tools)

    # EDUCATION section - multiple entries (10th, 12th, etc.)
    education_blocks = []
    check_icon = _education_check_icon_html()
    for edu in education_list:
        qual = edu.get("qualification") or ""
        board = edu.get("board") or ""
        school = edu.get("school_name") or ""
        year = edu.get("year_of_passing") or ""
        stream = edu.get("stream") or ""
        marks = edu.get("marks") or ""

        if qual or board or school or year:
            # Build rows with icons only when values exist (for document-fetched education data)
            qual_html = f"{qual or 'Education'} {check_icon}" if qual else "Education"
            board_html = f"{board} {check_icon}" if board else ""
            school_html = f"{school} {check_icon}" if school else ""
            year_html = f"{year} {check_icon}" if year else ""
            stream_html = f"{stream} {check_icon}" if stream else ""
            marks_html = f"{marks} {check_icon}" if marks else ""

            education_blocks.append(f"""
            <div class="edu-entry">
                <div class="edu-qualification">{qual_html}</div>
                <div class="edu-row"><span class="edu-label">Board:</span> <span class="edu-val">{board_html}</span></div>
                <div class="edu-row"><span class="edu-label">School:</span> <span class="edu-val">{school_html}</span></div>
                <div class="edu-row"><span class="edu-label">Year of Passing:</span> <span class="edu-val">{year_html}</span></div>
                <div class="edu-row"><span class="edu-label">Stream:</span> <span class="edu-val">{stream_html}</span></div>
                <div class="edu-row"><span class="edu-label">Marks:</span> <span class="edu-val">{marks_html}</span></div>
            </div>""")

    if not education_blocks:
        education_blocks = ['<div class="edu-entry"><div class="edu-val">No educational details provided</div></div>']
    education_section = "".join(education_blocks)

    # WORK EXPERIENCE section - display float value for total experience
    # Format: 5.5 Years, 3.0 Years, etc.
    exp_text = f"{exp_years} Years" if exp_years > 0 else "0 Years"
    experience_verified = bool(experience_data.get("experience_verified", False))

    # NEW: Work experience entries with multiple workplaces
    # Badge: always yellow self-declared icon for work experience
    experience_entries = []
    exp_badge = _self_declared_badge_html()

    # NEW: Get workplaces array from experience_data
    workplaces = experience_data.get("workplaces", [])
    if not isinstance(workplaces, list):
        workplaces = []

    # NEW: Display all workplaces with their locations and durations matching image format
    # Format: Job Title on one line, Location on next line, Duration on next line
    if workplaces and len(workplaces) > 0:
        for idx, workplace in enumerate(workplaces):
            workplace_name = workplace.get("workplace_name", "Workplace") if isinstance(workplace, dict) else str(
                workplace)
            work_location = workplace.get("work_location", "") if isinstance(workplace, dict) else ""
            work_duration = workplace.get("work_duration", "") if isinstance(workplace, dict) else ""

            # Format workplace entry: title, location, duration each on separate lines
            experience_entries.append(f"""
            <div class="exp-entry">
                <div class="exp-job-title">{workplace_name}</div>
                {f'<div class="exp-location">{work_location}</div>' if work_location else ''}
                {f'<div class="exp-duration">Duration: {work_duration}</div>' if work_duration else ''}
            </div>""")

    # Fallback: If no workplaces but have primary skill and experience, show summary
    if not experience_entries and primary_skill != "Not specified" and exp_years > 0:
        experience_entries.append(f"""
            <div class="exp-entry">
                <div class="exp-job-title">{primary_skill}</div>
                <div class="exp-duration">Duration: {exp_years} Years</div>
            </div>""")

    if not experience_entries:
        experience_entries = ['<div class="exp-entry"><div class="exp-val">No work experience provided</div></div>']
    experience_section = "".join(experience_entries)

    # Footer legend: which icon denotes what (verified / self-declared) — does not change main layout
    def _legend_icon(img_b64, fallback_char, alt_text):
        if img_b64:
            return f'<img src="{img_b64}" class="legend-icon" alt="{alt_text}" />'
        return f'<span class="legend-icon" style="font-size:12pt;">{fallback_char}</span>'

    legend_verified = _legend_icon(verified_logo_b64, "✓", "Verified")
    legend_self_declared = _legend_icon(self_declared_logo_b64, "◎", "Self Declared")
    footer_legend_html = f"""<div class="footer-legend"><table class="footer-legend-table" cellpadding="0" cellspacing="0" align="center"><tr><td><span class="legend-item">{legend_verified}<span class="legend-label">Verified</span></span></td><td><span class="legend-item">{legend_self_declared}<span class="legend-label">Self Declared</span></span></td></tr></table></div>"""

    # Table-based two-column layout for reliable PDF rendering (xhtml2pdf does not support flexbox)
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CV - {full_name}</title>
    <style>
        @page {{ size: A4; margin: 0; }}
        * {{ margin: 0; padding: 0; }}
        html, body {{ height: 297mm; min-height: 297mm; font-family: Arial, Calibri, sans-serif; font-size: 11pt; line-height: 1.5; color: #1F2937; background: #fff; }}
        table.cv-table {{ width: 100%; height: 297mm; min-height: 297mm; border-collapse: collapse; table-layout: fixed; -pdf-keep-in-frame-mode: shrink; }}
        table.cv-table td {{ vertical-align: top; }}
        td.sidebar-cell {{ width: 33%; background: #1E3A8A; color: #fff; padding: 30px 25px; }}
        td.main-cell {{ width: 67%; background: #fff; padding: 35px 40px; }}
        td.footer-cell {{ height: 32px; padding: 0 25px; background: #F9FAFB; border-top: 1px solid #E5E7EB; vertical-align: middle; text-align: center; }}
        .sidebar-title {{ font-size: 11pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; padding-bottom: 8px; margin-bottom: 15px; border-bottom: 2px solid rgba(255,255,255,0.5); }}
        .sidebar-row {{ margin-bottom: 14px; line-height: 1.3; }}
        .sidebar-label {{ font-size: 9pt; display: block; margin-bottom: 2px; color: rgba(255,255,255,0.9); }}
        .sidebar-value {{ font-weight: 700; font-size: 11pt; display: block; margin-top: 0; line-height: 1.35; }}
        .about-text {{ font-size: 10pt; line-height: 1.7; text-align: justify; }}
        .skill-item {{ margin-bottom: 12px; line-height: 1.4; }}
        .skill-name {{ font-size: 10pt; font-weight: 500; display: inline; }}
        .skill-badge {{ font-size: 8pt; font-weight: 400; display: inline; margin-left: 6px; vertical-align: middle; }}
        .badge-icon {{ font-size: 10pt; }}
        .badge-logo {{ width: 16px; height: 16px; vertical-align: middle; display: inline-block; }}
        .badge-verified {{ color: #93C5FD; }}
        .badge-self-reported {{ color: #9333EA; }}
        .badge-self-verified {{ color: #10B981; }}
        .name-heading {{ display: block; width: 100%; margin-bottom: 2px; }}
        .name-first {{ font-size: 28pt; font-weight: 700; color: #1F2937; line-height: 1.0; display: block !important; width: 100%; margin: 0 !important; padding: 0 !important; }}
        .name-last {{ font-size: 28pt; font-weight: 700; color: #1F2937; line-height: 1.0; display: block !important; width: 100%; margin: 0 !important; padding: 0 !important; margin-top: 4px !important; }}
        .main-role {{ font-size: 14pt; color: #4B5563; margin-top: 5px; margin-bottom: 18px; }}
        .main-section {{ margin-bottom: 25px; page-break-inside: avoid; }}
        .main-title {{ font-size: 12pt; font-weight: 700; text-transform: uppercase; color: #1E3A8A; padding-bottom: 8px; margin-bottom: 15px; border-bottom: 2px solid #3B82F6; }}
        .edu-entry {{ margin-bottom: 18px; }}
        .edu-qualification {{ font-weight: 700; font-size: 11pt; margin-bottom: 8px; color: #1F2937; }}
        .edu-row {{ font-size: 10pt; margin-bottom: 4px; }}
        .edu-label {{ color: #6B7280; }}
        .edu-val {{ color: #374151; }}
        .detail-row {{ margin-bottom: 12px; font-size: 10pt; line-height: 1.3; }}
        .detail-label {{ display: block; color: #6B7280; font-weight: 600; font-size: 9pt; margin-bottom: 2px; }}
        .detail-value {{ display: block; color: #374151; font-weight: 500; }}
        .edu-check-icon {{ width: 14px; height: 14px; vertical-align: middle; display: inline-block; margin-left: 4px; }}
        .exp-total {{ font-size: 11pt; margin-bottom: 18px; font-weight: 600; }}
        .exp-entry {{ margin-bottom: 20px; page-break-inside: avoid; }}
        .exp-job-title {{ font-weight: 700; font-size: 11pt; color: #1F2937; margin-bottom: 6px; }}
        .exp-location {{ font-weight: 600; font-size: 10pt; color: #374151; margin-bottom: 6px; }}
        .exp-duration {{ font-weight: 500; font-size: 10pt; color: #6B7280; }}
        .exp-entry-table {{ width: 100%; }}
        .exp-bullet-cell {{ width: 20px; padding-top: 6px; }}
        .exp-bullet {{ width: 8px; height: 8px; background: #3B82F6; border-radius: 50%; }}
        .exp-role {{ font-weight: 700; font-size: 11pt; color: #1F2937; margin-bottom: 4px; }}
        .exp-meta {{ font-size: 10pt; color: #6B7280; }}
        .exp-badge {{ font-size: 9pt; margin-left: 6px; }}
        .exp-val {{ color: #6B7280; }}
        .footer-legend {{ font-size: 8pt; color: #6B7280; text-align: center; margin: 0; padding: 0; }}
        .footer-legend-table {{ width: 100%; max-width: 280px; margin: 0 auto; border: 0; }}
        .footer-legend-table td {{ padding: 0 12px; vertical-align: middle; border: 0; text-align: center; }}
        .legend-item {{ display: inline-block; white-space: nowrap; }}
        .legend-icon {{ width: 14px; height: 14px; vertical-align: middle; display: inline-block; }}
        .legend-label {{ font-weight: 500; color: #4B5563; margin-left: 4px; vertical-align: middle; }}
        .video-link {{ color: #60A5FA; text-decoration: none; font-weight: 600; }}
        .video-link:hover {{ text-decoration: underline; }}
        @media print {{ body {{ margin: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }} }}
    </style>
</head>
<body>
<table class="cv-table" cellpadding="0" cellspacing="0">
<tr>
<td class="sidebar-cell">
    <div class="sidebar-title">ABOUT</div>
    <div class="about-text">{about_text}</div>
    {'<div class="sidebar-title" style="margin-top: 25px;">VIDEO INTRODUCTION</div>' + video_introduction_html if video_introduction_html else ''}
    <div class="sidebar-title" style="margin-top: 25px;">LOCATION PREFERRED</div>
    {location_preferred_html}
    <div class="sidebar-title" style="margin-top: 25px;">SKILLS</div>
    {skills_html}
    <div class="sidebar-title" style="margin-top: 25px;">TOOLS</div>
    {tools_html}
</td>
<td class="main-cell">
    <div class="name-heading">
        <div class="name-first">{first_name}</div>
        {f'<div class="name-last">{last_name}</div>' if last_name else ''}
    </div>
    <div class="main-role">{primary_skill}</div>
    <div class="main-section">
        <div class="main-title">PERSONAL DETAILS</div>
        <div class="detail-row">
            <span class="detail-label">Date of Birth (DD-MM-YYYY):</span>
            <span class="detail-value">{dob} {verified_badge}</span>
        </div>
        <div class="detail-row">
            <span class="detail-label">Contact Number:</span>
            <span class="detail-value">{mobile} {verified_badge}</span>
        </div>
        <div class="detail-row">
            <span class="detail-label">Current Location:</span>
            <span class="detail-value">{current_location} {verified_badge}</span>
        </div>
        <div class="detail-row">
            <span class="detail-label">Address:</span>
            <span class="detail-value">{address} {verified_badge}</span>
        </div>
    </div>
    <div class="main-section">
        <div class="main-title">EDUCATION</div>
        {education_section}
    </div>
    <div class="main-section">
        <div class="main-title">WORK EXPERIENCE</div>
        <div class="exp-total">Total years of experience: {exp_text}</div>
        {experience_section}
    </div>
</td>
</tr>
<tr>
<td colspan="2" class="footer-cell">{footer_legend_html}</td>
</tr>
</table>
</body>
</html>"""
    return html


def generate_cv_text(worker_data: dict, experience_data: dict, education_data=None) -> str:
    """Generate plain text CV"""
    # Handle education_data - can be None, single dict, or list
    if education_data is None:
        education_list = []
    elif isinstance(education_data, dict):
        education_list = [education_data]
    else:
        education_list = education_data

    name = worker_data.get('name', 'Worker')
    mobile = worker_data.get('mobile_number', 'Not provided')
    dob = worker_data.get('dob', 'Not provided')
    address = worker_data.get('address', 'Not specified')

    primary_skill = experience_data.get('primary_skill', 'Not specified')
    exp_years = experience_data.get('experience_years', 0)
    # Capitalize first letter of each skill
    skills_list = experience_data.get('skills', [])
    skills = ", ".join([s.capitalize() if isinstance(s, str) else str(s).capitalize() for s in skills_list])
    raw_location = experience_data.get('preferred_location', 'Not specified')
    location = clean_location_for_display(raw_location)

    # Build education section if available (multiple entries)
    education_text = ""
    if education_list:
        education_text = "\nEDUCATION\n"
        for edu in education_list:
            if edu.get("qualification"):
                education_text += f"\nQualification: {edu.get('qualification')}\n"
            if edu.get("board"):
                education_text += f"Board: {edu.get('board')}\n"
            if edu.get("school_name"):
                education_text += f"School/College: {edu.get('school_name')}\n"
            if edu.get("year_of_passing"):
                education_text += f"Year of Passing: {edu.get('year_of_passing')}\n"
            if edu.get("marks"):
                education_text += f"Marks: {edu.get('marks')}\n"
            education_text += "-" * 40 + "\n"

    text = f"""{'=' * 60}
RESUME
{'=' * 60}

NAME: {name}
MOBILE: {mobile}
DOB: {dob}
ADDRESS: {address}

PROFESSIONAL SUMMARY
Primary Skill: {primary_skill}
Experience: {exp_years} years
Preferred Location: {location}

SKILLS
{skills if skills else 'Not specified'}{education_text}

Generated: {datetime.now().strftime('%d-%m-%Y %H:%M')}
{'=' * 60}
"""

    return text


def _html_to_pdf_playwright(html_content: str, pdf_path: Path) -> bool:
    """
    Generate PDF using Playwright (Chromium). Matches browser rendering.
    Returns True if successful. On failure or if Playwright not installed, returns False.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.debug("Playwright not installed; will use xhtml2pdf fallback")
        return False
    # On Windows, worker thread needs ProactorEventLoop for Playwright's subprocess (Chromium).
    old_policy = None
    if sys.platform == "win32":
        old_policy = asyncio.get_event_loop_policy()
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        pdf_path = Path(pdf_path)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_content(html_content, wait_until="load")
            # Full A4: 210mm x 297mm. Content and blue sidebar stretch over entire page.
            page.pdf(
                path=str(pdf_path),
                format="A4",
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            )
            browser.close()
        if not pdf_path.exists() or pdf_path.stat().st_size == 0:
            return False
        with open(pdf_path, "rb") as f:
            if f.read(4) != b"%PDF":
                return False
        logger.info(f"PDF generated with Playwright: {pdf_path} (Size: {pdf_path.stat().st_size} bytes)")
        return True
    except Exception as e:
        msg = repr(e) if not str(e).strip() else str(e)
        logger.warning(f"Playwright PDF failed: {msg}")
        return False
    finally:
        if old_policy is not None:
            asyncio.set_event_loop_policy(old_policy)


def _html_to_pdf_pisa(html_content: str, pdf_path: Path) -> bool:
    """Fallback: convert HTML to PDF using xhtml2pdf (pisa)."""
    try:
        from xhtml2pdf import pisa
    except ImportError:
        logger.warning("xhtml2pdf not installed. Install with: pip install xhtml2pdf")
        return False
    if not html_content.strip().startswith("<!DOCTYPE"):
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        @page {{ size: A4; margin: 1cm; }}
        body {{ font-family: Arial, sans-serif; font-size: 12pt; line-height: 1.6; }}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""
    pdf_path = Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(pdf_path, "wb") as pdf_file:
            pisa_status = pisa.CreatePDF(html_content, dest=pdf_file, encoding="utf-8")
        if pisa_status.err:
            logger.error(f"xhtml2pdf errors: {pisa_status.err}")
            return False
    except Exception as e:
        logger.error(f"xhtml2pdf creation failed: {str(e)}", exc_info=True)
        return False
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        if pdf_path.exists():
            pdf_path.unlink()
        return False
    with open(pdf_path, "rb") as f:
        if f.read(4) != b"%PDF":
            return False
    logger.info(f"PDF generated with xhtml2pdf: {pdf_path} (Size: {pdf_path.stat().st_size} bytes)")
    return True


def html_to_pdf(html_content: str, pdf_path: Path) -> bool:
    """
    Convert HTML content to PDF. Tries Playwright (browser-accurate) first,
    then falls back to xhtml2pdf (pisa). Returns True if successful.
    When called from an asyncio context, runs Playwright in a thread to avoid
    "Sync API inside the asyncio loop" warning.
    """
    pdf_path = Path(pdf_path)

    def _try_playwright() -> bool:
        try:
            return _html_to_pdf_playwright(html_content, pdf_path)
        except Exception:
            return False

    try:
        asyncio.get_running_loop()
        in_async = True
    except RuntimeError:
        in_async = False

    if in_async:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_try_playwright)
            if future.result(timeout=60):
                return True
    else:
        if _try_playwright():
            return True

    if _html_to_pdf_pisa(html_content, pdf_path):
        return True
    logger.error("PDF generation failed (Playwright and xhtml2pdf both failed or unavailable)")
    return False


def save_cv(worker_id: str, worker_data: dict, experience_data: dict, cv_dir: Path, education_data=None,
            use_llm: bool = True, transcript: str = None) -> str:
    """
    Save CV in HTML, TXT, and PDF formats.
    Tries LLM generation first, falls back to template if LLM unavailable.

    Args:
        transcript: Optional conversation transcript for richer CV content

    Returns path to PDF file (or HTML if PDF generation fails).
    """

    cv_dir.mkdir(parents=True, exist_ok=True)

    # Filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    cv_name = f"CV_{worker_id}_{timestamp}"

    # ALWAYS use exact template - ensure consistent design
    # LLM generation disabled to maintain exact template match
    html_content = None
    # Note: LLM generation is disabled to ensure exact template is always used
    # Uncomment below if you want to use LLM with transcript, but template will be used as fallback
    # if use_llm and transcript:
    #     try:
    #         from .llm_cv_generator import generate_cv_with_llm
    #         llm_education = None
    #         if education_data:
    #             if isinstance(education_data, dict):
    #                 llm_education = education_data
    #             elif isinstance(education_data, list) and len(education_data) > 0:
    #                 llm_education = education_data[0]
    #         html_content = generate_cv_with_llm(worker_data, experience_data, llm_education, transcript=transcript)
    #         if html_content:
    #             logger.info("CV generated using LLM with transcript")
    #     except Exception as e:
    #         logger.warning(f"LLM CV generation failed, falling back to template: {str(e)}")

    # Always use exact template to match design
    if not html_content:
        # Handle education_data - can be single dict or list
        if education_data is None:
            education_list = None
        elif isinstance(education_data, dict):
            education_list = [education_data]
        else:
            education_list = education_data
        html_content = generate_cv_html(worker_data, experience_data, education_list)
        logger.info("CV generated using template")

    # Save HTML
    html_path = cv_dir / f"{cv_name}.html"
    html_path.write_text(html_content, encoding='utf-8')

    # Save TXT (always use template for text version)
    txt_path = cv_dir / f"{cv_name}.txt"
    # Handle education_data for text generation
    if education_data is None:
        txt_education = None
    elif isinstance(education_data, dict):
        txt_education = education_data
    else:
        txt_education = education_data[0] if education_data else None  # Use first for text version
    txt_content = generate_cv_text(worker_data, experience_data, txt_education)
    txt_path.write_text(txt_content, encoding='utf-8')

    # Generate and save PDF - MUST succeed
    pdf_path = cv_dir / f"{cv_name}.pdf"
    pdf_success = html_to_pdf(html_content, pdf_path)

    # If PDF generation failed, retry once (Playwright then xhtml2pdf again)
    if not pdf_success:
        logger.warning("First PDF generation attempt failed, retrying...")
        pdf_success = html_to_pdf(html_content, pdf_path)
        if pdf_success:
            logger.info("PDF generated successfully on retry")

    # Always return PDF path - if generation failed, raise exception
    if pdf_success:
        # Also create name-based files for easier lookup (used by preview/download endpoints)
        try:
            name = (worker_data.get("name") or "").strip()
            if name:
                safe_name = "".join(c if c.isalnum() or c.isspace() else "" for c in name)
                safe_name = "_".join(safe_name.split()).strip("_")
                if safe_name:
                    name_based_html = cv_dir / f"{safe_name}_Resume.html"
                    name_based_pdf = cv_dir / f"{safe_name}_Resume.pdf"
                    # Copy timestamped files to name-based files
                    shutil.copy2(html_path, name_based_html)
                    shutil.copy2(pdf_path, name_based_pdf)

                    os.environ[worker_id] = str(name_based_pdf)
                    logger.info(f"Created name-based CV files: {safe_name}_Resume.html/pdf")
        except Exception as e:
            logger.warning(f"Failed to create name-based CV files: {e}")
            # Don't fail - timestamped files are sufficient

        logger.info(f"CV saved successfully for worker {worker_id}: HTML={html_path.name}, PDF={pdf_path.name}")

        # Mark CV as generated in database (NEW: CV status tracking)
        try:
            from ..db import crud
            crud.mark_cv_generated(worker_id)
            logger.info(f"CV status updated in database for worker {worker_id}")
        except Exception as e:
            logger.warning(f"Failed to update cv_status for {worker_id}: {e}")
            # Don't fail CV generation if status update fails

        return str(pdf_path)
    else:
        # If PDF generation completely failed, this is a critical error
        logger.error("PDF generation failed completely. xhtml2pdf may not be installed correctly.")
        raise Exception("PDF generation failed. Please ensure xhtml2pdf is installed: pip install xhtml2pdf")
