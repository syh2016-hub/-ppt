"""Offline English outline planner used by the built-in AI."""
from __future__ import annotations

import re
from typing import Any

from .config import MAX_SLIDES, MIN_SLIDES
from .utils import clean_text


def english_topic(prompt: str) -> str:
    text = re.sub(r"\s+", " ", (prompt or "").strip())
    text = re.sub(
        r"^(please\s+)?(create|make|build|generate|design)\s+(a|an)?\s*(presentation|deck|slides?|courseware|lesson)\s*(about|on|for)?\s*",
        "",
        text,
        flags=re.I,
    )
    text = re.split(r"[.。!?]\s*", text)[0].strip()
    return clean_text(text, 78) or "A Practical Presentation"


def local_outline_en(
    prompt: str,
    *,
    target_slides: int = 10,
    audience: str = "",
    include_agenda: bool = True,
    include_summary: bool = True,
    include_qa: bool = True,
) -> dict[str, Any]:
    target = max(MIN_SLIDES, min(MAX_SLIDES, int(target_slides or 10)))
    topic = english_topic(prompt)
    resolved_audience = clean_text(audience, 60) or "a general audience"
    section_defs = [
        ("Context", "WHY NOW", "The situation, the audience, and why this topic matters now."),
        ("The Shift", "CHANGE", "The forces changing the game and the bottleneck that remains."),
        ("Framework", "METHOD", "A practical way to turn the idea into a repeatable approach."),
        ("Evidence", "PROOF", "A small pilot, success signals, and what the data should show."),
        ("Roadmap", "ACTION", "A 90-day path from first step to measurable progress."),
        ("Risks", "GUARDRAILS", "Failure modes, boundaries, and how to stop safely."),
    ]
    if target < 8:
        section_count = 1
    elif target < 12:
        section_count = 2
    elif target < 20:
        section_count = 3
    elif target < 30:
        section_count = 4
    elif target < 40:
        section_count = 5
    else:
        section_count = 6
    agenda_on = bool(include_agenda and target >= 8)
    summary_on = bool(include_summary and target >= 6)
    stats_on = target >= 10
    quote_on = target >= 12
    while True:
        fixed = 1 + int(agenda_on) + section_count + int(stats_on) + int(quote_on) + int(summary_on) + 1
        content_count = target - fixed
        if content_count >= section_count:
            break
        if quote_on:
            quote_on = False
            continue
        if stats_on:
            stats_on = False
            continue
        if agenda_on:
            agenda_on = False
            continue
        if section_count > 1:
            section_count -= 1
            continue
        break
    sections = section_defs[:section_count]
    content_count = max(section_count, target - (1 + int(agenda_on) + section_count + int(stats_on) + int(quote_on) + int(summary_on) + 1))
    counts = [content_count // section_count] * section_count
    for index in range(content_count % section_count):
        counts[index] += 1

    patterns = [
        ("What the audience is seeing now", [
            f"Signal: {resolved_audience} is being asked to do more with less.",
            "The tools are better, but the workflow has not caught up.",
            "The gap is no longer access; it is translation into daily practice.",
            "The opportunity is a small, measurable first step.",
        ]),
        ("The real constraint", [
            "The bottleneck is not information; it is decision-making.",
            "Teams need one shared definition of success before tools.",
            "A pilot without a baseline cannot prove progress.",
            "Focus beats breadth in the first 90 days.",
        ]),
        ("A practical framework", [
            "Define the problem in one sentence.",
            "Choose one high-frequency use case.",
            "Run a two-week pilot with a clear baseline.",
            "Turn what works into a repeatable template.",
        ]),
        ("What good looks like", [
            "People can explain the change in plain language.",
            "The workflow is shorter, not just more digital.",
            "The first result is visible within one month.",
            "The team can continue without outside help.",
        ]),
        ("A small pilot", [
            "Pick a real audience and a real deadline.",
            "Measure the current baseline before changing anything.",
            "Change one variable and keep the rest stable.",
            "Decide to scale, adjust, or stop with evidence.",
        ]),
        ("Metrics that matter", [
            "Outcome: a result the audience can feel.",
            "Process: a behavior that can be repeated.",
            "Experience: whether people want to use it again.",
            "Guardrail: a metric that catches unintended harm.",
        ]),
        ("Risks and guardrails", [
            "Risk: a tool rollout without a process owner.",
            "Risk: a pilot that cannot be measured.",
            "Guardrail: keep a rollback path at every stage.",
            "Rule: stop, learn, and redesign when the data says so.",
        ]),
    ]

    def bullets_for(section_index: int, variant: int) -> tuple[str, list[str], str]:
        sec = sections[section_index]
        pattern_title, pattern_bullets = patterns[variant % len(patterns)]
        title = f"{sec[0]}: {pattern_title}"
        bullets = [
            pattern_bullets[0],
            pattern_bullets[1],
            f"Applied to {sec[0].lower()}: {sec[2]}",
            pattern_bullets[3],
        ]
        return title, bullets[:4], f"We will look at {sec[0]} through this lens: {sec[2]} Keep the focus on what the audience can do differently after this slide."

    slides: list[dict[str, Any]] = []
    slides.append({
        "type": "cover", "eyebrow": "2026 · PRESENTATION", "title": topic,
        "subtitle": "A clear narrative, a practical framework, and next steps.",
        "bullets": [], "stats": [], "quote": "", "author": "",
        "notes": f"Good morning. Today we are going to look at {topic}, with a focus on practical decisions rather than abstract ideas.",
        "section": 0,
    })
    if agenda_on:
        slides.append({
            "type": "agenda", "eyebrow": "CONTENTS", "title": "What we will cover",
            "subtitle": "From context to a measurable next step.",
            "bullets": [f"{i+1:02d}  {sec[0]} · {sec[2]}" for i, sec in enumerate(sections)],
            "stats": [], "quote": "", "author": "",
            "notes": f"We will move through {len(sections)} chapters, each ending with one decision or action.",
            "section": 0,
        })
    for section_index, sec in enumerate(sections):
        slides.append({
            "type": "section", "eyebrow": f"SECTION {section_index+1:02d} · {sec[1]}",
            "title": sec[0], "subtitle": sec[2], "bullets": [], "stats": [], "quote": "", "author": "",
            "notes": f"Let us move into {sec[0]}. {sec[2]}", "section": section_index + 1,
        })
        for variant in range(counts[section_index]):
            title, bullets, notes = bullets_for(section_index, variant)
            slides.append({
                "type": "bullets", "eyebrow": f"{section_index+1:02d} / {sec[0].upper()}",
                "title": title, "subtitle": "", "bullets": bullets, "stats": [], "quote": "", "author": "",
                "notes": notes, "section": section_index + 1,
            })
    if stats_on:
        slides.append({
            "type": "stats", "eyebrow": "MEASURE", "title": "Three numbers to watch",
            "subtitle": "Choose the three numbers that will guide the next decision.",
            "bullets": [], "stats": [
                {"value": "3", "label": "Priority use cases", "note": "Focus before scale"},
                {"value": "90", "label": "Day pilot", "note": "Small loop, real feedback"},
                {"value": "1", "label": "Weekly review", "note": "Make data actionable"},
            ], "quote": "", "author": "",
            "notes": "Three numbers keep the team honest: the use cases we chose, the length of the pilot, and the rhythm of review.",
            "section": 0,
        })
    if quote_on:
        slides.append({
            "type": "quote", "eyebrow": "A PAUSE", "title": "One sentence to keep",
            "subtitle": "", "bullets": [], "stats": [],
            "quote": "Clarity is a form of respect for the audience.",
            "author": "Qiming Studio",
            "notes": "I want to pause here: clarity is a form of respect. It shapes every slide we make.",
            "section": 0,
        })
    if summary_on:
        slides.append({
            "type": "summary", "eyebrow": "TAKEAWAYS", "title": "Three things to remember",
            "subtitle": "A short list the audience can take into the next meeting.",
            "bullets": [
                "Define the problem in one sentence.",
                "Run one small pilot with a real baseline.",
                "Keep a weekly feedback loop and a clear stop rule.",
            ], "stats": [], "quote": "", "author": "",
            "notes": "If the audience remembers only three things, let it be these: a clear problem, a small pilot, and a feedback loop.",
            "section": 0,
        })
    slides.append({
        "type": "end", "eyebrow": "THANK YOU", "title": "Thank you" if include_qa else "Let us begin",
        "subtitle": "Questions and discussion are welcome." if include_qa else "Turn the first insight into one action.",
        "bullets": [], "stats": [], "quote": "", "author": "",
        "notes": "Thank you for your time. I am happy to take questions or discuss the next step.",
        "section": 0,
    })
    while len(slides) > target:
        candidates = [i for i, slide in enumerate(slides) if i not in (0, len(slides)-1) and slide["type"] != "summary"]
        if not candidates:
            break
        slides.pop(candidates[-1])
    while len(slides) < target:
        slides.insert(len(slides)-1, {
            "type": "bullets", "eyebrow": "EXTEND", "title": "A question to take further",
            "subtitle": "", "bullets": [
                "What assumption is still untested?",
                "Who owns the next action?",
                "What will we measure in the first two weeks?",
            ], "stats": [], "quote": "", "author": "",
            "notes": "This page extends the discussion with three questions that turn the idea into action.",
            "section": 0,
        })
    return {
        "title": topic,
        "subtitle": "A clear narrative, a practical framework, and next steps.",
        "audience": resolved_audience,
        "narrative": "From context to a practical framework, evidence, and a measurable next step.",
        "provider_used": "Qiming Built-in AI",
        "warnings": [],
        "sources": [],
        "slides": slides,
    }
