from __future__ import annotations

from openppx.runtime.gateway_service import (
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
    assert gateway_service_name("openppx") == "openppx-gateway"
    assert gateway_service_name("  openppx dev ") == "openppx-dev-gateway"
    assert gateway_service_name("..") == "openppx-gateway"


def test_render_launchd_plist_contains_required_sections() -> None:
    content = render_launchd_plist(
        label="ai.openppx.app.gateway",
        program="/usr/local/bin/ppx",
        args=["gateway", "run", "--channels", "local,feishu"],
        working_directory="/tmp/openppx",
        env={"OPENPPX_CHANNELS": "local,feishu"},
        stdout_path="/tmp/openppx/stdout.log",
        stderr_path="/tmp/openppx/stderr.log",
    )

    assert "<key>Label</key>" in content
    assert "<string>ai.openppx.app.gateway</string>" in content
    assert "<key>ProgramArguments</key>" in content
    assert "<string>/usr/local/bin/ppx</string>" in content
    assert "<string>gateway</string>" in content
    assert "<key>EnvironmentVariables</key>" in content
    assert "<key>OPENPPX_CHANNELS</key><string>local,feishu</string>" in content
    assert "<key>StandardOutPath</key>" in content
    assert "<true/>" in content


def test_render_systemd_unit_contains_required_sections() -> None:
    content = render_systemd_unit(
        description="OpenPPX Gateway",
        exec_start="/usr/local/bin/ppx gateway run --channels local",
        working_directory="/tmp/openppx",
        env={"OPENPPX_CHANNELS": "local", "OPENPPX_DEBUG": "1"},
    )

    assert "[Unit]" in content
    assert "Description=OpenPPX Gateway" in content
    assert "After=network-online.target" in content
    assert "[Service]" in content
    assert "ExecStart=/usr/local/bin/ppx gateway run --channels local" in content
    assert 'Environment="OPENPPX_CHANNELS=local"' in content
    assert 'Environment="OPENPPX_DEBUG=1"' in content
    assert "WantedBy=default.target" in content
