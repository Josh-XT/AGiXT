"""
Trial Service - Handles free trial credit granting and domain validation.

This service manages the free trial system which grants credits to new users
registering with valid business email domains. It prevents abuse by:
1. Blocking common free email providers (gmail, outlook, etc.)
2. Tracking which domains have already used trial credits
3. Enforcing one trial per domain policy
"""

import logging
from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from DB import Company, TrialDomain, get_session, get_db_session
from ExtensionsHub import ExtensionsHub

# Common free email providers that don't qualify for business trials
FREE_EMAIL_PROVIDERS = frozenset(
    [
        # Google
        "gmail.com",
        "googlemail.com",
        # Microsoft
        "outlook.com",
        "hotmail.com",
        "live.com",
        "msn.com",
        "passport.com",
        # Yahoo
        "yahoo.com",
        "yahoo.co.uk",
        "yahoo.fr",
        "yahoo.de",
        "yahoo.es",
        "yahoo.it",
        "yahoo.ca",
        "yahoo.com.au",
        "yahoo.co.jp",
        "yahoo.co.in",
        "ymail.com",
        "rocketmail.com",
        # Apple
        "icloud.com",
        "me.com",
        "mac.com",
        # AOL
        "aol.com",
        "aim.com",
        # ProtonMail
        "protonmail.com",
        "protonmail.ch",
        "proton.me",
        "pm.me",
        # Tutanota
        "tutanota.com",
        "tutamail.com",
        "tuta.io",
        # Zoho
        "zohomail.com",
        "zoho.com",
        # Other common free providers
        "mail.com",
        "email.com",
        "inbox.com",
        "gmx.com",
        "gmx.net",
        "gmx.de",
        "web.de",
        "yandex.com",
        "yandex.ru",
        "qq.com",
        "163.com",
        "126.com",
        "sina.com",
        "fastmail.com",
        "fastmail.fm",
        "hushmail.com",
        "mailinator.com",
        "guerrillamail.com",
        "tempmail.com",
        "10minutemail.com",
        "sharklasers.com",
        "trashmail.com",
        "dispostable.com",
        "getairmail.com",
        "maildrop.cc",
        # ISP-based free email
        "comcast.net",
        "verizon.net",
        "att.net",
        "cox.net",
        "charter.net",
        "earthlink.net",
        "sbcglobal.net",
        "btinternet.com",
        "virginmedia.com",
        "sky.com",
        "orange.fr",
        "free.fr",
        "laposte.net",
        "t-online.de",
    ]
)


