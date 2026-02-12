from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from os import getenv
from MagicalAuth import verify_api_key, get_user_company_id
from middleware import send_discord_notification
import logging

app = APIRouter()


class FeedbackInput(BaseModel):
    """Input model for user feedback to development team."""

    feedback: str
    subject: Optional[str] = None
    category: str
    priority: Optional[str] = "normal"
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    company_name: Optional[str] = None


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "UP"}


@app.post(
    "/v1/feedback",
    tags=["Health"],
    summary="Send feedback to development team",
    description="Submit feedback, bug reports, or feature requests to the DevXT development team.",
)
async def send_feedback(
    feedback_input: FeedbackInput,
    user=Depends(verify_api_key),
):
    """
    Send feedback to the development team's Discord channel.

    This endpoint allows users to submit feedback, report issues, or request features.
    The feedback is sent directly to the DevXT development team's Discord channel.
    """
    try:
        # Get user email and company from the authenticated user
        user_email = None
        if isinstance(user, dict):
            user_email = user.get("email")
        elif isinstance(user, str):
            user_email = user

        # Get company ID if available
        company_id = None
        try:
            company_id = get_user_company_id(user)
        except Exception:
            pass

        # Map category to emoji
        category_emojis = {
            "bug": "🐛",
            "feature": "✨",
            "question": "❓",
            "billing": "💳",
            "access": "🔐",
            "other": "📝",
        }
        category_emoji = category_emojis.get(feedback_input.category.lower(), "📝")

        # Map priority to color
        priority_colors = {
            "low": 3447003,  # Blue
            "normal": 5814783,  # Purple
            "high": 16776960,  # Yellow
            "urgent": 15158332,  # Red
        }
        color = priority_colors.get(feedback_input.priority.lower(), 5814783)

        # Build the embed title from subject or fallback
        embed_title = (
            f"{category_emoji} {feedback_input.subject}"
            if feedback_input.subject
            else f"{category_emoji} User Feedback"
        )

        # Build Discord embed fields - each field is a clean key/value pair
        fields = [
            {
                "name": "Category",
                "value": feedback_input.category.title(),
                "inline": True,
            },
            {
                "name": "Priority",
                "value": feedback_input.priority.title(),
                "inline": True,
            },
        ]

        # Add user info if provided
        if feedback_input.user_name:
            fields.append(
                {
                    "name": "Submitted By",
                    "value": feedback_input.user_name,
                    "inline": True,
                }
            )

        # Add company info
        if feedback_input.company_name:
            fields.append(
                {
                    "name": "Company",
                    "value": feedback_input.company_name,
                    "inline": True,
                }
            )
        elif company_id:
            fields.append(
                {
                    "name": "Company ID",
                    "value": str(company_id),
                    "inline": True,
                }
            )

        # Add the description/feedback as the last field
        feedback_text = (
            feedback_input.feedback[:1024]
            if feedback_input.feedback
            else "No details provided"
        )
        fields.append(
            {
                "name": "Description",
                "value": feedback_text,
                "inline": False,
            }
        )

        await send_discord_notification(
            title=embed_title,
            description=f"Support request submitted via {getenv('APP_NAME', 'AGiXT')}",
            color=color,
            fields=fields,
            user_email=feedback_input.user_email or user_email,
            user_id=None,
        )

        return {
            "message": "Thank you! Your feedback has been successfully sent to the development team. They will review your feedback to help improve the system."
        }

    except Exception as e:
        logging.error(f"Failed to send feedback to development team: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"We apologize, but there was an error sending your feedback. Please try again later.",
        )
