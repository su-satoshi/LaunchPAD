"""
Claude-powered AI agent for job matching, email drafting, and resume analysis.
Uses claude-sonnet-4-6 with prompt caching for efficiency.
"""
import json
import logging
import os
import re
from typing import Optional
from dotenv import dotenv_values
import anthropic

# Load environment variables from .env file
env_vars = dotenv_values()
api_key = env_vars.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
logger = logging.getLogger(__name__)

client = anthropic.Anthropic(
    api_key=api_key,
    timeout=anthropic.Timeout(90.0, connect=10.0),  # 90s per call, 10s connect
)
MODEL = "claude-sonnet-4-6"


def analyze_resume(resume_text: str) -> dict:
    """Extract structured data from resume text."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system="You are an expert resume parser. Extract structured information from resumes.",
        messages=[
            {
                "role": "user",
                "content": f"""Parse this resume and return a JSON object with these fields:
- name (string)
- email (string)
- phone (string)
- location (string)
- skills (list of strings)
- years_experience (integer)
- education (list of {{degree, institution, year}})
- work_history (list of {{title, company, start_date, end_date, description}})
- summary (2-3 sentence professional summary)
- top_strengths (list of 5 key strengths)

Resume:
{resume_text}

Return only valid JSON, no markdown.""",
            }
        ],
    )
    try:
        text = response.content[0].text.strip()
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        return json.loads(text)
    except Exception as e:
        logger.error(f"Resume parse error: {e}")
        return {}


def match_job_to_resume(
    job: dict,
    resume_text: str,
    user_skills: list[str],
    user_preferences: dict,
) -> dict:
    """
    Score a job against the candidate's resume and preferences.
    Returns: {score, reasons, skills_matched, skills_missing, recommendation}
    Uses prompt caching on the resume text for efficiency.
    """
    pref_summary = json.dumps({
        "titles": user_preferences.get("job_titles", []),
        "keywords": user_preferences.get("keywords", []),
        "exclude": user_preferences.get("exclude_keywords", []),
        "locations": user_preferences.get("locations", []),
        "remote_only": user_preferences.get("remote_only", False),
        "min_salary": user_preferences.get("min_salary"),
        "job_types": user_preferences.get("job_types", []),
        "experience_levels": user_preferences.get("experience_levels", []),
    }, indent=2)

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": "You are an expert job-matching AI that scores job fit with precision.",
            },
            {
                "type": "text",
                "text": f"CANDIDATE RESUME:\n{resume_text}\n\nCANDIDATE SKILLS: {', '.join(user_skills)}\n\nJOB PREFERENCES:\n{pref_summary}",
                "cache_control": {"type": "ephemeral"},
            },
        ],
        messages=[
            {
                "role": "user",
                "content": f"""Score this job for the candidate. Return JSON only.

JOB:
Title: {job.get('title')}
Company: {job.get('company')}
Location: {job.get('location')}
Type: {job.get('job_type')}
Remote: {job.get('remote')}
Description: {(job.get('description') or '')[:2000]}

Return this exact JSON structure:
{{
  "score": 0.0-1.0,
  "recommendation": "apply" | "skip" | "review",
  "reasons": ["reason1", "reason2"],
  "skills_matched": ["skill1", "skill2"],
  "skills_missing": ["skill1", "skill2"],
  "fit_summary": "one sentence summary of fit",
  "red_flags": ["any concerns"],
  "salary_assessment": "comment on salary if visible"
}}

