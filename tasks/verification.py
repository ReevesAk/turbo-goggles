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
        "verification_code_found": {"type": "boolean"},
        "target_matched": {"type": "boolean"},
        "flags": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "verdict", "confidence_score", "reasoning",
        "username_matched", "hashtag_found", "mention_found",
        "action_confirmed", "verification_code_found", "target_matched", "flags",
    ],
}

# Per (platform, task_type): what screenshot the user is expected to submit
# and what the AI must look for to confirm both identity and action.
_PLATFORM_PROOF_GUIDANCE = {
    # ── TikTok ──────────────────────────────────────────────────────────────
    ("TikTok", "Like"): (
        "PROOF TYPE — TikTok Like: "
        "Expected screenshot: the user's Profile → 'Liked' tab (heart/bookmark tab on their own profile). "
        "Must show (1) their @handle in the profile header, "
        "(2) the target video '{hint}' visible in the liked grid — match by title, thumbnail, or @{target}'s branding, "
        "and (3) not just any video, but specifically the required one. "
        "A screenshot of the video page with a heart icon or like count alone is NOT valid — it does not identify the user."
    ),
    ("TikTok", "Follow"): (
        "PROOF TYPE — TikTok Follow: "
        "Expected screenshot: the user's Profile → 'Following' list. "
        "Must show (1) their @handle in the profile or list header and "
        "(2) the account @{target} explicitly listed in the Following list. "
        "Any other account visible does not count — @{target} must be identifiable by handle or display name. "
        "A screenshot of @{target}'s account page with a 'Following' button state is also valid "
        "IF their own @handle is visible on screen."
    ),
    ("TikTok", "Comment"): (
        "PROOF TYPE — TikTok Comment: "
        "Expected screenshot: the comment section of the target TikTok video by @{target}. "
        "Must show (1) their @handle next to their comment, "
        "(2) the unique verification code present verbatim in the comment text, and "
        "(3) the video context (title, thumbnail, or @{target} account name) confirming this is the correct post — '{hint}'. "
        "All three are required for Pass. If the code is absent, verdict must be Fail."
    ),
    ("TikTok", "Post"): (
        "PROOF TYPE — TikTok Post: "
        "Expected screenshot: their TikTok post on their profile or in the feed. "
        "Must show (1) their @handle on the post and (2) any required hashtag or mention in the caption. "
        "Confirm the post content matches the task description: '{hint}'."
    ),
    # ── Instagram ───────────────────────────────────────────────────────────
    ("Instagram", "Like"): (
        "PROOF TYPE — Instagram Like: "
        "Expected screenshot: Settings → Your Activity → Interactions → Likes (the liked posts list). "
        "Must show (1) their account context (username/avatar) and "
        "(2) the target post '{hint}' from @{target} visible in the liked list — identifiable by image, caption snippet, or account name. "
        "A screenshot of a post with a filled red heart alone is NOT valid — "
        "the 'Your Activity → Likes' page is the only accepted proof."
    ),
    ("Instagram", "Follow"): (
        "PROOF TYPE — Instagram Follow: "
        "Expected screenshot: Profile → Following list. "
        "Must show (1) their @handle in the profile or list header and "
        "(2) the account @{target} visible and identifiable in the Following list. "
        "A screenshot of @{target}'s profile page showing 'Following' is also valid "
        "IF their own @handle is visible in the header."
    ),
    ("Instagram", "Comment"): (
        "PROOF TYPE — Instagram Comment: "
        "Expected screenshot: the comment section of the target Instagram post by @{target}. "
        "Must show (1) their @handle next to their comment, "
        "(2) the unique verification code present verbatim in the comment text, and "
        "(3) visible context confirming this is the correct post — @{target}'s username or post matching '{hint}'. "
        "All three are required for Pass. If the code is absent, verdict must be Fail."
    ),
    ("Instagram", "Post"): (
        "PROOF TYPE — Instagram Post: "
        "Expected screenshot: their Instagram post on their profile grid or in the feed. "
        "Must show (1) their @handle on the post and (2) any required hashtag or mention in the caption. "
        "Confirm the post content matches the task description: '{hint}'."
    ),
    # ── Facebook ────────────────────────────────────────────────────────────
    ("Facebook", "Like"): (
        "PROOF TYPE — Facebook Like/React: "
        "Expected screenshot: Profile → Activity Log → Likes and Reactions section. "
        "Must show (1) their Facebook name or profile context in the header and "
        "(2) the target post or page '{hint}' from {target} identifiable in the activity log. "
        "A screenshot of a post with a reaction emoji alone is NOT valid — the Activity Log is required."
    ),
    ("Facebook", "Follow"): (
        "PROOF TYPE — Facebook Follow/Like Page: "
        "Expected screenshot: the target Facebook Page '{hint}' ({target}) showing both 'Liked' and 'Following' status, "
        "with their profile name or avatar visible in the top navigation bar. "
        "The page name or branding must be clearly identifiable as {target}. "
        "Alternatively, Profile → Pages → Liked Pages showing {target} is also valid."
    ),
    ("Facebook", "Comment"): (
        "PROOF TYPE — Facebook Comment: "
        "Expected screenshot: the comment section of the target Facebook post by {target}. "
        "Must show (1) their Facebook profile name and picture next to their comment, "
        "(2) the unique verification code present verbatim in the comment text, and "
        "(3) visible context confirming this is the correct post — {target}'s name or post matching '{hint}'. "
        "All three are required for Pass. If the code is absent, verdict must be Fail."
    ),
    ("Facebook", "Post"): (
        "PROOF TYPE — Facebook Post: "
        "Expected screenshot: their Facebook post on their timeline or in the feed. "
        "Must show (1) their Facebook name on the post and (2) any required hashtag or mention in the post text. "
        "Confirm the post content matches the task description: '{hint}'."
    ),
    # ── YouTube ─────────────────────────────────────────────────────────────
    ("YouTube", "Like"): (
        "PROOF TYPE — YouTube Like: "
        "Expected screenshot: Library → Liked videos playlist. "
        "Must show (1) their channel name or Google account avatar at the top and "
        "(2) the target video '{hint}' from @{target} visible in the Liked videos list — identifiable by title or thumbnail. "
        "A screenshot of the video with a filled thumbs-up icon alone is NOT valid — the Liked videos playlist is required."
    ),
    ("YouTube", "Follow"): (
        "PROOF TYPE — YouTube Subscribe: "
        "Expected screenshot: the target YouTube channel @{target} showing the 'Subscribed' button, "
        "with their Google account avatar visible in the top-right corner. "
        "The channel name or handle @{target} must be clearly visible on screen. "
        "Alternatively, Library → Subscriptions showing @{target}'s content is also valid."
    ),
    ("YouTube", "Comment"): (
        "PROOF TYPE — YouTube Comment: "
        "Expected screenshot: the comment section of the target YouTube video '{hint}' by @{target}. "
        "Must show (1) their channel name next to their comment, "
        "(2) the unique verification code present verbatim in the comment text, and "
        "(3) visible context confirming this is the correct video — the video title or @{target}'s channel name matching '{hint}'. "
        "All three are required for Pass. If the code is absent, verdict must be Fail."
    ),
    ("YouTube", "Post"): (
        "PROOF TYPE — YouTube Community Post: "
        "Expected screenshot: their YouTube Community tab showing the published post. "
        "Must show (1) their channel name on the post and (2) any required hashtag or mention in the post text. "
        "Confirm the post content matches the task description: '{hint}'."
    ),
    # ── X (Twitter) ─────────────────────────────────────────────────────────
    ("X", "Like"): (
        "PROOF TYPE — X (Twitter) Like: "
        "Expected screenshot: Profile → Likes tab, showing the target post in their liked posts list. "
        "Must show (1) their @handle in the profile header and "
        "(2) the target post '{hint}' from @{target} visible in the Likes tab — identifiable by post text or @{target}'s handle. "
        "A screenshot of a post with a filled pink heart alone is NOT sufficient."
    ),
    ("X", "Follow"): (
        "PROOF TYPE — X (Twitter) Follow: "
        "Expected screenshot: Profile → Following list showing the target account @{target}. "
        "Must show (1) their @handle in the profile or list header and "
        "(2) @{target} explicitly listed and identifiable in the Following list."
    ),
    ("X", "Comment"): (
        "PROOF TYPE — X (Twitter) Reply: "
        "Expected screenshot: their reply to the target post by @{target}. "
        "Must show (1) their @handle above the reply, "
        "(2) the verification code verbatim in the reply text, and "
        "(3) the original post context from @{target} matching '{hint}'. "
        "All three are required for Pass. If the code is absent, verdict must be Fail."
    ),
    ("X", "Post"): (
        "PROOF TYPE — X (Twitter) Post: "
        "Expected screenshot: their X post on their profile or in the feed. "
        "Their @handle must be visible, any required hashtag or mention must be present, "
        "and the post content must match the task description: '{hint}'."
    ),
}

