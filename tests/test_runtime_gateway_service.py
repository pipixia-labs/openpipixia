from __future__ import annotations

from openheron.runtime.gateway_service import (
    detect_service_manager,
    gateway_service_name,
    render_launchd_plist,
    render_systemd_unit,
)


def test_detect_service_manager_by_platform_name() -> None:
    assert detect_service_manager("darwin") == "launchd"
    assert detect_service_manager("darwin23") == "launchd"
    assert detect_service_manager("linux") == "systemd"
    assert detect_service_manager("linux-gnu") == "systemd"
    assert detect_service_manager("win32") == "unsupported"


def test_gateway_service_name_normalization() -> None:
    assert gateway_service_name("openheron") == "openheron-gateway"
    assert gateway_service_name("  openheron dev ") == "openheron-dev-gateway"
    assert gateway_service_name("..") == "openheron-gateway"


def test_render_launchd_plist_contains_required_sections() -> None:
    content = render_launchd_plist(
        label="ai.openheron.gateway",
        program="/usr/local/bin/openheron",
        args=["gateway", "--channels", "local,feishu"],
        working_directory="/tmp/openheron",
        env={"OPENHERON_CHANNELS": "local,feishu"},
        stdout_path="/tmp/openheron/stdout.log",
        stderr_path="/tmp/openheron/stderr.log",
    )

    assert "<key>Label</key>" in content
    assert "<string>ai.openheron.gateway</string>" in content
    assert "<key>ProgramArguments</key>" in content
    assert "<string>/usr/local/bin/openheron</string>" in content
    assert "<string>gateway</string>" in content
    assert "<key>EnvironmentVariables</key>" in content
    assert "<key>OPENHERON_CHANNELS</key><string>local,feishu</string>" in content
    assert "<key>StandardOutPath</key>" in content
    assert "<true/>" in content


def test_render_systemd_unit_contains_required_sections() -> None:
    content = render_systemd_unit(
        description="Openheron Gateway",
        exec_start="/usr/local/bin/openheron gateway --channels local",
        working_directory="/tmp/openheron",
        env={"OPENHERON_CHANNELS": "local", "OPENHERON_DEBUG": "1"},
    )

    assert "[Unit]" in content
    assert "Description=Openheron Gateway" in content
    assert "After=network-online.target" in content
    assert "[Service]" in content
    assert "ExecStart=/usr/local/bin/openheron gateway --channels local" in content
    assert 'Environment="OPENHERON_CHANNELS=local"' in content
    assert 'Environment="OPENHERON_DEBUG=1"' in content
    assert "WantedBy=default.target" in content
