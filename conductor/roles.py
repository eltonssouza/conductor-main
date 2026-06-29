"""The 36-role registry: each role's matching skill, area, and the project types
it is selected for.

`cdt init` uses this to pick a relevant subset of roles for a project
and to resolve each role to its Agent template (`templates/agents/<role>.md`) and
Skill template (`templates/skills/<skill>/SKILL.md`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set


@dataclass(frozen=True)
class Role:
    slug: str        # agent template slug (templates/agents/<slug>.md)
    skill: str       # matching skill slug (templates/skills/<skill>/SKILL.md)
    area: str


# role -> matching skill (1:1) + area. Derived from the flow's gate pairings.
ROLES: Dict[str, Role] = {r.slug: r for r in [
    # Management / Product
    Role("product-manager", "product-discovery", "product"),
    Role("product-owner", "refine-backlog", "product"),
    Role("technical-program-manager", "plan-program", "product"),
    Role("engineering-manager", "team-diagnosis", "product"),
    Role("business-analyst", "map-requirements", "product"),
    Role("scrum-master", "facilitate-retro", "product"),
    Role("agile-coach", "agile-diagnosis", "product"),
    Role("cto", "technology-strategy", "product"),
    Role("vp-engineering", "scale-organization", "product"),
    # Engineering
    Role("software-engineer", "implement-feature-tdd", "engineering"),
    Role("tech-lead", "drive-technical-decision", "engineering"),
    Role("frontend-engineer", "build-ui-component", "engineering"),
    Role("backend-engineer", "design-service", "engineering"),
    Role("fullstack-engineer", "deliver-vertical-feature", "engineering"),
    Role("staff-engineer", "lead-technical-initiative", "engineering"),
    Role("principal-engineer", "define-technical-direction", "engineering"),
    # Architecture
    Role("software-architect", "decide-architecture", "architecture"),
    Role("solutions-architect", "design-solution", "architecture"),
    Role("enterprise-architect", "map-enterprise-architecture", "architecture"),
    # Data / AI
    Role("database-administrator", "optimize-database", "data"),
    Role("data-engineer", "build-data-pipeline", "data"),
    Role("data-scientist", "predictive-analysis", "data"),
    Role("machine-learning-engineer", "productionize-model", "data"),
    Role("ai-engineer", "design-llm-system", "data"),
    # Ops / Infra
    Role("site-reliability-engineer", "service-reliability", "ops"),
    Role("devops-engineer", "build-cicd-pipeline", "ops"),
    Role("platform-engineer", "build-platform-capability", "ops"),
    # Quality
    Role("quality-assurance", "test-strategy", "quality"),
    Role("sdet", "automate-tests", "quality"),
    # Security / Privacy
    Role("security-engineer", "model-threats", "security"),
    Role("application-security-engineer", "review-app-security", "security"),
    Role("ciso", "security-program", "security"),
    Role("data-protection-officer", "assess-privacy", "security"),
    # Design / UX
    Role("ux-designer", "design-ux-flow", "design"),
    Role("ux-researcher", "conduct-ux-research", "design"),
    Role("ui-designer", "design-visual-interface", "design"),
]}

PROJECT_TYPES = ("backend", "frontend", "mobile", "fullstack", "library",
                 "data", "unknown")

# Always included, regardless of type — the spine of the 12-gate flow.
CORE: List[str] = [
    "product-owner", "business-analyst", "software-architect",
    "software-engineer", "tech-lead", "quality-assurance",
    "security-engineer", "devops-engineer",
]

# Extra roles by detected project type (added to CORE).
TYPE_EXTRA: Dict[str, List[str]] = {
    "frontend": ["product-manager", "frontend-engineer", "ux-designer",
                 "ui-designer", "ux-researcher", "sdet"],
    "backend": ["product-manager", "backend-engineer", "solutions-architect",
                "database-administrator", "application-security-engineer",
                "site-reliability-engineer", "sdet"],
    "mobile": ["product-manager", "frontend-engineer", "ui-designer",
               "ux-designer", "ux-researcher", "backend-engineer", "sdet"],
    "data": ["data-engineer", "data-scientist", "machine-learning-engineer",
             "ai-engineer", "database-administrator", "solutions-architect"],
    "library": ["staff-engineer", "principal-engineer", "solutions-architect",
                "sdet"],
    "unknown": [],
}
TYPE_EXTRA["fullstack"] = sorted(set(TYPE_EXTRA["frontend"]) | set(TYPE_EXTRA["backend"]))


def select_roles(ptype: str, *, all_roles: bool = False,
                 override: Optional[List[str]] = None) -> List[str]:
    """Returns the role slugs to scaffold for a project type.

    all_roles -> all 36; override -> exactly those (validated); else CORE + the
    type's extras.
    """
    if override:
        unknown = [r for r in override if r not in ROLES]
        if unknown:
            raise ValueError(f"unknown role(s): {', '.join(unknown)}")
        chosen: Set[str] = set(override)
    elif all_roles:
        chosen = set(ROLES)
    else:
        chosen = set(CORE) | set(TYPE_EXTRA.get(ptype, []))
    return sorted(chosen)


def skill_for(role: str) -> str:
    return ROLES[role].skill