class TrialService:
    """Service for managing free trial credits and domain validation."""

    def __init__(self):
        self.extensions_hub = ExtensionsHub()

    def extract_domain(self, email: str) -> str:
        """
        Extract the domain from an email address.

        Args:
            email: Full email address

        Returns:
            Lowercase domain portion of the email
        """
        if not email or "@" not in email:
            return ""
        return email.lower().split("@")[1]

    def is_free_email_provider(self, domain: str) -> bool:
        """
        Check if the domain is a known free email provider.

        Args:
            domain: Email domain to check

        Returns:
            True if the domain is a free email provider
        """
        return domain.lower() in FREE_EMAIL_PROVIDERS

    def is_business_domain(self, email: str) -> bool:
        """
        Check if an email is from a business domain (not a free provider).

        Args:
            email: Full email address

        Returns:
            True if the email is from a business domain
        """
        domain = self.extract_domain(email)
        if not domain:
            return False
        return not self.is_free_email_provider(domain)

    def has_domain_used_trial(self, domain: str, session: Session = None) -> bool:
        """
        Check if a domain has already used trial credits.

        Args:
            domain: Email domain to check
            session: Optional database session

        Returns:
            True if the domain has already used trial credits
        """
        close_session = False
        if session is None:
            session = get_session()
            close_session = True

        try:
            trial = (
                session.query(TrialDomain)
                .filter(TrialDomain.domain == domain.lower())
                .first()
            )
            return trial is not None
        finally:
            if close_session:
                session.close()

    def get_trial_config(self) -> dict:
        """
        Get the trial configuration from the pricing config.

        Returns:
            Trial configuration dict with enabled, days, credits_usd, etc.
        """
        pricing_config = self.extensions_hub.get_pricing_config()
        trial_config = pricing_config.get("trial", {}) if pricing_config else {}

        # Default trial configuration
        defaults = {
            "enabled": False,
            "days": 7,
            "credits_usd": 5.00,  # $5 worth of credits
            "type": "credits",
            "requires_card": False,
            "description": "Free trial credits for business domains",
        }

        # Merge with defaults
        for key, value in defaults.items():
            if key not in trial_config:
                trial_config[key] = value

        return trial_config

    def check_trial_eligibility(
        self, email: str, session: Session = None
    ) -> Tuple[bool, str, Optional[float]]:
        """
        Check if an email is eligible for trial credits.

        Args:
            email: Email address to check
            session: Optional database session

        Returns:
            Tuple of (eligible: bool, reason: str, credits_usd: float or None)
        """
        trial_config = self.get_trial_config()

        # Check if trials are enabled
        if not trial_config.get("enabled", False):
            return False, "Trials are not currently enabled", None

        domain = self.extract_domain(email)
        if not domain:
            return False, "Invalid email address", None

        # Check if it's a free email provider
        if self.is_free_email_provider(domain):
            return (
                False,
                f"Free email providers ({domain}) are not eligible for trial credits. Please use a business email.",
                None,
            )

        # Check if domain already used trial
        close_session = False
        if session is None:
            session = get_session()
            close_session = True

        try:
            if self.has_domain_used_trial(domain, session):
                return (
                    False,
                    f"A trial has already been used for the domain {domain}",
                    None,
                )

            credits_usd = trial_config.get("credits_usd", 5.00)
            return True, "Eligible for trial credits", credits_usd
        finally:
            if close_session:
                session.close()

    def grant_trial_credits(
        self,
        company_id: str,
        user_id: str,
        email: str,
        session: Session = None,
    ) -> Tuple[bool, str, Optional[float]]:
        """
        Grant trial credits to a company if eligible.

        This method:
        1. Validates the email domain is eligible
        2. Records the domain as having used trial credits
        3. Adds credits to the company's token balance

        Args:
            company_id: UUID of the company to grant credits to
            user_id: UUID of the user requesting trial
            email: Email address of the user
            session: Optional database session

        Returns:
            Tuple of (success: bool, message: str, credits_granted: float or None)
        """
        domain = self.extract_domain(email)

        # Check eligibility first
        eligible, reason, credits_usd = self.check_trial_eligibility(email, session)
        if not eligible:
            return False, reason, None

        close_session = False
        if session is None:
            session = get_session()
            close_session = True

        try:
            # Double-check domain hasn't been used (race condition protection)
            existing_trial = (
                session.query(TrialDomain)
                .filter(TrialDomain.domain == domain.lower())
                .first()
            )
            if existing_trial:
                return (
                    False,
                    f"A trial has already been used for the domain {domain}",
                    None,
                )

            # Get the company
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                return False, "Company not found", None

            # Record the trial domain
            trial_domain = TrialDomain(
                domain=domain.lower(),
                company_id=company_id,
                user_id=user_id,
                credits_granted=credits_usd,
            )
            session.add(trial_domain)

            # Grant credits to company
            current_balance = company.token_balance_usd or 0.0
            company.token_balance_usd = current_balance + credits_usd
            company.trial_credits_granted = credits_usd
            company.trial_credits_granted_at = datetime.utcnow()
            company.trial_domain = domain.lower()

            # Calculate token amount based on pricing
            # We'll use the default token price from PriceService
            try:
                from payments.stripe_service import PriceService

                price_service = PriceService()
                token_price = float(price_service.get_token_price())
                if token_price > 0:
                    tokens_granted = int((credits_usd / token_price) * 1_000_000)
                    company.token_balance = (
                        company.token_balance or 0
                    ) + tokens_granted
            except Exception as e:
                logging.warning(f"Could not calculate token amount for trial: {e}")

            session.commit()

            logging.info(
                f"Granted ${credits_usd:.2f} trial credits to company {company_id} "
                f"for domain {domain}"
            )

            # Send Discord notification for trial credits
            try:
                import asyncio
                from middleware import send_discord_trial_notification

                # Get company name for notification
                company_name = company.name if company else None

                # Run async notification in sync context
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If we're already in an async context, create a task
                    asyncio.create_task(
                        send_discord_trial_notification(
                            email=email,
                            credits_usd=credits_usd,
                            domain=domain.lower(),
                            company_id=company_id,
                            company_name=company_name,
                        )
                    )
                else:
                    # Otherwise run synchronously
                    loop.run_until_complete(
                        send_discord_trial_notification(
                            email=email,
                            credits_usd=credits_usd,
                            domain=domain.lower(),
                            company_id=company_id,
                            company_name=company_name,
                        )
                    )
            except Exception as e:
                logging.warning(f"Failed to send Discord trial notification: {e}")

            return True, f"Granted ${credits_usd:.2f} in trial credits", credits_usd

        except Exception as e:
            if not close_session:
                session.rollback()
            logging.error(f"Error granting trial credits: {e}")
            return False, f"Error granting trial credits: {str(e)}", None
        finally:
            if close_session:
                session.close()

    def get_trial_status(self, company_id: str, session: Session = None) -> dict:
        """
        Get the trial status for a company.

        Args:
            company_id: UUID of the company
            session: Optional database session

        Returns:
            Dict with trial status information
        """
        close_session = False
        if session is None:
            session = get_session()
            close_session = True

        try:
            company = session.query(Company).filter(Company.id == company_id).first()
            if not company:
                return {"trial_used": False, "credits_granted": None}

            return {
                "trial_used": company.trial_credits_granted is not None,
                "credits_granted": company.trial_credits_granted,
                "granted_at": (
                    company.trial_credits_granted_at.isoformat()
                    if company.trial_credits_granted_at
                    else None
                ),
                "domain": company.trial_domain,
            }
        finally:
            if close_session:
                session.close()


# Singleton instance
trial_service = TrialService()


def check_trial_eligibility(email: str) -> Tuple[bool, str, Optional[float]]:
    """Convenience function to check trial eligibility."""
    return trial_service.check_trial_eligibility(email)


def grant_trial_credits(
    company_id: str, user_id: str, email: str
) -> Tuple[bool, str, Optional[float]]:
    """Convenience function to grant trial credits."""
    return trial_service.grant_trial_credits(company_id, user_id, email)


def is_business_domain(email: str) -> bool:
    """Convenience function to check if email is from a business domain."""
    return trial_service.is_business_domain(email)
