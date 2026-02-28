"""Install summary and onboarding prompt rule models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from .doctor_rules import DOCTOR_CHANNEL_BOOL_ENV_BACKFILL_RULES, DOCTOR_CHANNEL_ENV_BACKFILL_RULES
from .provider import provider_api_key_env
from .provider_registry import find_provider_spec


@dataclass(frozen=True)
class InstallChannelPromptRule:
    """Schema rule for collecting one channel credential during install setup."""

    key: str
    prompt: str
    use_secret_reader: bool = False
    parse_bool: bool = False
    strip_for_presence: bool = True


@dataclass(frozen=True)
class InstallProviderSummaryRequirement:
    """Schema rule for install summary provider missing checks and fix hints."""

    key: str
    fix_hint_template: str = "set providers.{provider}.{key} in {config_path}"
    env_name_resolver: Callable[[str], str | None] | None = None
    skip_for_oauth: bool = False
    doctor_env_backfill_code: str | None = None
    doctor_env_backfill_rule: str = "provider_env_backfill"

    @property
    def item_suffix(self) -> str:
        return self.key


@dataclass(frozen=True)
class InstallChannelSummaryRequirement:
    """Schema rule for install summary missing checks and fix hints."""

    channel: str
    key: str
    presence: Literal["truthy_bool", "non_empty_strip", "non_empty_raw"] = "non_empty_strip"
    fix_hint_template: str = "set {item} in {config_path}"

    @property
    def item(self) -> str:
        return f"channels.{self.channel}.{self.key}"


INSTALL_CHANNEL_PROMPT_RULES: dict[str, tuple[InstallChannelPromptRule, ...]] = {
    "feishu": (
        InstallChannelPromptRule("appId", "Feishu appId (required for enabled channel, press Enter to skip for now)> "),
        InstallChannelPromptRule(
            "appSecret",
            "Feishu appSecret (required for enabled channel, press Enter to skip for now)> ",
            use_secret_reader=True,
        ),
    ),
    "telegram": (
        InstallChannelPromptRule(
            "token",
            "Telegram bot token (required for enabled channel, press Enter to skip for now)> ",
            use_secret_reader=True,
        ),
    ),
    "discord": (
        InstallChannelPromptRule(
            "token",
            "Discord bot token (required for enabled channel, press Enter to skip for now)> ",
            use_secret_reader=True,
        ),
    ),
    "dingtalk": (
        InstallChannelPromptRule(
            "clientId",
            "DingTalk clientId (required for enabled channel, press Enter to skip for now)> ",
        ),
        InstallChannelPromptRule(
            "clientSecret",
            "DingTalk clientSecret (required for enabled channel, press Enter to skip for now)> ",
            use_secret_reader=True,
        ),
    ),
    "slack": (
        InstallChannelPromptRule(
            "botToken",
            "Slack bot token (required for enabled channel, press Enter to skip for now)> ",
            use_secret_reader=True,
        ),
    ),
    "whatsapp": (
        InstallChannelPromptRule(
            "bridgeUrl",
            "WhatsApp bridgeUrl (required for enabled channel, press Enter to skip for now)> ",
        ),
    ),
    "email": (
        InstallChannelPromptRule(
            "consentGranted",
            "Email consent granted? (required for enabled channel, y/N, press Enter to skip for now)> ",
            parse_bool=True,
        ),
        InstallChannelPromptRule(
            "smtpHost",
            "Email smtpHost (required for enabled channel, press Enter to skip for now)> ",
        ),
        InstallChannelPromptRule(
            "smtpUsername",
            "Email smtpUsername (required for enabled channel, press Enter to skip for now)> ",
        ),
        InstallChannelPromptRule(
            "smtpPassword",
            "Email smtpPassword (required for enabled channel, press Enter to skip for now)> ",
            use_secret_reader=True,
            strip_for_presence=False,
        ),
    ),
    "qq": (
        InstallChannelPromptRule(
            "appId",
            "QQ appId (required for enabled channel, press Enter to skip for now)> ",
        ),
        InstallChannelPromptRule(
            "secret",
            "QQ secret (required for enabled channel, press Enter to skip for now)> ",
            use_secret_reader=True,
        ),
    ),
}

INSTALL_PROVIDER_SUMMARY_REQUIREMENTS: tuple[InstallProviderSummaryRequirement, ...] = (
    InstallProviderSummaryRequirement(
        "apiKey",
        env_name_resolver=provider_api_key_env,
        skip_for_oauth=True,
        doctor_env_backfill_code="provider.env.api_key_backfilled",
    ),
)


def build_install_channel_summary_requirements() -> tuple[InstallChannelSummaryRequirement, ...]:
    """Build install summary requirements from doctor channel rule metadata."""

    requirements: list[InstallChannelSummaryRequirement] = []
    bool_requirements: dict[tuple[str, str], InstallChannelSummaryRequirement] = {}
    for bool_rule in DOCTOR_CHANNEL_BOOL_ENV_BACKFILL_RULES:
        bool_requirements[(bool_rule.channel, bool_rule.key)] = InstallChannelSummaryRequirement(
            channel=bool_rule.channel,
            key=bool_rule.key,
            presence="truthy_bool",
            fix_hint_template=f"set channels.{bool_rule.channel}.{bool_rule.key}=true in {{config_path}}",
        )

    for backfill_rule in DOCTOR_CHANNEL_ENV_BACKFILL_RULES:
        channel = backfill_rule.channel
        key = backfill_rule.key
        bool_requirement = bool_requirements.get((channel, key))
        if bool_requirement is not None:
            requirements.append(bool_requirement)
        fix_hint_template = (
            "set {item} in {config_path} (Feishu credentials)"
            if channel == "feishu"
            else "set {item} in {config_path}"
        )
        presence: Literal["truthy_bool", "non_empty_strip", "non_empty_raw"] = "non_empty_strip"
        if channel == "email" and key == "smtpPassword":
            presence = "non_empty_raw"
        requirements.append(
            InstallChannelSummaryRequirement(
                channel=channel,
                key=key,
                presence=presence,
                fix_hint_template=fix_hint_template,
            )
        )
    for summary_requirement in bool_requirements.values():
        if summary_requirement not in requirements:
            requirements.append(summary_requirement)
    return tuple(requirements)


def install_channel_value_missing(
    *,
    cfg: dict[str, Any],
    key: str,
    presence: Literal["truthy_bool", "non_empty_strip", "non_empty_raw"],
) -> bool:
    """Return whether a channel field is considered missing by install summary rules."""

    value = cfg.get(key)
    if presence == "truthy_bool":
        return not bool(value)
    if presence == "non_empty_raw":
        return not str(value or "")
    return not str(value or "").strip()


def install_summary_provider_missing(
    *,
    selected_provider: str,
    provider_cfg: dict[str, Any],
    requirements: tuple[InstallProviderSummaryRequirement, ...],
) -> list[str]:
    """Collect missing provider fields for install summary."""

    if selected_provider == "-":
        return []
    provider_item = provider_cfg.get(selected_provider, {})
    if not isinstance(provider_item, dict):
        return []

    provider_spec = find_provider_spec(selected_provider)
    missing: list[str] = []
    for requirement in requirements:
        if requirement.skip_for_oauth and provider_spec and provider_spec.is_oauth:
            continue
        if requirement.env_name_resolver is not None:
            env_name = requirement.env_name_resolver(selected_provider)
            if env_name and not str(provider_item.get(requirement.key, "")).strip():
                missing.append(f"{selected_provider}.{requirement.item_suffix}")
            continue
        if not str(provider_item.get(requirement.key, "")).strip():
            missing.append(f"{selected_provider}.{requirement.item_suffix}")
    return missing


def install_summary_provider_fix_hints(
    *,
    selected_provider: str,
    config_path: Path,
    requirements: tuple[InstallProviderSummaryRequirement, ...],
) -> dict[str, str]:
    """Build install summary fix hint map for provider missing fields."""

    if selected_provider == "-":
        return {}
    hints: dict[str, str] = {}
    for requirement in requirements:
        item = f"{selected_provider}.{requirement.item_suffix}"
        hints[item] = requirement.fix_hint_template.format(
            provider=selected_provider,
            key=requirement.key,
            config_path=config_path,
        )
    return hints


def install_summary_channel_missing(
    channels_cfg: dict[str, Any],
    requirements: tuple[InstallChannelSummaryRequirement, ...],
) -> list[str]:
    """Collect missing channel fields for install summary in stable rule order."""

    missing: list[str] = []
    for requirement in requirements:
        channel_cfg = channels_cfg.get(requirement.channel, {})
        if not isinstance(channel_cfg, dict) or not bool(channel_cfg.get("enabled")):
            continue
        if install_channel_value_missing(
            cfg=channel_cfg,
            key=requirement.key,
            presence=requirement.presence,
        ):
            missing.append(requirement.item)
    return missing


def install_summary_channel_fix_hints(
    config_path: Path,
    requirements: tuple[InstallChannelSummaryRequirement, ...],
) -> dict[str, str]:
    """Build install summary fix hint map for channel missing fields."""

    hints: dict[str, str] = {}
    for requirement in requirements:
        hints[requirement.item] = requirement.fix_hint_template.format(
            item=requirement.item,
            config_path=config_path,
        )
    return hints


def install_summary_missing(
    *,
    selected_provider: str,
    provider_cfg: dict[str, Any],
    channels_cfg: dict[str, Any],
    provider_requirements: tuple[InstallProviderSummaryRequirement, ...],
    channel_requirements: tuple[InstallChannelSummaryRequirement, ...],
) -> list[str]:
    """Collect all install summary missing items in a stable order."""

    missing: list[str] = []
    missing.extend(
        install_summary_provider_missing(
            selected_provider=selected_provider,
            provider_cfg=provider_cfg,
            requirements=provider_requirements,
        )
    )
    missing.extend(install_summary_channel_missing(channels_cfg, channel_requirements))
    return missing


def install_summary_fix_hints(
    *,
    missing: list[str],
    selected_provider: str,
    config_path: Path,
    provider_requirements: tuple[InstallProviderSummaryRequirement, ...],
    channel_requirements: tuple[InstallChannelSummaryRequirement, ...],
) -> list[str]:
    """Render install summary fix hints for provider and channel missing items."""

    provider_fix_hints = install_summary_provider_fix_hints(
        selected_provider=selected_provider,
        config_path=config_path,
        requirements=provider_requirements,
    )
    channel_fix_hints = install_summary_channel_fix_hints(config_path, channel_requirements)
    combined_hints = {**provider_fix_hints, **channel_fix_hints}

    rendered: list[str] = []
    for item in missing:
        hint = combined_hints.get(item)
        if hint:
            rendered.append(hint)
        else:
            rendered.append(f"set {item} in {config_path}")
    return rendered


def apply_install_channel_prompt_rules(
    *,
    channels_cfg: dict[str, Any],
    enabled_channels: list[str],
    input_fn: Callable[[str], str],
    secret_input_fn: Callable[[str], str] | None = None,
    prompt_rules: dict[str, tuple[InstallChannelPromptRule, ...]] | None = None,
) -> None:
    """Collect missing channel credentials using table-driven prompt rules."""

    rules_map = prompt_rules or INSTALL_CHANNEL_PROMPT_RULES
    default_secret_reader = secret_input_fn or input_fn
    for channel_name in enabled_channels:
        channel_cfg = channels_cfg.get(channel_name, {})
        if not isinstance(channel_cfg, dict):
            continue
        rules = rules_map.get(channel_name, ())
        for rule in rules:
            if rule.parse_bool:
                if bool(channel_cfg.get(rule.key)):
                    continue
                raw = input_fn(rule.prompt).strip().lower()
                if raw in {"y", "yes", "true", "1", "on"}:
                    channel_cfg[rule.key] = True
                elif raw in {"n", "no", "false", "0", "off"}:
                    channel_cfg[rule.key] = False
                continue

            value = channel_cfg.get(rule.key, "")
            has_value = bool(str(value).strip()) if rule.strip_for_presence else bool(str(value))
            if has_value:
                continue
            reader = default_secret_reader if rule.use_secret_reader else input_fn
            raw = reader(rule.prompt).strip()
            if raw:
                channel_cfg[rule.key] = raw