Score 0.9+ = excellent match. 0.7-0.9 = good. 0.5-0.7 = moderate. Below 0.5 = poor.
Penalise heavily for excluded keywords. Penalise if remote-only preference not met.""",
            }
        ],
    )
    try:
        text = response.content[0].text.strip()
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        return json.loads(text)
    except Exception as e:
        logger.error(f"Job match error: {e}")
        return {"score": 0.0, "recommendation": "skip", "reasons": [], "skills_matched": [], "skills_missing": []}


def batch_match_jobs(
    jobs: list[dict],
    resume_text: str,
    user_skills: list[str],
    user_preferences: dict,
    visa_status: str = "",
    work_rights: str = "",
) -> list[dict]:
    """
    Score up to 10 jobs in a single Claude call.
    Returns list of match dicts in the same order as input jobs.
    Falls back to empty score on parse error.
    """
    experience_levels = user_preferences.get("experience_levels", [])
    exclude_keywords  = user_preferences.get("exclude_keywords", [])
    locations         = user_preferences.get("locations", [])

    # Build a rich preference summary for more accurate scoring
    pref_lines = [
        f"Target job titles: {', '.join(user_preferences.get('job_titles', []) or ['any'])}",
        f"Must-have keywords: {', '.join(user_preferences.get('keywords', []) or [])}",
        f"Exclude keywords (auto-reject if present): {', '.join(exclude_keywords or [])}",
        f"Preferred locations: {', '.join(locations or [])}",
        f"Remote only: {user_preferences.get('remote_only', False)}",
        f"Seniority targets: {', '.join(experience_levels) if experience_levels else 'any level'}",
        f"Job types: {', '.join(user_preferences.get('job_types', []) or ['any'])}",
        f"Min salary: {user_preferences.get('min_salary') or 'no minimum'}",
    ]
    if visa_status:
        pref_lines.append(f"Visa status: {visa_status}")
    if work_rights:
        pref_lines.append(f"Work rights: {work_rights}")

    pref_summary = "\n".join(f"• {l}" for l in pref_lines)

    # Build scoring guidance for seniority
    seniority_guidance = ""
    if experience_levels:
        lvl_map = {
            "intern": "internship, graduate, student",
            "entry":  "entry level, junior, associate, 0-2 years",
            "mid":    "mid level, 2-5 years, software engineer II",
            "senior": "senior, 5+ years, sr. engineer",
            "lead":   "lead, staff, principal, tech lead",
            "manager":"manager, EM, engineering manager, director",
        }
        wanted_terms = [lvl_map.get(l, l) for l in experience_levels]
        seniority_guidance = (
            f"SENIORITY: Target levels are [{', '.join(experience_levels)}]. "
            f"Penalise roles that explicitly require seniority outside this range. "
            f"Reward roles matching: {'; '.join(wanted_terms)}."
        )

    jobs_text = ""
    for i, job in enumerate(jobs):
        jobs_text += f"""
JOB {i}:
  Title: {job.get('title')}
  Company: {job.get('company')}
  Location: {job.get('location')} | Remote: {job.get('remote')}
  Type: {job.get('job_type') or 'not specified'}
  Salary: {job.get('salary_min') or '?'} – {job.get('salary_max') or '?'} {job.get('salary_currency') or ''}
  Description: {(job.get('description') or '')[:900]}
"""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": (
                        "You are an expert job-matching AI. Score each job against the candidate's profile "
                        "with high precision. Consider skills match, seniority fit, location preference, "
                        "visa work rights, salary alignment, and excluded keywords."
                    ),
                },
                {
                    "type": "text",
                    "text": (
                        f"CANDIDATE RESUME:\n{resume_text}\n\n"
                        f"CANDIDATE SKILLS: {', '.join(user_skills or [])}\n\n"
                        f"CANDIDATE PREFERENCES:\n{pref_summary}\n\n"
                        + (f"{seniority_guidance}\n\n" if seniority_guidance else "")
                        + "SCORING RULES:\n"
                        "• Score 0.9-1.0: Strong skill match, right seniority, right location, no red flags\n"
                        "• Score 0.7-0.89: Good match with minor gaps\n"
                        "• Score 0.5-0.69: Moderate — missing some skills or slight seniority mismatch\n"
                        "• Score <0.5: Poor match, major gaps, or excluded keywords found\n"
                        "• AUTO-SKIP (score 0.1): Job contains any excluded keyword\n"
                        "• AUTO-SKIP (score 0.1): Job requires visa sponsorship and candidate has full rights (or vice-versa if noted)\n"
                        "• LOCATION: Penalise jobs in wrong country if location preference is strict"
                    ),
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages=[
                {
                    "role": "user",
                    "content": f"""Score each of the following {len(jobs)} jobs for this candidate.

{jobs_text}

Return a JSON array of exactly {len(jobs)} objects (index 0 to {len(jobs)-1}), one per job, in order:
[
  {{
    "score": 0.0-1.0,
    "recommendation": "apply"|"skip"|"review",
    "reasons": ["concise reason 1", "concise reason 2"],
    "skills_matched": ["skill1", "skill2"],
    "skills_missing": ["skill1"],
    "fit_summary": "one sentence describing fit",
    "seniority_match": true|false
  }},
  ...
]

