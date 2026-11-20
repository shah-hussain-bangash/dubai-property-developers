"""Build the integration client set from settings.

Safe default: every integration runs in MOCK mode. A live client is only built
when ``INTEGRATIONS_MODE=live`` AND that integration's credentials are present.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.config.settings import Settings
from integrations.bayut import client as bayut
from integrations.espocrm.client import (
    CRMClient,
    EspoCRMConfig,
    HttpEspoCRMClient,
    MockEspoCRMClient,
)
from integrations.espocrm.client import descriptor as espocrm_descriptor
from integrations.google.client import CalendarClient, GoogleConfig, MockCalendarClient
from integrations.google.client import descriptor as google_descriptor
from integrations.listing_portal import ListingPortalClient
from integrations.meta.client import (
    HttpWhatsAppClient,
    MetaWhatsAppConfig,
    MockWhatsAppClient,
    WhatsAppClient,
)
from integrations.meta.client import descriptor as meta_descriptor
from integrations.n8n.client import HttpN8nClient, MockN8nClient, N8nClient, N8nConfig
from integrations.n8n.client import descriptor as n8n_descriptor
from integrations.propertyfinder import client as propertyfinder
from integrations.slack.client import (
    MockSlackNotifier,
    SlackConfig,
    SlackNotifier,
    WebhookSlackNotifier,
)
from integrations.slack.client import descriptor as slack_descriptor
from integrations.telephony.client import MockTelephonyClient, TelephonyClient, TelephonyConfig
from integrations.telephony.client import descriptor as telephony_descriptor
from schemas.integrations.models import IntegrationDescriptor, IntegrationMode


@dataclass
class IntegrationSet:
    crm: CRMClient
    whatsapp: WhatsAppClient
    calendar: CalendarClient
    bayut: ListingPortalClient
    propertyfinder: ListingPortalClient
    telephony: TelephonyClient
    n8n: N8nClient
    slack: SlackNotifier
    descriptors: list[IntegrationDescriptor] = field(default_factory=list)


def _mode(settings: Settings, configured: bool) -> IntegrationMode:
    if settings.integrations_mode == IntegrationMode.LIVE and configured:
        return IntegrationMode.LIVE
    return IntegrationMode.MOCK


def build_integrations(settings: Settings) -> IntegrationSet:
    espo = EspoCRMConfig(base_url=settings.espocrm_base_url, api_key=settings.espocrm_api_key)
    espo.mode = _mode(settings, espo.is_configured)
    meta = MetaWhatsAppConfig(
        phone_number_id=settings.meta_whatsapp_phone_number_id,
        access_token=settings.meta_whatsapp_access_token,
        app_secret=settings.meta_app_secret,
        api_version=settings.meta_graph_api_version,
    )
    meta.mode = _mode(settings, meta.is_configured)
    google = GoogleConfig(credentials_file=settings.google_credentials_file)  # mock only for now
    bayut_cfg = bayut.BayutConfig()
    pf_cfg = propertyfinder.PropertyFinderConfig()
    telephony = TelephonyConfig(provider=settings.telephony_provider)  # mock only for now
    n8n = N8nConfig(webhook_base_url=settings.n8n_webhook_base_url)
    n8n.mode = _mode(settings, n8n.is_configured)
    slack = SlackConfig(webhook_url=settings.slack_webhook_url)
    slack.mode = _mode(settings, slack.is_configured)

    live = IntegrationMode.LIVE
    return IntegrationSet(
        crm=HttpEspoCRMClient(espo) if espo.mode == live else MockEspoCRMClient(),
        whatsapp=HttpWhatsAppClient(meta) if meta.mode == live else MockWhatsAppClient(),
        calendar=MockCalendarClient(),
        bayut=bayut.build_client(bayut_cfg),
        propertyfinder=propertyfinder.build_client(pf_cfg),
        telephony=MockTelephonyClient(),
        n8n=HttpN8nClient(n8n) if n8n.mode == live else MockN8nClient(),
        slack=WebhookSlackNotifier(slack) if slack.mode == live else MockSlackNotifier(),
        descriptors=[
            espocrm_descriptor(espo),
            meta_descriptor(meta),
            google_descriptor(google),
            bayut.descriptor(bayut_cfg),
            propertyfinder.descriptor(pf_cfg),
            telephony_descriptor(telephony),
            n8n_descriptor(n8n),
            slack_descriptor(slack),
        ],
    )
