"""Conversational profile extraction.

Primary path is deterministic rules (reliable, offline, testable):
  - skill mention matching against the catalogue (with synonyms)
  - weekly-hours and deadline regexes
  - target-role detection from a keyword map
  - experience-level and preference keywords

If a real LLM provider is configured, the same input is also parsed with
a structured-JSON prompt and merged when the result passes validation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app import config
from app.ai.llm import get_llm_provider
from app.ai.prompts import PROFILE_EXTRACTION_SYSTEM, PROFILE_EXTRACTION_USER
from app.data.loader import DataCatalog
from app.utils import get_logger, safe_float, safe_int

log = get_logger("extraction")

# ------------------------------------------------------------------
# Static maps
# ------------------------------------------------------------------
ROLE_KEYWORDS: list[tuple[str, str]] = [
    ("machine learning engineer", "ml_engineer"),
    ("ml engineer", "ml_engineer"),
    ("ml engineering", "ml_engineer"),
    ("ai engineer", "ai_engineer"),
    ("ai engineering", "ai_engineer"),
    ("artificial intelligence engineer", "ai_engineer"),
    ("data scientist", "data_scientist"),
    ("data science", "data_scientist"),
    ("data analyst", "data_analyst"),
    ("data analytics", "data_analyst"),
    ("cybersecurity analyst", "cybersecurity_analyst"),
    ("cyber security analyst", "cybersecurity_analyst"),
    ("security analyst", "cybersecurity_analyst"),
    ("soc analyst", "cybersecurity_analyst"),
    ("penetration tester", "penetration_tester"),
    ("pen tester", "penetration_tester"),
    ("ethical hacker", "penetration_tester"),
    ("cloud engineer", "cloud_engineer"),
    ("cloud engineering", "cloud_engineer"),
    ("devops engineer", "devops_engineer"),
    ("devops", "devops_engineer"),
    ("software engineer", "software_engineer"),
    ("software developer", "software_engineer"),
    ("web developer", "web_developer"),
    ("web development", "web_developer"),
    ("frontend developer", "web_developer"),
]

SKILL_SYNONYMS: dict[str, list[str]] = {
    "python": ["python", "py"],
    "ml_fundamentals": ["machine learning", "ml basics", "basic ml", "ml fundamentals", "machine-learning"],
    "deep_learning": ["deep learning", "neural networks", "dl"],
    "statistics": ["statistics", "stats", "statistical"],
    "pandas": ["pandas"],
    "numpy": ["numpy"],
    "sql": ["sql", "databases"],
    "data_viz": ["data visualization", "visualization", "matplotlib", "seaborn", "charts", "plotly"],
    "data_cleaning": ["data cleaning", "data wrangling", "data preprocessing"],
    "docker": ["docker", "containers"],
    "kubernetes": ["kubernetes", "k8s"],
    "cloud": ["cloud", "aws", "azure", "gcp"],
    "linux": ["linux", "unix"],
    "networking": ["networking", "network"],
    "security_fundamentals": ["cybersecurity", "cyber security", "security basics", "information security"],
    "web_security": ["web security", "owasp", "hacking web"],
    "pen_testing": ["penetration testing", "pen testing", "ethical hacking"],
    "javascript": ["javascript", "js"],
    "react": ["react"],
    "html_css": ["html", "css", "web design", "frontend"],
    "git": ["git", "github", "version control"],
    "fastapi": ["fastapi", "apis", "api development"],
    "mlops": ["mlops", "ml ops", "model deployment", "deployment of models"],
    "excel": ["excel", "spreadsheets"],
    "powerbi": ["power bi", "tableau", "dashboards"],
    "nlp": ["nlp", "natural language processing"],
    "transform_models": ["llm", "llms", "transformers", "chatgpt", "langchain", "rag"],
    "probability": ["probability"],
    "linalg": ["linear algebra"],
    "cicd": ["ci/cd", "github actions", "pipelines"],
    "terraform": ["terraform", "infrastructure as code"],
    "aws": ["aws"],
    "bash": ["bash", "shell scripting", "shell"],
    "node": ["node", "node.js", "backend"],
}

EXPERIENCE_KEYWORDS = {
    "advanced": ["senior", "experienced", "advanced", "expert", "years of"],
    "intermediate": ["intermediate", "third-year", "third year", "junior", "some experience", "have worked"],
    "beginner": ["beginner", "new to", "start learning", "student", "no experience", "basics", "just started"],
}

PREFERENCE_KEYWORDS: list[tuple[list[str], str]] = [
    (["hands-on", "practical", "projects", "project-based", "build"], "hands-on"),
    (["video", "watch", "youtube", "courses"], "video"),
    (["reading", "read", "books", "documentation", "theory"], "reading"),
    (["interactive", "labs", "lab", "practice", "exercises", "coding"], "interactive"),
]

MONTHS_TO_WEEKS = {
    "one": 4, "two": 9, "three": 13, "four": 17, "five": 22, "six": 26,
    "seven": 30, "eight": 35, "nine": 39, "ten": 43, "eleven": 48, "twelve": 52,
}

_WORD_TO_NUMBER = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}


@dataclass
class ExtractedProfile:
    goal: str = ""
    target_role: str = ""
    experience_level: str = "beginner"
    skills: list[tuple[str, float]] = field(default_factory=list)   # (skill_id, confidence)
    strengths: list[str] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)
    weekly_hours: float = 0.0
    deadline_weeks: int = 0
    raw_text: str = ""
    extraction_source: str = "rules"
    confidence: float = 0.7

    def as_dict(self) -> dict:
        return {
            "goal": self.goal,
            "target_role": self.target_role,
            "experience_level": self.experience_level,
            "skills": [(s, round(c, 2)) for s, c in self.skills],
            "strengths": self.strengths,
            "interests": self.interests,
            "preferences": self.preferences,
            "weekly_hours": self.weekly_hours,
            "deadline_weeks": self.deadline_weeks,
            "extraction_source": self.extraction_source,
            "confidence": round(self.confidence, 2),
        }


# ------------------------------------------------------------------
# Rule-based extraction
# ------------------------------------------------------------------
def _extract_weekly_hours(text: str) -> float:
    patterns = [
        r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\s*(?:per|a|each|every)\s*(?:week|wk)",
        r"(\d+(?:\.\d+)?)\s*h\s*/\s*week",
        r"(\d+(?:\.\d+)?)\s*hours?/week",
        r"(?:about|around|approximately)\s*(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)",
        r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)\s*(?:per|a)\s*(?:day|week)",
    ]
    for pat in patterns:
        m = re.search(pat, text.lower())
        if m:
            v = safe_float(m.group(1), 0.0)
            if "day" in pat:
                v *= 7
            return min(v, config.MAX_WEEKLY_HOURS)
    return 0.0


def _extract_deadline_weeks(text: str) -> int:
    t = text.lower()
    # months or years, numeric or written-out
    m = re.search(
        r"(?:(?:within|in|about|around)\s+)?(?:the\s+next\s+)?"
        r"(?:(\d+)|(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve))"
        r"\s*(months?|years?)",
        t,
    )
    if m:
        num, word, unit = m.group(1), m.group(2), m.group(3)
        if unit.startswith("year"):
            value = safe_int(num, 0) if num else _WORD_TO_NUMBER.get(word, 1)
            return min(104, value * 52)
        # months
        if num:
            return min(104, safe_int(num, 0) * 4)
        return min(104, MONTHS_TO_WEEKS.get(word, 26))
    m = re.search(r"(\d+)\s*weeks?", t)
    if m:
        return min(104, safe_int(m.group(1), 0))
    return 0


def _detect_role(text: str, catalog: DataCatalog | None) -> str:
    t = text.lower()
    for phrase, role_id in ROLE_KEYWORDS:
        if phrase in t:
            return role_id
    if catalog is not None:
        # fall back: role title mentioned anywhere in the catalogue
        for role in catalog.roles.values():
            if role.title.lower() in t:
                return role.role_id
    return ""


def _detect_experience(text: str) -> str:
    t = text.lower()
    for level, keywords in EXPERIENCE_KEYWORDS.items():
        if any(k in t for k in keywords):
            return level
    return "beginner"


def _detect_preferences(text: str) -> list[str]:
    t = text.lower()
    prefs: list[str] = []
    for keywords, pref in PREFERENCE_KEYWORDS:
        if any(k in t for k in keywords) and pref not in prefs:
            prefs.append(pref)
    if not prefs:
        prefs = ["hands-on"]
    return prefs


def _detect_skills(text: str, catalog: DataCatalog) -> list[tuple[str, float]]:
    """Find catalogue skills mentioned in the text, with a confidence score."""
    t = text.lower()
    found: dict[str, float] = {}
    for skill_id, synonyms in SKILL_SYNONYMS.items():
        for syn in synonyms:
            if syn in t:
                # confidence by modifier context
                conf = 0.55
                if re.search(rf"\b(know|comfortable with|good at|strong|proficient|expert)\b[^.]*?\b{re.escape(syn)}\b", t) or \
                   re.search(rf"\b{re.escape(syn)}\b[^.]*?\b(know|comfortable|good at|strong|proficient)\b", t):
                    conf = 0.8
                elif re.search(rf"\b(basic|some|beginner|little|fundamentals of)\b[^.]*?\b{re.escape(syn)}\b", t):
                    conf = 0.35
                if conf > found.get(skill_id, 0):
                    found[skill_id] = conf
                break
    # also direct catalogue name match
    for skill in catalog.skills.values():
        if skill.name.lower() in t and skill.skill_id not in found:
            found[skill.skill_id] = 0.5
    return sorted(found.items(), key=lambda kv: -kv[1])


def extract_profile(text: str, catalog: DataCatalog) -> ExtractedProfile:
    """Rule-based extraction (always runs, always safe)."""
    text = text.strip()
    prof = ExtractedProfile(
        goal=text[:300],
        target_role=_detect_role(text, catalog),
        experience_level=_detect_experience(text),
        skills=_detect_skills(text, catalog),
        preferences=_detect_preferences(text),
        weekly_hours=_extract_weekly_hours(text),
        deadline_weeks=_extract_deadline_weeks(text),
        raw_text=text,
        extraction_source="rules",
    )
    prof.strengths = [s for s, c in prof.skills if c >= 0.7]
    if not prof.goal:
        prof.goal = text
    return prof


def merge_llm_extraction(base: ExtractedProfile, llm_json: dict | None) -> ExtractedProfile:
    """Merge validated LLM output over the rule-based result."""
    if not llm_json:
        return base
    result = base
    try:
        if isinstance(llm_json.get("target_role"), str) and llm_json["target_role"] in result_target_ids():
            result.target_role = llm_json["target_role"]
        if llm_json.get("experience_level") in ("beginner", "intermediate", "advanced"):
            result.experience_level = llm_json["experience_level"]
        if isinstance(llm_json.get("weekly_hours"), (int, float)) and llm_json["weekly_hours"] > 0:
            result.weekly_hours = safe_float(llm_json["weekly_hours"], result.weekly_hours, 1, config.MAX_WEEKLY_HOURS)
        if isinstance(llm_json.get("deadline_weeks"), (int, float)) and llm_json["deadline_weeks"] > 0:
            result.deadline_weeks = safe_int(llm_json["deadline_weeks"], result.deadline_weeks, 1, 104)
        if isinstance(llm_json.get("goal"), str) and len(llm_json["goal"]) > 5:
            result.goal = llm_json["goal"][:300]
        llm_skills = llm_json.get("skills")
        if isinstance(llm_skills, list) and llm_skills:
            merged = {s: c for s, c in result.skills}
            for entry in llm_skills:
                if isinstance(entry, dict) and isinstance(entry.get("skill_id"), str):
                    merged[entry["skill_id"]] = safe_float(entry.get("confidence"), 0.5, 0, 1)
            result.skills = sorted(merged.items(), key=lambda kv: -kv[1])
            result.strengths = [s for s, c in result.skills if c >= 0.7]
        result.extraction_source = "rules+llm"
        result.confidence = 0.9
    except Exception as exc:  # noqa: BLE001 - never let LLM parsing break onboarding
        log.warning("llm merge failed, keeping rule-based profile: %s", exc)
    return result


def result_target_ids() -> set[str]:
    from app.data.loader import get_catalog

    return set(get_catalog().roles.keys())


def extract_profile_hybrid(text: str, catalog: DataCatalog) -> ExtractedProfile:
    """Rule-based extraction upgraded with the LLM when available/valid."""
    base = extract_profile(text, catalog)
    provider = get_llm_provider()
    if provider.available() and provider.name != "local":
        try:
            llm_json = provider.complete_json(
                PROFILE_EXTRACTION_SYSTEM.format(roles=", ".join(result_target_ids())),
                PROFILE_EXTRACTION_USER.format(learner_message=text),
            )
            return merge_llm_extraction(base, llm_json)
        except Exception as exc:  # noqa: BLE001
            log.warning("profile extraction LLM path failed: %s", exc)
    return base