Return ONLY the JSON array, no markdown, no commentary.""",
                }
            ],
        )
        text = response.content[0].text.strip()
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        results = json.loads(text)
        if not isinstance(results, list):
            raise ValueError("Expected list")
        # Pad or trim to match input length
        while len(results) < len(jobs):
            results.append({"score": 0.0, "recommendation": "skip", "reasons": [], "skills_matched": [], "skills_missing": []})
        return results[:len(jobs)]
    except Exception as e:
        logger.error(f"Batch match error: {e}")
        return [{"score": 0.0, "recommendation": "skip", "reasons": [], "skills_matched": [], "skills_missing": []} for _ in jobs]


def draft_application_email(
    job: dict,
    resume_text: str,
    user_profile: dict,
    email_type: str = "application",
    recipient_name: Optional[str] = None,
    additional_context: Optional[str] = None,
) -> dict:
    """
    Draft a personalised job application or referral request email.
    Returns: {subject, body, to_address, to_name}
    Uses prompt caching on resume for efficiency.
    """
    type_instructions = {
        "application": "Write a compelling job application email with a cover letter tone. Be specific about the role and company.",
        "referral_request": f"Write a concise, professional referral request to {recipient_name or 'a contact'} asking if they can refer the candidate for this role.",
        "cold_email": "Write a cold outreach email to a hiring manager expressing interest in working at this company.",
        "follow_up": "Write a polite follow-up email checking on the status of a job application sent 1 week ago.",
    }

    instructions = type_instructions.get(email_type, type_instructions["application"])
    context_block = f"\nAdditional context: {additional_context}" if additional_context else ""

    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=[
            {
                "type": "text",
                "text": "You are an expert job application email writer who crafts compelling, personalised emails.",
            },
            {
                "type": "text",
                "text": f"""CANDIDATE PROFILE:
Name: {user_profile.get('name', 'Candidate')}
Email: {user_profile.get('email', '')}
Phone: {user_profile.get('phone', '')}
LinkedIn: {user_profile.get('linkedin_url', '')}
GitHub: {user_profile.get('github_url', '')}
Portfolio: {user_profile.get('portfolio_url', '')}

RESUME SUMMARY:
{resume_text[:3000]}""",
                "cache_control": {"type": "ephemeral"},
            },
        ],
        messages=[
            {
                "role": "user",
                "content": f"""{instructions}{context_block}

JOB DETAILS:
Title: {job.get('title')}
Company: {job.get('company')}
Location: {job.get('location')}
URL: {job.get('url')}
Description excerpt: {(job.get('description') or '')[:1500]}

Return JSON only:
{{
  "subject": "email subject line",
  "body": "full email body with proper formatting",
  "suggested_to_address": "hr@company.com or empty string if unknown",
  "suggested_to_name": "Hiring Manager or specific name if known",
  "key_points_made": ["point1", "point2"]
}}""",
            }
        ],
    )
    try:
        text = response.content[0].text.strip()
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        return json.loads(text)
    except Exception as e:
        logger.error(f"Email draft error: {e}")
        return {
            "subject": f"Application for {job.get('title')} at {job.get('company')}",
            "body": f"Dear Hiring Manager,\n\nI am writing to express my interest in the {job.get('title')} position at {job.get('company')}.\n\nBest regards,\n{user_profile.get('name', '')}",
            "suggested_to_address": "",
            "suggested_to_name": "Hiring Manager",
        }


def find_company_email(company: str, job_title: str) -> dict:
    """Use Claude to suggest likely HR/recruiter email formats and contacts."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system="You are a recruiter research assistant. Suggest email contacts for job applications.",
        messages=[
            {
                "role": "user",
                "content": f"""For a {job_title} application at {company}, suggest:
1. The most likely HR/recruiting email address format
2. LinkedIn search terms to find the hiring manager
3. Any known careers email (e.g. careers@company.com)

Return JSON:
{{
  "likely_email": "careers@company.com",
  "email_formats": ["firstname@company.com", "firstname.lastname@company.com"],
  "linkedin_search": "search query to find hiring manager",
  "confidence": "high|medium|low"
}}""",
            }
        ],
    )
    try:
        text = response.content[0].text.strip()
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        return json.loads(text)
    except Exception:
        return {"likely_email": f"careers@{company.lower().replace(' ', '')}.com", "confidence": "low"}


def generate_daily_summary(stats: dict, top_jobs: list[dict]) -> str:
    """Generate a human-readable daily summary of the agent's activity."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=600,
        system="You are a helpful job search assistant writing a brief daily activity report.",
        messages=[
            {
                "role": "user",
                "content": f"""Write a concise daily job search summary (3-4 sentences) based on:

Stats: {json.dumps(stats, indent=2)}

Top matched jobs today:
{json.dumps([{{k: j.get(k) for k in ['title', 'company', 'match_score', 'source']}} for j in top_jobs[:5]], indent=2)}

Mention highlights, good matches, and any actions needed from the user.""",
            }
        ],
    )
    return response.content[0].text.strip()
