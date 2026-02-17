"""
Trial Service - Handles free trial credit granting and domain validation.

This service manages the free trial system which grants credits to all new users
registering. It prevents abuse by:
1. Tracking which domains have already used trial credits
2. Enforcing one trial per domain policy for business domains
3. Allowing individual trials for users with public email providers
"""

import logging
from datetime import datetime, timezone
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
        # Additional disposable email providers
        "throwaway.email",
        "temp-mail.org",
        "guerrillamail.info",
        "guerrillamail.net",
        "guerrillamail.de",
        "yopmail.com",
        "yopmail.fr",
        "mohmal.com",
        "tempail.com",
        "fakeinbox.com",
        "mailnesia.com",
        "throwam.com",
        "tmpmail.net",
        "tmpmail.org",
        "bupmail.com",
        "mailsac.com",
        "mytemp.email",
        "emailondeck.com",
        "33mail.com",
        "getnada.com",
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

    def _get_pricing_config(self):
        """Get pricing config from extensions hub."""
        try:
            return self.extensions_hub.get_pricing_config()
        except Exception:
            return None

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

        # Fall back to default pricing config if no pricing.json exists
        if pricing_config is None:
            pricing_config = self.extensions_hub.get_default_pricing_config()

        trial_config = pricing_config.get("trial", {}) if pricing_config else {}

        # Default trial configuration
        defaults = {
            "enabled": False,
            "days": 7,
            "credits_usd": 5.00,  # $5 worth of credits
            "type": "credits",
            "requires_card": False,
            "description": "Free trial credits for new users",
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

        All new signups are now eligible for trial credits.
        The domain restriction has been removed.

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

        # Note: Business domain restriction removed - all signups get trial credits now
        # The is_free_email_provider check has been removed to allow all domains

        # RFC 2606 reserved test domains - always grant trial credits (for testing)
        # These domains can never be real domains and are safe for testing
        test_domains = {"example.com", "example.org", "example.net"}
        is_test_domain = domain.lower() in test_domains or domain.lower().endswith(
            ".test"
        )

        # Check if this is a public email provider (gmail, outlook, etc.)
        # Public email providers skip domain uniqueness - each user gets their own trial
        # Domain uniqueness only applies to business domains to prevent company abuse
        is_public_provider = self.is_free_email_provider(domain)

        # Check if domain already used trial (to prevent abuse)
        # Skip this check for:
        # 1. Test domains (so automated tests can run repeatedly)
        # 2. Public email providers (each individual user gets their own trial)
        close_session = False
        if session is None:
            session = get_session()
            close_session = True

        try:
            if (
                not is_test_domain
                and not is_public_provider
                and self.has_domain_used_trial(domain, session)
            ):
                return (
                    False,
                    "This email is not eligible for trial credits",
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

        # RFC 2606 reserved test domains - skip domain tracking
        test_domains = {"example.com", "example.org", "example.net"}
        is_test_domain = domain.lower() in test_domains or domain.lower().endswith(
            ".test"
        )

        # Check if this is a public email provider (gmail, outlook, etc.)
        # Public providers skip domain tracking - each user is treated as individual
        is_public_provider = self.is_free_email_provider(domain)

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
            # Skip this check for test domains and public email providers
            if not is_test_domain and not is_public_provider:
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

            # Record the trial domain (skip for test domains and public providers)
            # Only track business domains to prevent company-wide abuse
            if not is_test_domain and not is_public_provider:
                trial_domain = TrialDomain(
                    domain=domain.lower(),
                    company_id=company_id,
                    user_id=user_id,
                    credits_granted=credits_usd,
                )
                session.add(trial_domain)
                try:
                    session.flush()  # Force insert to catch unique constraint violation
                except Exception as e:
                    from sqlalchemy.exc import IntegrityError

                    if isinstance(e, IntegrityError):
                        session.rollback()
                        return (
                            False,
                            "This email is not eligible for trial credits",
                            None,
                        )
                    raise

            # Grant credits to company via add_tokens_to_company (resolves root parent)
            company.trial_credits_granted = credits_usd
            company.trial_credits_granted_at = datetime.now(timezone.utc)
            company.trial_domain = domain.lower()

            # For tiered_plan pricing, set the trial plan_id from pricing config
            # but only if the company doesn't already have a paid subscription
            pricing_config = self._get_pricing_config()
            pricing_model = (
                pricing_config.get("pricing_model") if pricing_config else "per_token"
            )
            has_paid_subscription = (
                company.stripe_subscription_id
                and company.plan_id
                and company.plan_id
                != pricing_config.get("trial", {}).get("plan_id", "starter")
            )

            if pricing_model == "tiered_plan" and not has_paid_subscription:
                trial_config = pricing_config.get("trial", {})
                trial_plan_id = trial_config.get("plan_id", "starter")
                from MagicalAuth import MagicalAuth

                auth = MagicalAuth()
                auth.set_company_plan(
                    company_id=company_id,
                    plan_id=trial_plan_id,
                )
            elif pricing_model == "per_bed" and not has_paid_subscription:
                trial_config = pricing_config.get("trial", {})
                trial_beds = trial_config.get("units", 5)
                company.bed_limit = trial_beds
                company.plan_id = f"per_bed_{trial_beds}"

            # Calculate token amount and add via add_tokens_to_company (root parent aware)
            tokens_granted = 0
            try:
                from payments.stripe_service import PriceService

                price_service = PriceService()
                token_price = float(price_service.get_token_price())
                if token_price > 0:
                    tokens_granted = int((credits_usd / token_price) * 1_000_000)
            except Exception as e:
                logging.warning(f"Could not calculate token amount for trial: {e}")

            session.commit()

            # Add tokens via the root-parent-aware method
            if tokens_granted > 0:
                try:
                    from MagicalAuth import MagicalAuth

                    auth = MagicalAuth()
                    auth.add_tokens_to_company(
                        company_id=company_id,
                        token_amount=tokens_granted,
                        amount_usd=credits_usd,
                    )
                except Exception as e:
                    logging.warning(
                        f"Could not add tokens via add_tokens_to_company: {e}"
                    )
                    # Fallback: add directly
                    company.token_balance = (
                        company.token_balance or 0
                    ) + tokens_granted
                    company.token_balance_usd = (
                        company.token_balance_usd or 0
                    ) + credits_usd
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

                # Schedule async notification safely from sync context
                try:
                    loop = asyncio.get_running_loop()
                    # In an async context, schedule the coroutine thread-safely
                    import concurrent.futures

                    future = asyncio.run_coroutine_threadsafe(
                        send_discord_trial_notification(
                            email=email,
                            credits_usd=credits_usd,
                            domain=domain.lower(),
                            company_id=company_id,
                            company_name=company_name,
                        ),
                        loop,
                    )
                    # Don't block waiting for result
                except RuntimeError:
                    # No running loop — run synchronously in a new loop
                    asyncio.run(
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
