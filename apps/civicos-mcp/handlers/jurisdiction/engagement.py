"""
Engagement handlers with jurisdiction configuration.

These handlers use the jurisdiction config for contact info
instead of hardcoded values.
"""

from typing import Any, Callable

from ..loader import get_config_for_handler

# Type aliases
CivicClient = Any
ValidateInput = Callable[[dict], tuple[bool, dict, str | None]]
Logger = Any


def compose_public_comment(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get context for writing a public comment (config-driven)."""
    config = get_config_for_handler(jurisdiction)
    contact = config.contact_info
    body = config.governing_body

    item_title = args.get("item_title", "")
    topic = args.get("topic") or item_title

    is_valid, sanitized, error = validate_input({"item_title": item_title, "topic": topic})
    if not is_valid:
        return f"Error: Invalid input - {error}"

    result_parts = [f"# Public Comment Context: {item_title}", ""]

    result_parts.append("## Submission Guidelines")
    result_parts.append("")
    result_parts.append(f"**{body.name}:**")
    if contact.clerk_email:
        result_parts.append(f"- Email: {contact.clerk_email}")
    result_parts.append(f"- Subject line: \"{contact.public_comment_subject}\"")
    if contact.public_comment_deadline:
        result_parts.append(f"- Deadline: {contact.public_comment_deadline} for written record")
    if contact.in_person_time_limit:
        result_parts.append(f"- In-person: {contact.in_person_time_limit} max, sign up before meeting")
    result_parts.append("")

    # Past testimony
    try:
        testimony = civic.get_public_testimony(topic, top_k=3)
        if testimony:
            result_parts.append("## What Others Have Said")
            for t in testimony[:3]:
                speaker = getattr(t, 'speaker_name', 'Resident')
                text = getattr(t, 'text', str(t))[:200]
                result_parts.append(f"**{speaker}:** \"{text}...\"")
                result_parts.append("")
    except Exception as e:
        logger.warning(f"Could not fetch testimony: {e}")

    result_parts.append("## Tips for Effective Comments")
    result_parts.append("")
    result_parts.append("1. State your position clearly in the first sentence")
    result_parts.append("2. Be specific - reference the agenda item by name")
    result_parts.append("3. Share personal impact - how does this affect you?")
    result_parts.append("4. Propose alternatives if opposing")
    result_parts.append(f"5. Be respectful - address \"{body.members_title}\"")
    result_parts.append(f"6. Include your address to show you're a {config.display_name} resident")

    return "\n".join(result_parts)


def get_comment_guidelines(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get public comment guidelines (config-driven)."""
    config = get_config_for_handler(jurisdiction)
    contact = config.contact_info
    body = config.governing_body

    parts = [
        f"{config.display_name} Public Comment Guidelines:",
        "",
        "EMAIL SUBMISSION:",
    ]

    if contact.clerk_email:
        parts.append(f"- Send to: {contact.clerk_email}")
    parts.append(f"- Subject: \"{contact.public_comment_subject}\"")
    parts.append(f"- Include your name and {config.display_name} address")
    if contact.public_comment_deadline:
        parts.append(f"- Submit by {contact.public_comment_deadline} for inclusion in official record")

    parts.extend([
        "",
        "IN-PERSON COMMENTS:",
        "- Sign up before meeting starts",
    ])
    if contact.in_person_time_limit:
        parts.append(f"- {contact.in_person_time_limit} maximum per speaker")
    parts.append(f"- Address comments to {body.members_title}")
    parts.append("- No personal attacks or off-topic remarks")

    parts.extend([
        "",
        "CONTACT INFO:",
    ])
    if contact.clerk_email:
        parts.append(f"- City Clerk: {contact.clerk_email}")
    if body.meeting_schedule:
        parts.append(f"- Council meetings: {body.meeting_schedule}")
    if contact.city_hall_address:
        parts.append(f"- City Hall: {contact.city_hall_address}")

    return "\n".join(parts)


def get_comment_template(
    civic: CivicClient,
    jurisdiction: str,
    validate_input: ValidateInput,
    logger: Logger,
    args: dict,
) -> str:
    """Get a fill-in-the-blank public comment template (config-driven)."""
    config = get_config_for_handler(jurisdiction)
    body = config.governing_body

    item_title = args.get("item_title", "")
    stance = args.get("stance")
    key_points = args.get("key_points")

    parts = [
        f"Re: {item_title}",
        "",
        f"Dear {body.members_title},",
        "",
    ]

    if stance:
        stance_text = {
            "support": "I am writing to express my support for this agenda item.",
            "oppose": "I am writing to express my concerns about this agenda item.",
            "question": "I am writing to request clarification about this agenda item.",
            "neutral": "I am writing to provide input on this agenda item."
        }
        parts.append(stance_text.get(stance.lower(), "I am writing to provide input on this agenda item."))
    else:
        parts.append("I am writing to provide input on this agenda item.")

    parts.append("")

    if key_points:
        parts.append("Key points:")
        for point in key_points.split("\n"):
            if point.strip():
                parts.append(f"- {point.strip()}")
    else:
        parts.append("Please consider the following:")
        parts.append("- [Your specific concerns or suggestions here]")
        parts.append("- [Impact on residents/community]")
        parts.append("- [Alternatives or modifications to consider]")

    parts.extend([
        "",
        "Thank you for your consideration and service to our community.",
        "",
        "Sincerely,",
        "[Your Name]",
        f"[Your Address in {config.display_name}]",
    ])

    return "\n".join(parts)
