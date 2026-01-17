from Extensions import Extensions
import requests
import json
import logging
import asyncio
from typing import Dict, List, Any, Optional
from urllib.parse import urljoin
import base64
from fastapi import APIRouter, Request, Header, HTTPException, Depends
from pydantic import BaseModel
from MagicalAuth import MagicalAuth, verify_api_key  # type: ignore
from Globals import getenv  # type: ignore
from DB import (
    get_session,
    User,
    UserPreferences,
    Company,
    UserCompany,
    PaymentTransaction,
)  # type: ignore
from Models import Detail, WebhookModel  # type: ignore
import stripe as stripe_lib


# OAuth configuration for Stripe Connect (if implementing OAuth)
SCOPES = [
    "read_write",  # Stripe Connect scope
]
AUTHORIZE = "https://connect.stripe.com/oauth/authorize"
PKCE_REQUIRED = False


class StripeSSO:
    def __init__(self, access_token=None, refresh_token=None):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("STRIPE_CLIENT_ID")
        self.client_secret = getenv("STRIPE_CLIENT_SECRET")
        self.user_info = self.get_user_info() if access_token else None

    def get_new_token(self):
        logging.info("Attempting to refresh Stripe Connect access token...")

        response = requests.post(
            "https://connect.stripe.com/oauth/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )

        if response.status_code != 200:
            logging.error(f"Stripe token refresh failed: {response.text}")
            raise Exception(f"Stripe token refresh failed: {response.text}")

        token_data = response.json()
        if "access_token" in token_data:
            self.access_token = token_data["access_token"]

        return token_data

    def get_user_info(self):
        if not self.access_token:
            return None

        stripe_lib.api_key = self.access_token
        try:
            # Get account info using Stripe Connect token
            account = stripe_lib.Account.retrieve()
            return {
                "email": account.get("email", ""),
                "first_name": (
                    account.get("individual", {}).get("first_name", "")
                    if account.get("individual")
                    else ""
                ),
                "last_name": (
                    account.get("individual", {}).get("last_name", "")
                    if account.get("individual")
                    else ""
                ),
                "stripe_user_id": account.get("id", ""),
            }
        except Exception as e:
            logging.error(f"Error getting Stripe account info: {str(e)}")
            return None


def sso(code, redirect_uri=None) -> StripeSSO:
    """Handle Stripe Connect OAuth flow"""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    response = requests.post(
        "https://connect.stripe.com/oauth/token",
        data={
            "client_id": getenv("STRIPE_CLIENT_ID"),
            "client_secret": getenv("STRIPE_CLIENT_SECRET"),
            "code": code,
            "grant_type": "authorization_code",
        },
    )

    if response.status_code != 200:
        logging.error(f"Error getting Stripe Connect access token: {response.text}")
        return None

    data = response.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")

    return StripeSSO(access_token=access_token, refresh_token=refresh_token)


# Pydantic models for API requests/responses
class CheckoutRequest(BaseModel):
    cart: List[Dict[str, Any]]


class stripe_payments(Extensions):
    """
    Stripe Payments Extension

    This extension integrates with Stripe, a leading payment processing platform that provides
    comprehensive payment infrastructure for online businesses. Stripe offers extensive payment
    capabilities and financial services for businesses of all sizes.

    The extension supports two authentication modes:
    1. OAuth via Stripe Connect (for managing other accounts)
    2. Direct API Key (for managing your own account)

    Stripe offers comprehensive payment processing including:
    - Payment processing for credit cards, digital wallets, and bank transfers
    - Subscription and recurring billing management
    - Customer management and billing profiles
    - Product and pricing catalog management
    - Invoice creation and management
    - Payment method management and tokenization
    - Dispute and chargeback handling
    - Comprehensive analytics and reporting
    - Multi-party payments and marketplace functionality
    - International payment support with currency conversion
    - Compliance and security features (PCI DSS)
    - Webhook integration for real-time notifications

    This extension provides commands to interact with the Stripe API
    to manage customers, payments, subscriptions, products, and invoices.

    Authentication:
    - OAuth via Stripe Connect (STRIPE_ACCESS_TOKEN)
    - Direct API Key (STRIPE_SECRET_KEY)
    """

    CATEGORY = "Finance & Crypto"
    friendly_name = "Stripe Payments"

    def __init__(self, **kwargs):
        """
        Initialize Stripe Payments extension

        Gets credentials from environment variables:
        - STRIPE_SECRET_KEY: Stripe secret API key (starts with sk_)
        - STRIPE_PUBLISHABLE_KEY: Stripe publishable API key (starts with pk_)
        - STRIPE_CLIENT_ID: For OAuth flows
        - STRIPE_CLIENT_SECRET: For OAuth flows
        """
        self.secret_key = getenv("STRIPE_SECRET_KEY", "")
        self.publishable_key = getenv("STRIPE_PUBLISHABLE_KEY", "")
        self.base_url = "https://api.stripe.com/v1"
        self.user_id = kwargs.get("user_id", kwargs.get("user", "default"))
        self.access_token = kwargs.get(
            "STRIPE_ACCESS_TOKEN", None
        )  # OAuth token from MagicalAuth
        self.auth = None

        # Configure base headers
        self.headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        # Always set up payment processing endpoints (for your business)
        self.router = APIRouter(tags=["Stripe", "Subscription"], prefix="")
        self._setup_routes()

        # Check for OAuth setup for user account access commands
        stripe_client_id = getenv("STRIPE_CLIENT_ID")
        stripe_client_secret = getenv("STRIPE_CLIENT_SECRET")

        if stripe_client_id and stripe_client_secret:
            # Define OAuth-based commands (only when OAuth is configured)
            self.commands = {
                "Get Stripe Customers": self.get_customers,
                "Get Stripe Customer Details": self.get_customer_details,
                "Create Stripe Customer": self.create_customer,
                "Get Stripe Payments": self.get_payments,
                "Get Stripe Payment Details": self.get_payment_details,
                "Get Stripe Subscriptions": self.get_subscriptions,
                "Get Stripe Subscription Details": self.get_subscription_details,
                "Get Stripe Products": self.get_products,
                "Get Stripe Product Details": self.get_product_details,
                "Get Stripe Invoices": self.get_invoices,
                "Get Stripe Invoice Details": self.get_invoice_details,
                "Get Stripe Balance": self.get_balance,
                "Get Stripe Overview": self.get_overview,
            }

            if kwargs.get("api_key"):
                try:
                    self.auth = MagicalAuth(token=kwargs.get("api_key"))
                    # Try to get OAuth token if available
                    token = self.auth.refresh_oauth_token(provider="stripe_payments")
                    if token:
                        self.access_token = token
                        self.headers["Authorization"] = f"Bearer {token}"
                        return  # OAuth token found, we're done
                except Exception as e:
                    logging.debug(f"No OAuth token available for Stripe: {e}")

        # Fall back to direct API key from environment if no OAuth token available
        if self.secret_key:
            self.headers["Authorization"] = f"Bearer {self.secret_key}"

    def _setup_routes(self):
        """Set up FastAPI routes for the Stripe extension"""

        @self.router.post(
            "/v1/webhook", response_model=WebhookModel, tags=["Subscription"]
        )
        async def webhook(request: Request):
            """Stripe webhook endpoint for handling subscription events"""
            if getenv("STRIPE_WEBHOOK_SECRET") == "":
                raise HTTPException(status_code=404, detail="Webhook not configured")

            session = get_session()
            try:
                event = None
                data = None
                webhook_data = (await request.body()).decode("utf-8")
                logging.info(f"Webhook data: {webhook_data}")

                try:
                    event = stripe_lib.Webhook.construct_event(
                        payload=(await request.body()).decode("utf-8"),
                        sig_header=request.headers.get("stripe-signature"),
                        secret=getenv("STRIPE_WEBHOOK_SECRET"),
                    )
                    data = event["data"]["object"]
                except stripe_lib.error.SignatureVerificationError as e:
                    logging.debug(f"Webhook signature verification failed: {str(e)}.")
                    session.close()
                    raise HTTPException(
                        status_code=400, detail="Webhook signature verification failed."
                    )

                logging.debug(f"Stripe Webhook Event of type {event['type']} received")

                if event and event["type"] == "checkout.session.completed":
                    logging.debug("Checkout session completed.")
                    email = data["customer_details"]["email"]
                    user = session.query(User).filter_by(email=email).first()
                    stripe_id = data["customer"]
                    status = data["payment_status"]

                    if not user:
                        logging.debug("User not found.")
                        session.close()
                        return {"success": "false"}

                    # Update stripe_id preference
                    stripe_pref = (
                        session.query(UserPreferences)
                        .filter_by(user_id=user.id, pref_key="stripe_id")
                        .first()
                    )

                    if not stripe_pref:
                        stripe_pref = UserPreferences(
                            user_id=user.id, pref_key="stripe_id", pref_value=stripe_id
                        )
                        session.add(stripe_pref)
                    else:
                        stripe_pref.pref_value = stripe_id

                    # Only activate if payment is successful
                    if status == "paid":
                        user.is_active = True

                        # Retrieve subscription data to get quantity
                        if "subscription" in data:
                            try:
                                subscription = stripe_lib.Subscription.retrieve(
                                    data["subscription"], expand=["items.data.price"]
                                )

                                # Get quantity from subscription (assuming first item)
                                if (
                                    subscription
                                    and subscription.items
                                    and subscription.items.data
                                ):
                                    quantity = subscription.items.data[0].quantity

                                    # Store user_limit in preferences
                                    user_limit_pref = (
                                        session.query(UserPreferences)
                                        .filter_by(
                                            user_id=user.id, pref_key="user_limit"
                                        )
                                        .first()
                                    )

                                    if not user_limit_pref:
                                        user_limit_pref = UserPreferences(
                                            user_id=user.id,
                                            pref_key="user_limit",
                                            pref_value=str(quantity),
                                        )
                                        session.add(user_limit_pref)
                                    else:
                                        user_limit_pref.pref_value = str(quantity)

                                    # Update company user_limit if user has a company
                                    user_company = (
                                        session.query(UserCompany)
                                        .filter(UserCompany.user_id == user.id)
                                        .first()
                                    )

                                    if user_company:
                                        company = (
                                            session.query(Company)
                                            .filter(
                                                Company.id == user_company.company_id
                                            )
                                            .first()
                                        )
                                        if company:
                                            company.user_limit = quantity

                                    # Store subscription ID for future reference
                                    sub_id_pref = (
                                        session.query(UserPreferences)
                                        .filter_by(
                                            user_id=user.id, pref_key="subscription_id"
                                        )
                                        .first()
                                    )

                                    if not sub_id_pref:
                                        sub_id_pref = UserPreferences(
                                            user_id=user.id,
                                            pref_key="subscription_id",
                                            pref_value=subscription.id,
                                        )
                                        session.add(sub_id_pref)
                                    else:
                                        sub_id_pref.pref_value = subscription.id
                            except Exception as e:
                                logging.error(
                                    f"Error retrieving subscription details: {str(e)}"
                                )

                    session.commit()
                    session.close()
                    return {"success": "true"}

                elif event and event["type"] == "customer.subscription.updated":
                    logging.debug("Customer Subscription updated.")
                    subscription = data
                    customer_id = subscription["customer"]

                    # Find users with this customer ID
                    stripe_prefs = (
                        session.query(UserPreferences)
                        .filter(UserPreferences.pref_key == "stripe_id")
                        .filter(UserPreferences.pref_value == customer_id)
                        .all()
                    )

                    for pref in stripe_prefs:
                        user_id = pref.user_id
                        user = session.query(User).filter(User.id == user_id).first()

                        if user:
                            # Check if this is the subscription we're tracking
                            sub_id_pref = (
                                session.query(UserPreferences)
                                .filter_by(user_id=user_id, pref_key="subscription_id")
                                .first()
                            )

                            if (
                                sub_id_pref
                                and sub_id_pref.pref_value == subscription["id"]
                            ):
                                # Update user limit based on new subscription details
                                if subscription["items"]["data"]:
                                    new_quantity = subscription["items"]["data"][0][
                                        "quantity"
                                    ]

                                    user_limit_pref = (
                                        session.query(UserPreferences)
                                        .filter_by(
                                            user_id=user_id, pref_key="user_limit"
                                        )
                                        .first()
                                    )

                                    if not user_limit_pref:
                                        user_limit_pref = UserPreferences(
                                            user_id=user_id,
                                            pref_key="user_limit",
                                            pref_value=str(new_quantity),
                                        )
                                        session.add(user_limit_pref)
                                    else:
                                        user_limit_pref.pref_value = str(new_quantity)

                                    # Update company user_limit if user has a company
                                    user_company = (
                                        session.query(UserCompany)
                                        .filter(UserCompany.user_id == user_id)
                                        .first()
                                    )

                                    if user_company:
                                        company = (
                                            session.query(Company)
                                            .filter(
                                                Company.id == user_company.company_id
                                            )
                                            .first()
                                        )
                                        if company:
                                            company.user_limit = new_quantity

                                    # Update status based on subscription status
                                    if subscription["status"] == "active":
                                        user.is_active = True
                                    else:
                                        user.is_active = False

                    session.commit()
                    session.close()
                    return {"success": "true"}

                elif event and event["type"] == "customer.subscription.deleted":
                    logging.debug("Customer Subscription cancelled.")
                    customer_id = data["customer"]

                    # Find users with this customer ID
                    stripe_prefs = (
                        session.query(UserPreferences)
                        .filter(UserPreferences.pref_key == "stripe_id")
                        .filter(UserPreferences.pref_value == customer_id)
                        .all()
                    )

                    for pref in stripe_prefs:
                        user = (
                            session.query(User).filter(User.id == pref.user_id).first()
                        )
                        if user:
                            user.is_active = False

                            # Reset user limit to 0
                            user_limit_pref = (
                                session.query(UserPreferences)
                                .filter_by(user_id=user.id, pref_key="user_limit")
                                .first()
                            )

                            if user_limit_pref:
                                user_limit_pref.pref_value = "0"

                            # Reset company user_limit to 1 (default)
                            user_company = (
                                session.query(UserCompany)
                                .filter(UserCompany.user_id == user.id)
                                .first()
                            )

                            if user_company:
                                company = (
                                    session.query(Company)
                                    .filter(Company.id == user_company.company_id)
                                    .first()
                                )
                                if company:
                                    company.user_limit = 1

                    session.commit()
                    session.close()
                    return {"success": "true"}

                elif event and event["type"] == "payment_intent.succeeded":
                    logging.debug("Payment Intent succeeded.")
                    payment_intent_id = data["id"]

                    # Find the payment transaction
                    transaction = (
                        session.query(PaymentTransaction)
                        .filter(
                            PaymentTransaction.stripe_payment_intent_id
                            == payment_intent_id
                        )
                        .first()
                    )

                    if transaction:
                        # Update transaction status
                        transaction.status = "completed"

                        # If this is a token purchase, credit the company
                        if transaction.token_amount and transaction.company_id:
                            from MagicalAuth import MagicalAuth

                            auth = MagicalAuth()
                            auth.add_tokens_to_company(
                                company_id=transaction.company_id,
                                token_amount=transaction.token_amount,
                                amount_usd=float(transaction.amount_usd),
                            )
                            logging.info(
                                f"Credited {transaction.token_amount} tokens to company {transaction.company_id}"
                            )
                            # Send Discord notification for token top-up
                            try:
                                from middleware import send_discord_topup_notification

                                # Get user email from transaction
                                user_email = "Unknown"
                                if transaction.user_id:
                                    user = (
                                        session.query(User)
                                        .filter(User.id == transaction.user_id)
                                        .first()
                                    )
                                    if user:
                                        user_email = user.email
                                asyncio.create_task(
                                    send_discord_topup_notification(
                                        email=user_email,
                                        amount_usd=float(transaction.amount_usd),
                                        tokens=transaction.token_amount,
                                        company_id=str(transaction.company_id),
                                    )
                                )
                            except Exception as e:
                                logging.warning(
                                    f"Failed to send Discord notification: {e}"
                                )

                        # If this is a seat-based payment, update user and company limits
                        elif transaction.seat_count and transaction.seat_count > 0:
                            # Activate the user
                            user_email = "Unknown"
                            if transaction.user_id:
                                user_obj = (
                                    session.query(User)
                                    .filter(User.id == transaction.user_id)
                                    .first()
                                )
                                if user_obj:
                                    user_obj.is_active = True
                                    user_email = user_obj.email
                                    logging.info(
                                        f"Activated user {transaction.user_id} after Stripe payment"
                                    )

                            # Update company for seat-based subscription
                            user_company = None
                            company_id_for_notification = None
                            if transaction.user_id:
                                user_company = (
                                    session.query(UserCompany)
                                    .filter(UserCompany.user_id == transaction.user_id)
                                    .first()
                                )

                            if user_company:
                                company = (
                                    session.query(Company)
                                    .filter(Company.id == user_company.company_id)
                                    .first()
                                )
                                if company:
                                    company.user_limit = transaction.seat_count
                                    # Set payment_intent_id as a pseudo-subscription ID for seat validation
                                    # This satisfies the _has_sufficient_token_balance check
                                    company.stripe_subscription_id = payment_intent_id
                                    company.auto_topup_enabled = True
                                    company_id_for_notification = str(company.id)
                                    logging.info(
                                        f"Updated company {company.id} user_limit to {transaction.seat_count} "
                                        f"and enabled subscription for Stripe payment"
                                    )
                                else:
                                    logging.warning(
                                        f"Company not found for user_company.company_id={user_company.company_id} "
                                        f"during Stripe webhook seat-based payment"
                                    )
                            else:
                                logging.warning(
                                    f"UserCompany not found for user_id={transaction.user_id} "
                                    f"during Stripe webhook seat-based payment"
                                )

                            # Send Discord notification for subscription payment (always attempt)
                            try:
                                from middleware import (
                                    send_discord_subscription_notification,
                                )
                                from ExtensionsHub import ExtensionsHub

                                hub = ExtensionsHub()
                                pricing_config = hub.get_pricing_config()
                                pricing_model = (
                                    pricing_config.get("pricing_model")
                                    if pricing_config
                                    else None
                                )

                                asyncio.create_task(
                                    send_discord_subscription_notification(
                                        email=user_email,
                                        seat_count=transaction.seat_count,
                                        amount_usd=float(transaction.amount_usd),
                                        company_id=company_id_for_notification,
                                        pricing_model=pricing_model,
                                    )
                                )
                            except Exception as e:
                                logging.warning(
                                    f"Failed to send Discord subscription notification: {e}"
                                )

                    session.commit()
                    session.close()
                    return {"success": "true"}

                elif event and event["type"] == "checkout.session.completed":
                    # Check if this is an auto top-up subscription checkout
                    session_data = data
                    if session_data.get("mode") == "subscription":
                        metadata = session_data.get("metadata", {})
                        if metadata.get("type") == "auto_topup_subscription":
                            company_id = metadata.get("company_id")
                            amount_usd = float(metadata.get("amount_usd", 0))
                            subscription_id = session_data.get("subscription")

                            if company_id and subscription_id:
                                # Get app name for tracking
                                from ExtensionsHub import ExtensionsHub
                                from datetime import datetime

                                hub = ExtensionsHub()
                                pricing_config = hub.get_pricing_config()
                                app_name = (
                                    pricing_config.get("app_name")
                                    if pricing_config
                                    else None
                                )
                                if not app_name:
                                    app_name = getenv("APP_NAME") or "AGiXT"

                                # Update company with subscription info
                                company = (
                                    session.query(Company)
                                    .filter(Company.id == company_id)
                                    .first()
                                )
                                if company:
                                    company.auto_topup_enabled = True
                                    company.auto_topup_amount_usd = amount_usd
                                    company.stripe_subscription_id = subscription_id
                                    company.app_name = app_name
                                    company.last_subscription_billing_date = (
                                        datetime.now()
                                    )
                                    logging.info(
                                        f"Auto top-up subscription activated for {app_name} company {company_id}: ${amount_usd}/month"
                                    )

                    session.commit()
                    session.close()
                    return {"success": "true"}

                elif event and event["type"] == "invoice.payment_succeeded":
                    # Handle successful subscription invoice payment
                    invoice = data
                    subscription_id = invoice.get("subscription")

                    if subscription_id:
                        # Find company with this subscription
                        company = (
                            session.query(Company)
                            .filter(Company.stripe_subscription_id == subscription_id)
                            .first()
                        )

                        if company and company.auto_topup_enabled:
                            # Get the amount paid from the invoice
                            amount_cents = invoice.get("amount_paid", 0)
                            amount_usd = amount_cents / 100.0

                            if amount_usd > 0:
                                # Get per-app pricing from extension hub
                                from ExtensionsHub import ExtensionsHub
                                from datetime import datetime

                                hub = ExtensionsHub()
                                pricing_config = hub.get_pricing_config()

                                # Get app name and pricing model from config
                                app_name = (
                                    pricing_config.get("app_name")
                                    if pricing_config
                                    else None
                                )
                                if not app_name:
                                    app_name = getenv("APP_NAME") or "AGiXT"

                                pricing_model = (
                                    pricing_config.get("pricing_model")
                                    if pricing_config
                                    else "per_token"
                                )

                                # For seat-based billing, apply any available credits first
                                credits_applied = 0.0
                                if pricing_model in [
                                    "per_user",
                                    "per_capacity",
                                    "per_location",
                                ]:
                                    # Check if company has credits to apply
                                    available_credits = company.token_balance_usd or 0.0
                                    if available_credits > 0:
                                        # Apply credits up to the subscription amount
                                        credits_applied = min(
                                            available_credits, amount_usd
                                        )
                                        company.token_balance_usd = (
                                            available_credits - credits_applied
                                        )

                                        # Also deduct proportional tokens
                                        if (
                                            company.token_balance
                                            and company.token_balance > 0
                                        ):
                                            token_price_per_million = float(
                                                getenv(
                                                    "TOKEN_PRICE_PER_MILLION_USD",
                                                    "0.50",
                                                )
                                            )
                                            if token_price_per_million > 0:
                                                tokens_to_deduct = int(
                                                    (
                                                        credits_applied
                                                        / token_price_per_million
                                                    )
                                                    * 1_000_000
                                                )
                                                company.token_balance = max(
                                                    0,
                                                    company.token_balance
                                                    - tokens_to_deduct,
                                                )

                                        logging.info(
                                            f"Applied ${credits_applied:.2f} credits for {app_name} company {company.id}"
                                        )

                                    # For seat-based, we don't add tokens - the payment is for seat access
                                    # Update company's app tracking and billing date
                                    company.app_name = app_name
                                    company.last_subscription_billing_date = (
                                        datetime.now()
                                    )

                                    # Create payment transaction record
                                    invoice_id = invoice.get("id", "unknown")
                                    transaction = PaymentTransaction(
                                        user_id=None,
                                        company_id=str(company.id),
                                        seat_count=int(company.user_limit or 1),
                                        token_amount=0,  # No tokens for seat-based billing
                                        payment_method="stripe_subscription",
                                        currency="USD",
                                        network="stripe",
                                        amount_usd=amount_usd,
                                        amount_currency=amount_usd,
                                        exchange_rate=1.0,
                                        stripe_payment_intent_id=invoice_id,
                                        status="completed",
                                        reference_code=f"SUB_{subscription_id[:20]}_{invoice_id[:20]}",
                                        app_name=app_name,
                                        metadata=(
                                            {
                                                "credits_applied": credits_applied,
                                                "net_charge": amount_usd
                                                - credits_applied,
                                                "pricing_model": pricing_model,
                                            }
                                            if credits_applied > 0
                                            else {}
                                        ),
                                    )
                                    session.add(transaction)

                                    logging.info(
                                        f"Seat-based subscription for {app_name}: ${amount_usd} charged, ${credits_applied:.2f} credits applied for company {company.id}"
                                    )

                                    # Send Discord notification for subscription payment (seat-based)
                                    try:
                                        from middleware import (
                                            send_discord_subscription_notification,
                                        )

                                        company_email = company.email or "Unknown"
                                        asyncio.create_task(
                                            send_discord_subscription_notification(
                                                email=company_email,
                                                seat_count=int(company.user_limit or 1),
                                                amount_usd=float(amount_usd),
                                                company_id=str(company.id),
                                                pricing_model=pricing_model,
                                            )
                                        )
                                    except Exception as e:
                                        logging.warning(
                                            f"Failed to send Discord subscription notification: {e}"
                                        )
                                else:
                                    # Token-based billing - add tokens to balance
                                    token_price_per_million = float(
                                        getenv("TOKEN_PRICE_PER_MILLION_USD", "0.50")
                                    )
                                    if token_price_per_million <= 0:
                                        token_price_per_million = 0.50

                                    token_millions = (
                                        amount_usd / token_price_per_million
                                    )
                                    tokens = int(token_millions * 1_000_000)

                                    # Credit tokens to company
                                    company.token_balance = (
                                        company.token_balance or 0
                                    ) + tokens
                                    company.token_balance_usd = (
                                        company.token_balance_usd or 0.0
                                    ) + amount_usd

                                    # Update company's app tracking
                                    company.app_name = app_name
                                    company.last_subscription_billing_date = (
                                        datetime.now()
                                    )

                                    # Create payment transaction record with app_name
                                    invoice_id = invoice.get("id", "unknown")
                                    transaction = PaymentTransaction(
                                        user_id=None,
                                        company_id=str(company.id),
                                        seat_count=0,
                                        token_amount=tokens,
                                        payment_method="stripe_subscription",
                                        currency="USD",
                                        network="stripe",
                                        amount_usd=amount_usd,
                                        amount_currency=amount_usd,
                                        exchange_rate=1.0,
                                        stripe_payment_intent_id=invoice_id,
                                        status="completed",
                                        reference_code=f"SUB_{subscription_id[:20]}_{invoice_id[:20]}",
                                        app_name=app_name,
                                    )
                                    session.add(transaction)

                                    logging.info(
                                        f"Auto top-up for {app_name}: Credited {tokens} tokens (${amount_usd}) to company {company.id}"
                                    )

                    session.commit()
                    session.close()
                    return {"success": "true"}

                elif event and event["type"] == "invoice.payment_failed":
                    # Handle failed subscription payment
                    invoice = data
                    subscription_id = invoice.get("subscription")

                    if subscription_id:
                        company = (
                            session.query(Company)
                            .filter(Company.stripe_subscription_id == subscription_id)
                            .first()
                        )

                        if company:
                            logging.warning(
                                f"Auto top-up payment failed for company {company.id}"
                            )
                            # Optionally notify or take action on payment failure

                    session.close()
                    return {"success": "true"}

                else:
                    session.close()
                    return {"success": "true"}

            except Exception as e:
                logging.error(f"Error processing webhook: {str(e)}")
                session.rollback()
                session.close()
                return {"success": "false"}

        @self.router.get(
            "/v1/products", response_model=List[dict], tags=["Subscription"]
        )
        async def get_products():
            """Get Stripe products endpoint - uses business environment variables only"""
            try:
                # Always use environment variable for business Stripe account (not user OAuth)
                api_key = getenv("STRIPE_SECRET_KEY")
                if not api_key:
                    logging.warning(
                        "No Stripe API key configured, returning empty products list"
                    )
                    return []

                stripe_lib.api_key = api_key
                app_name = getenv("APP_NAME")

                # Get all active prices with their products
                all_prices = stripe_lib.Price.list(
                    active=True,
                    expand=["data.product"],
                )["data"]

                # Filter prices - more lenient filtering
                filtered_prices = []
                for price in all_prices:
                    if not price.product.active:
                        continue

                    # If APP_NAME is configured, filter by it, otherwise include all products
                    if app_name:
                        product_app_name = price.product.metadata.get("APP_NAME")
                        if product_app_name and product_app_name != app_name:
                            continue

                    filtered_prices.append(price)

                if not filtered_prices:
                    logging.warning(
                        f"No products found matching APP_NAME '{app_name}' or no products configured"
                    )
                    return []

                # Group prices by product
                products = []
                for price in filtered_prices:
                    product_id = price["product"]["id"]
                    product_index = next(
                        (
                            i
                            for i, d in enumerate(products)
                            if d["product"]["id"] == product_id
                        ),
                        None,
                    )
                    if product_index is None:
                        products.append(
                            {"product": price["product"], "prices": [price]}
                        )
                    else:
                        products[product_index]["prices"].append(price)

                # Convert to final format
                final_products = []
                for product in products:
                    try:
                        product_ref = product["product"].__dict__["_previous"]
                        final_products.append(product_ref)
                        product_ref["prices"] = [
                            price.__dict__["_previous"] for price in product["prices"]
                        ]
                        for price in product_ref["prices"]:
                            if "product" in price:
                                del price["product"]
                    except (KeyError, AttributeError) as e:
                        logging.error(
                            f"Error processing product {product.get('product', {}).get('id', 'unknown')}: {str(e)}"
                        )
                        continue

                logging.info(f"Returning {len(final_products)} products")
                return final_products

            except Exception as e:
                logging.error(f"Error fetching products: {str(e)}")
                return []

        @self.router.post("/v1/checkout", response_model=Detail, tags=["Subscription"])
        async def checkout(
            request: Request,
            authorization: str = Header(None),
        ):
            """Stripe checkout endpoint - uses business environment variables only"""
            # Always use environment variable for business Stripe account (not user OAuth)
            api_key = getenv("STRIPE_SECRET_KEY")
            if not api_key:
                raise HTTPException(
                    status_code=500, detail="Stripe API key not configured"
                )

            stripe_lib.api_key = api_key
            data = await request.json()
            auth = MagicalAuth(token=authorization)
            try:
                customer_id = auth.get_user_preferences()["stripe_customer_id"]
            except Exception as e:
                customer_id = e.__dict__["detail"]["customer_id"]

            checkout_session = stripe_lib.checkout.Session.create(
                customer=customer_id,
                line_items=data["cart"],
                mode="subscription",
                success_url=getenv("APP_URI"),
                cancel_url=getenv("APP_URI"),
            )
            return Detail(detail=checkout_session["url"])

    def _make_request(
        self, endpoint: str, method: str = "GET", params: Dict = None, data: Dict = None
    ) -> Dict:
        """
        Make authenticated request to Stripe API

        Args:
            endpoint: API endpoint path
            method: HTTP method (GET, POST, PUT, DELETE)
            params: Query parameters
            data: Request body data

        Returns:
            Dict: API response data
        """
        api_key = self.access_token if self.access_token else self.secret_key
        if not api_key:
            return {"error": "Stripe API key or access token not configured"}

        url = urljoin(self.base_url, endpoint)

        try:
            # Convert data dict to form-encoded string for Stripe API
            form_data = None
            if data:
                form_data = "&".join([f"{k}={v}" for k, v in data.items()])

            if method.upper() == "GET":
                response = requests.get(
                    url, headers=self.headers, params=params, timeout=30
                )
            elif method.upper() == "POST":
                response = requests.post(
                    url, headers=self.headers, data=form_data, params=params, timeout=30
                )
            elif method.upper() == "PUT":
                response = requests.put(
                    url, headers=self.headers, data=form_data, params=params, timeout=30
                )
            elif method.upper() == "DELETE":
                response = requests.delete(
                    url, headers=self.headers, params=params, timeout=30
                )
            else:
                return {"error": f"Unsupported HTTP method: {method}"}

            if response.status_code in [200, 201, 202, 204]:
                return response.json() if response.content else {"success": True}
            else:
                logging.error(
                    f"Stripe API error: {response.status_code} - {response.text}"
                )
                return {
                    "error": f"API request failed: {response.status_code} - {response.text}"
                }

        except requests.exceptions.RequestException as e:
            logging.error(f"Stripe API request error: {str(e)}")
            return {"error": f"Request failed: {str(e)}"}

    def verify_user(self):
        """Verify the user by checking Stripe account access"""
        if not self.auth:
            return False

        try:
            # Get fresh OAuth token similar to Microsoft
            token = self.auth.refresh_oauth_token(provider="stripe_payments")
            if token:
                self.access_token = token
                self.headers["Authorization"] = f"Bearer {token}"

                # Test the token by fetching account info
                response = self._make_request("GET", "/account")
                return response.get("id") is not None
        except Exception as e:
            logging.error(f"Error verifying Stripe user: {str(e)}")

        return False

    def _format_amount(self, amount: int, currency: str = "usd") -> str:
        """Format Stripe amount (cents) to human readable format"""
        if currency.lower() in ["jpy", "krw"]:  # Zero-decimal currencies
            return f"{amount} {currency.upper()}"
        else:
            return f"{amount / 100:.2f} {currency.upper()}"

    async def get_customers(self, limit: int = 10, email: str = None) -> str:
        """
        Get customers from Stripe

        Args:
            limit (int): Maximum number of customers to retrieve (default: 10)
            email (str): Filter by customer email (optional)

        Returns:
            str: Formatted list of customers
        """
        try:
            # Verify authentication first
            if self.auth and self.access_token:
                self.verify_user()

            params = {"limit": limit}
            if email:
                params["email"] = email

            data = self._make_request("/customers", params=params)

            if "error" in data:
                return f"Error retrieving customers: {data['error']}"

            customers = data.get("data", [])
            if not customers:
                return "No customers found in Stripe."

            result_lines = [f"# Stripe Customers ({len(customers)} found)\n"]

            for customer in customers:
                result_lines.extend(
                    [
                        f"## {customer.get('name', customer.get('email', 'Unknown'))}",
                        f"- **Customer ID**: {customer.get('id', 'N/A')}",
                        f"- **Email**: {customer.get('email', 'N/A')}",
                        f"- **Name**: {customer.get('name', 'N/A')}",
                        f"- **Phone**: {customer.get('phone', 'N/A')}",
                        f"- **Created**: {customer.get('created', 'N/A')}",
                        f"- **Default Source**: {customer.get('default_source', 'N/A')}",
                        f"- **Balance**: {self._format_amount(customer.get('balance', 0))}",
                        f"- **Delinquent**: {customer.get('delinquent', 'N/A')}",
                        "",
                    ]
                )

            has_more = data.get("has_more", False)
            if has_more:
                result_lines.append(
                    "*Note: More customers available. Use a higher limit to retrieve more.*"
                )

            return "\n".join(result_lines)

        except Exception as e:
            logging.error(f"Error getting Stripe customers: {str(e)}")
            return f"Error getting customers: {str(e)}"

    async def get_customer_details(self, customer_id: str) -> str:
        """
        Get detailed information about a specific customer

        Args:
            customer_id (str): The Stripe customer ID

        Returns:
            str: Detailed customer information
        """
        try:
            data = self._make_request(f"/customers/{customer_id}")

            if "error" in data:
                return f"Error retrieving customer details: {data['error']}"

            result_lines = [
                f"# Customer Details: {data.get('name', data.get('email', 'Unknown'))}\n",
                f"- **Customer ID**: {data.get('id', 'N/A')}",
                f"- **Email**: {data.get('email', 'N/A')}",
                f"- **Name**: {data.get('name', 'N/A')}",
                f"- **Phone**: {data.get('phone', 'N/A')}",
                f"- **Description**: {data.get('description', 'N/A')}",
                f"- **Created**: {data.get('created', 'N/A')}",
                f"- **Currency**: {data.get('currency', 'N/A')}",
                f"- **Balance**: {self._format_amount(data.get('balance', 0))}",
                f"- **Default Source**: {data.get('default_source', 'N/A')}",
                f"- **Delinquent**: {data.get('delinquent', 'N/A')}",
                f"- **Live Mode**: {data.get('livemode', 'N/A')}",
            ]

            # Add address information if available
            address = data.get("address", {})
            if address and any(address.values()):
                result_lines.extend(
                    [
                        "",
                        "## Address",
                        f"- **Line 1**: {address.get('line1', 'N/A')}",
                        f"- **Line 2**: {address.get('line2', 'N/A')}",
                        f"- **City**: {address.get('city', 'N/A')}",
                        f"- **State**: {address.get('state', 'N/A')}",
                        f"- **Postal Code**: {address.get('postal_code', 'N/A')}",
                        f"- **Country**: {address.get('country', 'N/A')}",
                    ]
                )

            # Add shipping information if available
            shipping = data.get("shipping", {})
            if shipping and any(shipping.values()):
                result_lines.extend(
                    [
                        "",
                        "## Shipping Address",
                        f"- **Name**: {shipping.get('name', 'N/A')}",
                        f"- **Phone**: {shipping.get('phone', 'N/A')}",
                    ]
                )
                ship_address = shipping.get("address", {})
                if ship_address:
                    result_lines.extend(
                        [
                            f"- **Line 1**: {ship_address.get('line1', 'N/A')}",
                            f"- **Line 2**: {ship_address.get('line2', 'N/A')}",
                            f"- **City**: {ship_address.get('city', 'N/A')}",
                            f"- **State**: {ship_address.get('state', 'N/A')}",
                            f"- **Postal Code**: {ship_address.get('postal_code', 'N/A')}",
                            f"- **Country**: {ship_address.get('country', 'N/A')}",
                        ]
                    )

            return "\n".join(result_lines)

        except Exception as e:
            logging.error(f"Error getting Stripe customer details: {str(e)}")
            return f"Error getting customer details: {str(e)}"

    async def create_customer(
        self, email: str, name: str = None, description: str = None
    ) -> str:
        """
        Create a new customer in Stripe

        Args:
            email (str): Customer email address
            name (str): Customer name (optional)
            description (str): Customer description (optional)

        Returns:
            str: Result of customer creation
        """
        try:
            data = {"email": email}
            if name:
                data["name"] = name
            if description:
                data["description"] = description

            response_data = self._make_request("/customers", method="POST", data=data)

            if "error" in response_data:
                return f"Error creating customer: {response_data['error']}"

            customer_id = response_data.get("id", "Unknown")
            return f"Successfully created customer: {customer_id} ({email})"

        except Exception as e:
            logging.error(f"Error creating Stripe customer: {str(e)}")
            return f"Error creating customer: {str(e)}"

    async def get_payments(self, limit: int = 10, customer_id: str = None) -> str:
        """
        Get payments (charges) from Stripe

        Args:
            limit (int): Maximum number of payments to retrieve (default: 10)
            customer_id (str): Filter by customer ID (optional)

        Returns:
            str: Formatted list of payments
        """
        try:
            params = {"limit": limit}
            if customer_id:
                params["customer"] = customer_id

            data = self._make_request("/charges", params=params)

            if "error" in data:
                return f"Error retrieving payments: {data['error']}"

            payments = data.get("data", [])
            if not payments:
                return "No payments found in Stripe."

            result_lines = [f"# Stripe Payments ({len(payments)} found)\n"]

            for payment in payments:
                result_lines.extend(
                    [
                        f"## {payment.get('id', 'Unknown')}",
                        f"- **Payment ID**: {payment.get('id', 'N/A')}",
                        f"- **Amount**: {self._format_amount(payment.get('amount', 0), payment.get('currency', 'usd'))}",
                        f"- **Status**: {payment.get('status', 'N/A')}",
                        f"- **Customer**: {payment.get('customer', 'N/A')}",
                        f"- **Description**: {payment.get('description', 'N/A')}",
                        f"- **Created**: {payment.get('created', 'N/A')}",
                        f"- **Paid**: {payment.get('paid', 'N/A')}",
                        f"- **Refunded**: {payment.get('refunded', 'N/A')}",
                        f"- **Source**: {payment.get('source', {}).get('brand', 'N/A')} ending in {payment.get('source', {}).get('last4', 'N/A')}",
                        "",
                    ]
                )

            has_more = data.get("has_more", False)
            if has_more:
                result_lines.append(
                    "*Note: More payments available. Use a higher limit to retrieve more.*"
                )

            return "\n".join(result_lines)

        except Exception as e:
            logging.error(f"Error getting Stripe payments: {str(e)}")
            return f"Error getting payments: {str(e)}"

    async def get_payment_details(self, payment_id: str) -> str:
        """
        Get detailed information about a specific payment

        Args:
            payment_id (str): The Stripe payment (charge) ID

        Returns:
            str: Detailed payment information
        """
        try:
            data = self._make_request(f"/charges/{payment_id}")

            if "error" in data:
                return f"Error retrieving payment details: {data['error']}"

            result_lines = [
                f"# Payment Details: {data.get('id', 'Unknown')}\n",
                f"- **Payment ID**: {data.get('id', 'N/A')}",
                f"- **Amount**: {self._format_amount(data.get('amount', 0), data.get('currency', 'usd'))}",
                f"- **Amount Captured**: {self._format_amount(data.get('amount_captured', 0), data.get('currency', 'usd'))}",
                f"- **Amount Refunded**: {self._format_amount(data.get('amount_refunded', 0), data.get('currency', 'usd'))}",
                f"- **Status**: {data.get('status', 'N/A')}",
                f"- **Customer**: {data.get('customer', 'N/A')}",
                f"- **Description**: {data.get('description', 'N/A')}",
                f"- **Created**: {data.get('created', 'N/A')}",
                f"- **Paid**: {data.get('paid', 'N/A')}",
                f"- **Captured**: {data.get('captured', 'N/A')}",
                f"- **Refunded**: {data.get('refunded', 'N/A')}",
                f"- **Disputed**: {data.get('disputed', 'N/A')}",
                f"- **Receipt Email**: {data.get('receipt_email', 'N/A')}",
                f"- **Receipt URL**: {data.get('receipt_url', 'N/A')}",
                f"- **Invoice**: {data.get('invoice', 'N/A')}",
                f"- **Live Mode**: {data.get('livemode', 'N/A')}",
            ]

            # Add billing details if available
            billing_details = data.get("billing_details", {})
            if billing_details and any(billing_details.values()):
                result_lines.extend(
                    [
                        "",
                        "## Billing Details",
                        f"- **Name**: {billing_details.get('name', 'N/A')}",
                        f"- **Email**: {billing_details.get('email', 'N/A')}",
                        f"- **Phone**: {billing_details.get('phone', 'N/A')}",
                    ]
                )

            # Add payment method details if available
            payment_method = data.get("payment_method_details", {})
            if payment_method:
                result_lines.extend(
                    [
                        "",
                        "## Payment Method",
                        f"- **Type**: {payment_method.get('type', 'N/A')}",
                    ]
                )
                card = payment_method.get("card", {})
                if card:
                    result_lines.extend(
                        [
                            f"- **Brand**: {card.get('brand', 'N/A')}",
                            f"- **Last 4**: {card.get('last4', 'N/A')}",
                            f"- **Exp Month**: {card.get('exp_month', 'N/A')}",
                            f"- **Exp Year**: {card.get('exp_year', 'N/A')}",
                            f"- **Country**: {card.get('country', 'N/A')}",
                        ]
                    )

            return "\n".join(result_lines)

        except Exception as e:
            logging.error(f"Error getting Stripe payment details: {str(e)}")
            return f"Error getting payment details: {str(e)}"

    async def get_subscriptions(
        self, limit: int = 10, customer_id: str = None, status: str = None
    ) -> str:
        """
        Get subscriptions from Stripe

        Args:
            limit (int): Maximum number of subscriptions to retrieve (default: 10)
            customer_id (str): Filter by customer ID (optional)
            status (str): Filter by status (active, canceled, incomplete, etc.) (optional)

        Returns:
            str: Formatted list of subscriptions
        """
        try:
            params = {"limit": limit}
            if customer_id:
                params["customer"] = customer_id
            if status:
                params["status"] = status

            data = self._make_request("/subscriptions", params=params)

            if "error" in data:
                return f"Error retrieving subscriptions: {data['error']}"

            subscriptions = data.get("data", [])
            if not subscriptions:
                return "No subscriptions found in Stripe."

            result_lines = [f"# Stripe Subscriptions ({len(subscriptions)} found)\n"]

            for subscription in subscriptions:
                result_lines.extend(
                    [
                        f"## {subscription.get('id', 'Unknown')}",
                        f"- **Subscription ID**: {subscription.get('id', 'N/A')}",
                        f"- **Customer**: {subscription.get('customer', 'N/A')}",
                        f"- **Status**: {subscription.get('status', 'N/A')}",
                        f"- **Current Period Start**: {subscription.get('current_period_start', 'N/A')}",
                        f"- **Current Period End**: {subscription.get('current_period_end', 'N/A')}",
                        f"- **Created**: {subscription.get('created', 'N/A')}",
                        f"- **Cancel At**: {subscription.get('cancel_at', 'N/A')}",
                        f"- **Canceled At**: {subscription.get('canceled_at', 'N/A')}",
                        "",
                    ]
                )

            has_more = data.get("has_more", False)
            if has_more:
                result_lines.append(
                    "*Note: More subscriptions available. Use a higher limit to retrieve more.*"
                )

            return "\n".join(result_lines)

        except Exception as e:
            logging.error(f"Error getting Stripe subscriptions: {str(e)}")
            return f"Error getting subscriptions: {str(e)}"

    async def get_subscription_details(self, subscription_id: str) -> str:
        """
        Get detailed information about a specific subscription

        Args:
            subscription_id (str): The Stripe subscription ID

        Returns:
            str: Detailed subscription information
        """
        try:
            data = self._make_request(f"/subscriptions/{subscription_id}")

            if "error" in data:
                return f"Error retrieving subscription details: {data['error']}"

            result_lines = [
                f"# Subscription Details: {data.get('id', 'Unknown')}\n",
                f"- **Subscription ID**: {data.get('id', 'N/A')}",
                f"- **Customer**: {data.get('customer', 'N/A')}",
                f"- **Status**: {data.get('status', 'N/A')}",
                f"- **Collection Method**: {data.get('collection_method', 'N/A')}",
                f"- **Current Period Start**: {data.get('current_period_start', 'N/A')}",
                f"- **Current Period End**: {data.get('current_period_end', 'N/A')}",
                f"- **Created**: {data.get('created', 'N/A')}",
                f"- **Start Date**: {data.get('start_date', 'N/A')}",
                f"- **Cancel At**: {data.get('cancel_at', 'N/A')}",
                f"- **Canceled At**: {data.get('canceled_at', 'N/A')}",
                f"- **Ended At**: {data.get('ended_at', 'N/A')}",
                f"- **Trial Start**: {data.get('trial_start', 'N/A')}",
                f"- **Trial End**: {data.get('trial_end', 'N/A')}",
            ]

            # Add subscription items if available
            items = data.get("items", {}).get("data", [])
            if items:
                result_lines.extend(
                    [
                        "",
                        "## Subscription Items",
                    ]
                )
                for item in items:
                    price = item.get("price", {})
                    result_lines.extend(
                        [
                            f"### Item: {item.get('id', 'Unknown')}",
                            f"- **Price ID**: {price.get('id', 'N/A')}",
                            f"- **Product**: {price.get('product', 'N/A')}",
                            f"- **Unit Amount**: {self._format_amount(price.get('unit_amount', 0), price.get('currency', 'usd'))}",
                            f"- **Recurring**: {price.get('recurring', {}).get('interval', 'N/A')}",
                            f"- **Quantity**: {item.get('quantity', 'N/A')}",
                        ]
                    )

            return "\n".join(result_lines)

        except Exception as e:
            logging.error(f"Error getting Stripe subscription details: {str(e)}")
            return f"Error getting subscription details: {str(e)}"

    async def get_products(self, limit: int = 10, active: bool = None) -> str:
        """
        Get products from Stripe

        Args:
            limit (int): Maximum number of products to retrieve (default: 10)
            active (bool): Filter by active status (optional)

        Returns:
            str: Formatted list of products
        """
        try:
            params = {"limit": limit}
            if active is not None:
                params["active"] = str(active).lower()

            data = self._make_request("/products", params=params)

            if "error" in data:
                return f"Error retrieving products: {data['error']}"

            products = data.get("data", [])
            if not products:
                return "No products found in Stripe."

            result_lines = [f"# Stripe Products ({len(products)} found)\n"]

            for product in products:
                result_lines.extend(
                    [
                        f"## {product.get('name', 'Unknown')}",
                        f"- **Product ID**: {product.get('id', 'N/A')}",
                        f"- **Name**: {product.get('name', 'N/A')}",
                        f"- **Description**: {product.get('description', 'N/A')}",
                        f"- **Active**: {product.get('active', 'N/A')}",
                        f"- **Type**: {product.get('type', 'N/A')}",
                        f"- **Created**: {product.get('created', 'N/A')}",
                        f"- **Updated**: {product.get('updated', 'N/A')}",
                        "",
                    ]
                )

            has_more = data.get("has_more", False)
            if has_more:
                result_lines.append(
                    "*Note: More products available. Use a higher limit to retrieve more.*"
                )

            return "\n".join(result_lines)

        except Exception as e:
            logging.error(f"Error getting Stripe products: {str(e)}")
            return f"Error getting products: {str(e)}"

    async def get_product_details(self, product_id: str) -> str:
        """
        Get detailed information about a specific product

        Args:
            product_id (str): The Stripe product ID

        Returns:
            str: Detailed product information
        """
        try:
            data = self._make_request(f"/products/{product_id}")

            if "error" in data:
                return f"Error retrieving product details: {data['error']}"

            result_lines = [
                f"# Product Details: {data.get('name', 'Unknown')}\n",
                f"- **Product ID**: {data.get('id', 'N/A')}",
                f"- **Name**: {data.get('name', 'N/A')}",
                f"- **Description**: {data.get('description', 'N/A')}",
                f"- **Active**: {data.get('active', 'N/A')}",
                f"- **Type**: {data.get('type', 'N/A')}",
                f"- **Created**: {data.get('created', 'N/A')}",
                f"- **Updated**: {data.get('updated', 'N/A')}",
                f"- **Shippable**: {data.get('shippable', 'N/A')}",
                f"- **Unit Label**: {data.get('unit_label', 'N/A')}",
                f"- **URL**: {data.get('url', 'N/A')}",
            ]

            # Add images if available
            images = data.get("images", [])
            if images:
                result_lines.extend(
                    [
                        "",
                        "## Images",
                    ]
                )
                for i, image_url in enumerate(images, 1):
                    result_lines.append(f"- **Image {i}**: {image_url}")

            return "\n".join(result_lines)

        except Exception as e:
            logging.error(f"Error getting Stripe product details: {str(e)}")
            return f"Error getting product details: {str(e)}"

    async def get_invoices(
        self, limit: int = 10, customer_id: str = None, status: str = None
    ) -> str:
        """
        Get invoices from Stripe

        Args:
            limit (int): Maximum number of invoices to retrieve (default: 10)
            customer_id (str): Filter by customer ID (optional)
            status (str): Filter by status (draft, open, paid, etc.) (optional)

        Returns:
            str: Formatted list of invoices
        """
        try:
            params = {"limit": limit}
            if customer_id:
                params["customer"] = customer_id
            if status:
                params["status"] = status

            data = self._make_request("/invoices", params=params)

            if "error" in data:
                return f"Error retrieving invoices: {data['error']}"

            invoices = data.get("data", [])
            if not invoices:
                return "No invoices found in Stripe."

            result_lines = [f"# Stripe Invoices ({len(invoices)} found)\n"]

            for invoice in invoices:
                result_lines.extend(
                    [
                        f"## {invoice.get('number', invoice.get('id', 'Unknown'))}",
                        f"- **Invoice ID**: {invoice.get('id', 'N/A')}",
                        f"- **Number**: {invoice.get('number', 'N/A')}",
                        f"- **Customer**: {invoice.get('customer', 'N/A')}",
                        f"- **Status**: {invoice.get('status', 'N/A')}",
                        f"- **Total**: {self._format_amount(invoice.get('total', 0), invoice.get('currency', 'usd'))}",
                        f"- **Amount Due**: {self._format_amount(invoice.get('amount_due', 0), invoice.get('currency', 'usd'))}",
                        f"- **Amount Paid**: {self._format_amount(invoice.get('amount_paid', 0), invoice.get('currency', 'usd'))}",
                        f"- **Created**: {invoice.get('created', 'N/A')}",
                        f"- **Due Date**: {invoice.get('due_date', 'N/A')}",
                        "",
                    ]
                )

            has_more = data.get("has_more", False)
            if has_more:
                result_lines.append(
                    "*Note: More invoices available. Use a higher limit to retrieve more.*"
                )

            return "\n".join(result_lines)

        except Exception as e:
            logging.error(f"Error getting Stripe invoices: {str(e)}")
            return f"Error getting invoices: {str(e)}"

    async def get_invoice_details(self, invoice_id: str) -> str:
        """
        Get detailed information about a specific invoice

        Args:
            invoice_id (str): The Stripe invoice ID

        Returns:
            str: Detailed invoice information
        """
        try:
            data = self._make_request(f"/invoices/{invoice_id}")

            if "error" in data:
                return f"Error retrieving invoice details: {data['error']}"

            result_lines = [
                f"# Invoice Details: {data.get('number', data.get('id', 'Unknown'))}\n",
                f"- **Invoice ID**: {data.get('id', 'N/A')}",
                f"- **Number**: {data.get('number', 'N/A')}",
                f"- **Customer**: {data.get('customer', 'N/A')}",
                f"- **Status**: {data.get('status', 'N/A')}",
                f"- **Description**: {data.get('description', 'N/A')}",
                f"- **Subtotal**: {self._format_amount(data.get('subtotal', 0), data.get('currency', 'usd'))}",
                f"- **Tax**: {self._format_amount(data.get('tax', 0), data.get('currency', 'usd'))}",
                f"- **Total**: {self._format_amount(data.get('total', 0), data.get('currency', 'usd'))}",
                f"- **Amount Due**: {self._format_amount(data.get('amount_due', 0), data.get('currency', 'usd'))}",
                f"- **Amount Paid**: {self._format_amount(data.get('amount_paid', 0), data.get('currency', 'usd'))}",
                f"- **Created**: {data.get('created', 'N/A')}",
                f"- **Due Date**: {data.get('due_date', 'N/A')}",
                f"- **Paid**: {data.get('paid', 'N/A')}",
                f"- **Attempt Count**: {data.get('attempt_count', 'N/A')}",
                f"- **Invoice PDF**: {data.get('invoice_pdf', 'N/A')}",
                f"- **Hosted Invoice URL**: {data.get('hosted_invoice_url', 'N/A')}",
            ]

            return "\n".join(result_lines)

        except Exception as e:
            logging.error(f"Error getting Stripe invoice details: {str(e)}")
            return f"Error getting invoice details: {str(e)}"

    async def get_balance(self) -> str:
        """
        Get Stripe account balance

        Returns:
            str: Account balance information
        """
        try:
            data = self._make_request("/balance")

            if "error" in data:
                return f"Error retrieving balance: {data['error']}"

            result_lines = [f"# Stripe Account Balance\n"]

            # Available balance
            available = data.get("available", [])
            if available:
                result_lines.append("## Available Balance")
                for balance in available:
                    result_lines.append(
                        f"- **{balance.get('currency', 'N/A').upper()}**: {self._format_amount(balance.get('amount', 0), balance.get('currency', 'usd'))}"
                    )
                result_lines.append("")

            # Pending balance
            pending = data.get("pending", [])
            if pending:
                result_lines.append("## Pending Balance")
                for balance in pending:
                    result_lines.append(
                        f"- **{balance.get('currency', 'N/A').upper()}**: {self._format_amount(balance.get('amount', 0), balance.get('currency', 'usd'))}"
                    )

            return "\n".join(result_lines)

        except Exception as e:
            logging.error(f"Error getting Stripe balance: {str(e)}")
            return f"Error getting balance: {str(e)}"

    async def get_overview(self) -> str:
        """
        Get Stripe account overview

        Returns:
            str: Stripe overview
        """
        try:
            # Get summary information from various endpoints
            customers_data = self._make_request("/customers", params={"limit": 1})
            payments_data = self._make_request("/charges", params={"limit": 1})
            subscriptions_data = self._make_request(
                "/subscriptions", params={"limit": 1}
            )
            products_data = self._make_request("/products", params={"limit": 1})
            invoices_data = self._make_request("/invoices", params={"limit": 1})
            balance_data = self._make_request("/balance")

            result_lines = [f"# Stripe Account Overview\n"]

            # Add counts
            if "error" not in customers_data:
                result_lines.append(
                    f"- **Total Customers**: ~{customers_data.get('total_count', 'N/A')}"
                )
            if "error" not in payments_data:
                result_lines.append(
                    f"- **Total Payments**: ~{payments_data.get('total_count', 'N/A')}"
                )
            if "error" not in subscriptions_data:
                result_lines.append(
                    f"- **Total Subscriptions**: ~{subscriptions_data.get('total_count', 'N/A')}"
                )
            if "error" not in products_data:
                result_lines.append(
                    f"- **Total Products**: ~{products_data.get('total_count', 'N/A')}"
                )
            if "error" not in invoices_data:
                result_lines.append(
                    f"- **Total Invoices**: ~{invoices_data.get('total_count', 'N/A')}"
                )

            # Add balance information
            if "error" not in balance_data:
                available = balance_data.get("available", [])
                if available:
                    result_lines.extend(
                        [
                            "",
                            "## Available Balance",
                        ]
                    )
                    for balance in available:
                        result_lines.append(
                            f"- **{balance.get('currency', 'N/A').upper()}**: {self._format_amount(balance.get('amount', 0), balance.get('currency', 'usd'))}"
                        )

            return "\n".join(result_lines)

        except Exception as e:
            logging.error(f"Error getting Stripe overview: {str(e)}")
            return f"Error getting overview: {str(e)}"
