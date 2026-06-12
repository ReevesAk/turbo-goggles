import json
import logging

import anthropic
from decouple import config as conf

logger = logging.getLogger(__name__)

VERIFICATION_MODEL = "claude-haiku-4-5"

_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["Pass", "Fail", "Uncertain"]},
        "confidence_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "reasoning": {"type": "string"},
        "username_matched": {"type": "boolean"},
        "hashtag_found": {"type": "boolean"},
        "mention_found": {"type": "boolean"},
        "action_confirmed": {"type": "boolean"},
        "flags": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "verdict", "confidence_score", "reasoning",
        "username_matched", "hashtag_found", "mention_found",
        "action_confirmed", "flags",
    ],
}


def _get_registered_username(submission) -> str | None:
    try:
        return submission.user.social_profile.get_username_for_platform(
            submission.task.platform
        )
    except Exception:
        return None


def _build_prompt(submission, registered_username: str | None) -> str:
    task = submission.task
    lines = [
        f"Platform: {task.platform}",
        f"Required action: {task.task_type}",
        f"Task: {task.description or task.title}",
    ]

    if task.target_account:
        lines.append(f"Target account: @{task.target_account}")
    if task.target_url:
        lines.append(f"Target URL: {task.target_url}")
    if task.required_hashtag:
        lines.append(f"Required hashtag: #{task.required_hashtag.lstrip('#')}")
    if task.required_mention:
        lines.append(f"Required mention: @{task.required_mention.lstrip('@')}")
    if task.required_keywords:
        lines.append(f"Required keywords: {', '.join(task.required_keywords)}")
    if registered_username:
        lines.append(f"Registered username for this user: @{registered_username}")
    if submission.post_url:
        lines.append(f"Submitted post URL: {submission.post_url}")

    lines += [
        "",
        "Examine the screenshot above and evaluate:",
        "- Is this a genuine, unedited screenshot from the stated platform?",
        "- Does it clearly show the required action was performed?",
        "- Does the logged-in account username match the registered username (if provided)?",
        "- Is the required hashtag visible in the post or comment (if required)?",
        "- Is the required mention present (if required)?",
        "- Are there any red flags: wrong platform UI, inconsistent elements, obvious edits?",
        "",
        'Return ONLY valid JSON matching this structure, no other text:',
        json.dumps({
            "verdict": "Pass|Fail|Uncertain",
            "confidence_score": "0-100 integer",
            "reasoning": "one or two sentences",
            "username_matched": "true if registered username visible and matches, false otherwise",
            "hashtag_found": "true if required hashtag present or not required",
            "mention_found": "true if required mention present or not required",
            "action_confirmed": "true if the action (follow/like/comment/post) is clearly visible",
            "flags": ["list", "of", "concerns"],
        }),
    ]
    return "\n".join(lines)


class VerificationError(Exception):
    pass


def verify_submission(submission) -> dict:
    """
    Sends the submission screenshot to Claude Vision for analysis.

    Returns a dict with keys: verdict, confidence_score, reasoning,
    username_matched, hashtag_found, mention_found, action_confirmed, flags.

    Raises VerificationError if the screenshot URL is missing or the API call fails.
    """
    if not submission.screenshot_url:
        raise VerificationError("No screenshot URL on submission")

    registered_username = _get_registered_username(submission)
    prompt = _build_prompt(submission, registered_username)

    client = anthropic.Anthropic(api_key=conf("ANTHROPIC_API_KEY"))

    try:
        response = client.messages.create(
            model=VERIFICATION_MODEL,
            max_tokens=512,
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "url",
                                "url": submission.screenshot_url,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
    except anthropic.APIError as exc:
        logger.exception("Claude API error verifying submission %s", submission.pk)
        raise VerificationError(str(exc)) from exc

    raw = response.content[0].text
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Non-JSON response from Claude for submission %s: %s", submission.pk, raw)
        raise VerificationError("Invalid JSON from Claude") from exc

    return {
        "verdict": data.get("verdict", "Uncertain"),
        "confidence_score": max(0, min(100, int(data.get("confidence_score", 0)))),
        "reasoning": str(data.get("reasoning", "")),
        "username_matched": bool(data.get("username_matched", False)),
        "hashtag_found": bool(data.get("hashtag_found", False)),
        "mention_found": bool(data.get("mention_found", False)),
        "action_confirmed": bool(data.get("action_confirmed", False)),
        "flags": list(data.get("flags", [])),
    }
