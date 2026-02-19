"""Channel interfaces and adapters."""

from .base import BaseChannel
from .email import EmailChannel
from .factory import build_channel_manager, parse_enabled_channels, validate_channel_setup
from .feishu import FeishuChannel
from .local import LocalChannel
from .slack import SlackChannel
from .manager import ChannelManager
from .telegram import TelegramChannel

__all__ = [
    "BaseChannel",
    "ChannelManager",
    "EmailChannel",
    "FeishuChannel",
    "LocalChannel",
    "SlackChannel",
    "TelegramChannel",
    "build_channel_manager",
    "parse_enabled_channels",
    "validate_channel_setup",
]