# Task types that require a per-submission verification code embedded in the text
_CODE_REQUIRED_TYPES = {"Comment", "Post"}


def _get_registered_username(submission) -> str | None:
    try:
        return submission.user.social_profile.get_username_for_platform(
            submission.task.platform
        )
    except Exception:
        return None


def _build_prompt(submission, registered_username: str | None) -> str:
    task = submission.task
    verification_code = submission.verification_code

    lines = [
        f"Platform: {task.platform}",
        f"Required action: {task.task_type}",
        f"Task: {task.description or task.title}",
    ]

    if task.target_account:
        lines.append(f"Target account: @{task.target_account}")
    if task.target_url:
        lines.append(f"Target URL: {task.target_url}")
    if task.target_content_hint:
        lines.append(f"Target content description: {task.target_content_hint}")
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
    if verification_code:
        lines.append(f"Unique verification code (must appear verbatim in the screenshot): {verification_code}")

    # Platform + action-specific proof guidance
    guidance = _PLATFORM_PROOF_GUIDANCE.get((task.platform, task.task_type))
    if guidance:
        target = task.target_account or ""
        code = verification_code or ""
        hint = task.target_content_hint or (task.description or task.title or "")
        lines += [
            "",
            guidance.replace("{target}", target).replace("{code}", code).replace("{hint}", hint),
        ]

    lines += [
        "",
        "Examine the screenshot above and evaluate:",
        "- Is this a genuine, unedited screenshot from the stated platform?",
        "- Does it match the expected proof type described above?",
        "- Does it clearly show the required action was performed?",
        "- Is the registered username (@handle or profile name) visible and matching?",
        "- Is the target account or content identifiable in the screenshot — does it match the target account, URL, or content description provided?",
        "- Is the required hashtag visible in the post or comment (if required)?",
        "- Is the required mention present (if required)?",
        f"- Is the verification code '{verification_code}' present verbatim in the screenshot? (only relevant for Comment/Post tasks)",
        "- Are there any red flags: wrong platform UI, inconsistent elements, obvious edits, wrong screenshot type, or wrong target?",
        "",
        'Return ONLY valid JSON matching this structure, no other text:',
        json.dumps({
            "verdict": "Pass|Fail|Uncertain",
            "confidence_score": "0-100 integer",
            "reasoning": "one or two sentences",
            "username_matched": "true if registered username is visible and matches, false otherwise",
            "target_matched": "true if the target account or post/video is clearly identifiable in the screenshot and matches the task's target, false otherwise",
            "hashtag_found": "true if required hashtag present or not required",
            "mention_found": "true if required mention present or not required",
            "action_confirmed": "true if the action (follow/like/comment/post/subscribe) is clearly visible",
            "verification_code_found": "true if the verification code appears verbatim in the screenshot, or if no code was required",
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
    username_matched, hashtag_found, mention_found, action_confirmed,
    verification_code_found, flags.

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
        "target_matched": bool(data.get("target_matched", False)),
        "hashtag_found": bool(data.get("hashtag_found", False)),
        "mention_found": bool(data.get("mention_found", False)),
        "action_confirmed": bool(data.get("action_confirmed", False)),
        "verification_code_found": bool(data.get("verification_code_found", True)),
        "flags": list(data.get("flags", [])),
    }
