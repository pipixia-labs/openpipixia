"""Channel registry metadata for factory/config alignment.

This module centralizes channel names and their bootstrap behavior:
- Which channels are recognized by config/CLI parsing.
- Which channels have runtime adapters implemented today.
- Which setup validations should run before gateway startup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from ..bus.queue import MessageBus
from .base import BaseChannel
from .discord import DiscordChannel
from .email import EmailChannel
from .feishu import FEISHU_AVAILABLE, FeishuChannel
from .local import LocalChannel
from .qq import QQ_AVAILABLE, QQChannel
from .slack import SlackChannel
from .telegram import TelegramChannel


LocalWriter = Callable[[str], None] | None
ChannelBuilder = Callable[[MessageBus, LocalWriter], BaseChannel | None]
ChannelValidator = Callable[[], list[str]]


@dataclass(frozen=True, slots=True)
class ChannelSpec:
    """Static metadata for one channel type."""

    name: str
    build: ChannelBuilder
    validate_setup: ChannelValidator


def _build_local(bus: MessageBus, local_writer: LocalWriter) -> BaseChannel:
    return LocalChannel(bus=bus, writer=local_writer)


def _validate_local() -> list[str]:
    return []


def _build_feishu(bus: MessageBus, _local_writer: LocalWriter) -> BaseChannel:
    allow_from = [item.strip() for item in os.getenv("FEISHU_ALLOW_FROM", "").split(",") if item.strip()]
    return FeishuChannel(
        bus=bus,
        app_id=os.getenv("FEISHU_APP_ID", "").strip(),
        app_secret=os.getenv("FEISHU_APP_SECRET", "").strip(),
        encrypt_key=os.getenv("FEISHU_ENCRYPT_KEY", "").strip(),
        verification_token=os.getenv("FEISHU_VERIFICATION_TOKEN", "").strip(),
        allow_from=allow_from,
    )


def _validate_feishu() -> list[str]:
    issues: list[str] = []
    if not FEISHU_AVAILABLE:
        issues.append("Feishu channel requires `lark-oapi` (pip install lark-oapi).")
    if not os.getenv("FEISHU_APP_ID", "").strip():
        issues.append("Missing FEISHU_APP_ID for feishu channel.")
    if not os.getenv("FEISHU_APP_SECRET", "").strip():
        issues.append("Missing FEISHU_APP_SECRET for feishu channel.")
    return issues


def _build_telegram(bus: MessageBus, _local_writer: LocalWriter) -> BaseChannel:
    allow_from = [item.strip() for item in os.getenv("TELEGRAM_ALLOW_FROM", "").split(",") if item.strip()]
    return TelegramChannel(
        bus=bus,
        token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        allow_from=allow_from,
        proxy=os.getenv("TELEGRAM_PROXY", "").strip(),
    )


def _validate_telegram() -> list[str]:
    if os.getenv("TELEGRAM_BOT_TOKEN", "").strip():
        return []
    return ["Missing TELEGRAM_BOT_TOKEN for telegram channel."]


def _build_discord(bus: MessageBus, _local_writer: LocalWriter) -> BaseChannel:
    allow_from = [item.strip() for item in os.getenv("DISCORD_ALLOW_FROM", "").split(",") if item.strip()]
    poll_channels = [item.strip() for item in os.getenv("DISCORD_POLL_CHANNELS", "").split(",") if item.strip()]
    return DiscordChannel(
        bus=bus,
        token=os.getenv("DISCORD_BOT_TOKEN", "").strip(),
        allow_from=allow_from,
        poll_channels=poll_channels,
        poll_interval_seconds=_env_int("DISCORD_POLL_INTERVAL_SECONDS", 10),
        include_bots=_env_flag("DISCORD_INCLUDE_BOTS", default=False),
    )


def _validate_discord() -> list[str]:
    if os.getenv("DISCORD_BOT_TOKEN", "").strip():
        return []
    return ["Missing DISCORD_BOT_TOKEN for discord channel."]


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "1" if default else "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        return default


def _build_email(bus: MessageBus, _local_writer: LocalWriter) -> BaseChannel:
    allow_from = [item.strip() for item in os.getenv("EMAIL_ALLOW_FROM", "").split(",") if item.strip()]
    return EmailChannel(
        bus=bus,
        consent_granted=_env_flag("EMAIL_CONSENT_GRANTED", default=False),
        auto_reply_enabled=_env_flag("EMAIL_AUTO_REPLY_ENABLED", default=True),
        imap_host=os.getenv("EMAIL_IMAP_HOST", "").strip(),
        imap_port=_env_int("EMAIL_IMAP_PORT", 993),
        imap_username=os.getenv("EMAIL_IMAP_USERNAME", "").strip(),
        imap_password=os.getenv("EMAIL_IMAP_PASSWORD", ""),
        imap_mailbox=os.getenv("EMAIL_IMAP_MAILBOX", "INBOX").strip() or "INBOX",
        imap_use_ssl=_env_flag("EMAIL_IMAP_USE_SSL", default=True),
        smtp_host=os.getenv("EMAIL_SMTP_HOST", "").strip(),
        smtp_port=_env_int("EMAIL_SMTP_PORT", 587),
        smtp_username=os.getenv("EMAIL_SMTP_USERNAME", "").strip(),
        smtp_password=os.getenv("EMAIL_SMTP_PASSWORD", ""),
        smtp_use_tls=_env_flag("EMAIL_SMTP_USE_TLS", default=True),
        smtp_use_ssl=_env_flag("EMAIL_SMTP_USE_SSL", default=False),
        from_address=os.getenv("EMAIL_FROM_ADDRESS", "").strip(),
        poll_interval_seconds=_env_int("EMAIL_POLL_INTERVAL_SECONDS", 30),
        mark_seen=_env_flag("EMAIL_MARK_SEEN", default=True),
        max_body_chars=_env_int("EMAIL_MAX_BODY_CHARS", 12000),
        allow_from=allow_from,
    )


def _validate_email() -> list[str]:
    issues: list[str] = []
    if not _env_flag("EMAIL_CONSENT_GRANTED", default=False):
        issues.append("Missing EMAIL_CONSENT_GRANTED=1 for email channel.")
    if not os.getenv("EMAIL_SMTP_HOST", "").strip():
        issues.append("Missing EMAIL_SMTP_HOST for email channel.")
    if not os.getenv("EMAIL_SMTP_USERNAME", "").strip():
        issues.append("Missing EMAIL_SMTP_USERNAME for email channel.")
    if not os.getenv("EMAIL_SMTP_PASSWORD", ""):
        issues.append("Missing EMAIL_SMTP_PASSWORD for email channel.")
    return issues


def _build_slack(bus: MessageBus, _local_writer: LocalWriter) -> BaseChannel:
    allow_from = [item.strip() for item in os.getenv("SLACK_ALLOW_FROM", "").split(",") if item.strip()]
    poll_channels = [item.strip() for item in os.getenv("SLACK_POLL_CHANNELS", "").split(",") if item.strip()]
    return SlackChannel(
        bus=bus,
        bot_token=os.getenv("SLACK_BOT_TOKEN", "").strip(),
        app_token=os.getenv("SLACK_APP_TOKEN", "").strip(),
        default_channel=os.getenv("SLACK_DEFAULT_CHANNEL", "").strip(),
        allow_from=allow_from,
        poll_channels=poll_channels,
        poll_interval_seconds=_env_int("SLACK_POLL_INTERVAL_SECONDS", 15),
        include_bots=_env_flag("SLACK_INCLUDE_BOTS", default=False),
    )


def _validate_slack() -> list[str]:
    if os.getenv("SLACK_BOT_TOKEN", "").strip():
        return []
    return ["Missing SLACK_BOT_TOKEN for slack channel."]


def _build_qq(bus: MessageBus, _local_writer: LocalWriter) -> BaseChannel:
    allow_from = [item.strip() for item in os.getenv("QQ_ALLOW_FROM", "").split(",") if item.strip()]
    return QQChannel(
        bus=bus,
        app_id=os.getenv("QQ_APP_ID", "").strip(),
        secret=os.getenv("QQ_SECRET", "").strip(),
        allow_from=allow_from,
    )


def _validate_qq() -> list[str]:
    issues: list[str] = []
    if not QQ_AVAILABLE:
        issues.append("QQ channel requires `qq-botpy` (pip install qq-botpy).")
    if not os.getenv("QQ_APP_ID", "").strip():
        issues.append("Missing QQ_APP_ID for qq channel.")
    if not os.getenv("QQ_SECRET", "").strip():
        issues.append("Missing QQ_SECRET for qq channel.")
    return issues


def _build_not_implemented(_bus: MessageBus, _local_writer: LocalWriter) -> None:
    # Channel is known by configuration but has no runtime adapter yet.
    return None


def _validate_not_implemented(name: str) -> ChannelValidator:
    def _inner() -> list[str]:
        return [f"Channel '{name}' is recognized but not implemented yet in sentientagent_v2."]

    return _inner


CHANNEL_ORDER: tuple[str, ...] = (
    "local",
    "feishu",
    "telegram",
    "whatsapp",
    "discord",
    "mochat",
    "dingtalk",
    "email",
    "slack",
    "qq",
)


def _make_registry() -> dict[str, ChannelSpec]:
    specs: dict[str, ChannelSpec] = {
        "local": ChannelSpec(
            name="local",
            build=_build_local,
            validate_setup=_validate_local,
        ),
        "feishu": ChannelSpec(
            name="feishu",
            build=_build_feishu,
            validate_setup=_validate_feishu,
        ),
        "telegram": ChannelSpec(
            name="telegram",
            build=_build_telegram,
            validate_setup=_validate_telegram,
        ),
        "discord": ChannelSpec(
            name="discord",
            build=_build_discord,
            validate_setup=_validate_discord,
        ),
        "email": ChannelSpec(
            name="email",
            build=_build_email,
            validate_setup=_validate_email,
        ),
        "slack": ChannelSpec(
            name="slack",
            build=_build_slack,
            validate_setup=_validate_slack,
        ),
        "qq": ChannelSpec(
            name="qq",
            build=_build_qq,
            validate_setup=_validate_qq,
        ),
    }

    for name in CHANNEL_ORDER:
        if name in specs:
            continue
        specs[name] = ChannelSpec(
            name=name,
            build=_build_not_implemented,
            validate_setup=_validate_not_implemented(name),
        )
    return specs


CHANNEL_SPECS: dict[str, ChannelSpec] = _make_registry()


def known_channel_names() -> list[str]:
    """Return all recognized channel names in stable display order."""
    return [name for name in CHANNEL_ORDER if name in CHANNEL_SPECS]


def get_channel_spec(name: str) -> ChannelSpec | None:
    """Return channel spec by name."""
    return CHANNEL_SPECS.get(name)
