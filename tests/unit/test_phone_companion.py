import io
import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from bootc_installer.utils import phone_companion
from bootc_installer.utils.phone_companion import (
    COMPANION_HTML,
    CONFIG_RECEIVED_EVENT,
    CompanionRequestHandler,
    CompanionServer,
    generate_self_signed_cert,
    get_local_ip,
)


@pytest.fixture(autouse=True)
def reset_phone_companion_state():
    phone_companion.GLOBAL_CONFIG = None
    CONFIG_RECEIVED_EVENT.clear()
    yield
    phone_companion.GLOBAL_CONFIG = None
    CONFIG_RECEIVED_EVENT.clear()


def _make_handler(path, body=b""):
    handler = CompanionRequestHandler.__new__(CompanionRequestHandler)
    handler.path = path
    handler.headers = {"Content-Length": str(len(body))}
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.send_error = MagicMock()
    return handler


def test_get_local_ip_returns_socket_address():
    sock = MagicMock()
    sock.getsockname.return_value = ("192.168.1.25", 12345)

    with patch("bootc_installer.utils.phone_companion.socket.socket", return_value=sock):
        assert get_local_ip() == "192.168.1.25"

    sock.connect.assert_called_once_with(("8.8.8.8", 80))
    sock.close.assert_called_once_with()


def test_get_local_ip_falls_back_to_hostname_lookup_on_udp_failure():
    with patch("bootc_installer.utils.phone_companion.socket.socket", side_effect=OSError("offline")), \
         patch("bootc_installer.utils.phone_companion.socket.gethostname", return_value="installer"), \
         patch("bootc_installer.utils.phone_companion.socket.gethostbyname", return_value="10.0.0.9"):
        assert get_local_ip() == "10.0.0.9"


def test_get_local_ip_returns_loopback_when_all_lookups_fail():
    with patch("bootc_installer.utils.phone_companion.socket.socket", side_effect=OSError("offline")), \
         patch("bootc_installer.utils.phone_companion.socket.gethostbyname", side_effect=OSError("no dns")):
        assert get_local_ip() == "127.0.0.1"


def test_generate_self_signed_cert_runs_openssl():
    with patch("bootc_installer.utils.phone_companion.subprocess.run") as run_mock:
        assert generate_self_signed_cert() is True

    run_mock.assert_called_once_with(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", "/tmp/companion-key.pem",
            "-out", "/tmp/companion-cert.pem",
            "-days", "1", "-nodes",
            "-subj", "/CN=bootc-companion",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_generate_self_signed_cert_returns_false_on_failure():
    with patch(
        "bootc_installer.utils.phone_companion.subprocess.run",
        side_effect=OSError("openssl missing"),
    ), patch("bootc_installer.utils.phone_companion.logger.warning") as warning_mock:
        assert generate_self_signed_cert() is False

    warning_mock.assert_called_once()


def test_companion_server_init_sets_default_state():
    server = CompanionServer()

    assert server.port == 8443
    assert server.server is None
    assert server.thread is None
    assert server.is_https is False


def test_companion_server_start_resets_state_and_starts_http_thread():
    server = CompanionServer(port=9999)
    fake_server = MagicMock()
    fake_thread = MagicMock()
    phone_companion.GLOBAL_CONFIG = {"stale": True}
    CONFIG_RECEIVED_EVENT.set()

    with patch("bootc_installer.utils.phone_companion.generate_self_signed_cert", return_value=False), \
         patch("bootc_installer.utils.phone_companion.http.server.HTTPServer", return_value=fake_server) as http_server_mock, \
         patch("bootc_installer.utils.phone_companion.threading.Thread", return_value=fake_thread) as thread_mock:
        server.start()

    assert phone_companion.GLOBAL_CONFIG is None
    assert not CONFIG_RECEIVED_EVENT.is_set()
    assert server.server is fake_server
    assert server.thread is fake_thread
    assert server.is_https is False
    http_server_mock.assert_called_once_with(("0.0.0.0", 9999), CompanionRequestHandler)
    thread_mock.assert_called_once_with(target=fake_server.serve_forever, daemon=True)
    fake_thread.start.assert_called_once_with()


def test_companion_server_start_configures_tls_when_certificate_exists():
    server = CompanionServer(port=8443)
    fake_server = MagicMock()
    wrapped_socket = MagicMock()
    original_socket = MagicMock()
    fake_server.socket = original_socket
    ssl_context = MagicMock()
    ssl_context.wrap_socket.return_value = wrapped_socket

    with patch("bootc_installer.utils.phone_companion.generate_self_signed_cert", return_value=True), \
         patch("bootc_installer.utils.phone_companion.http.server.HTTPServer", return_value=fake_server), \
         patch("bootc_installer.utils.phone_companion.ssl.SSLContext", return_value=ssl_context) as ssl_context_cls, \
         patch("bootc_installer.utils.phone_companion.threading.Thread", return_value=MagicMock()):
        server.start()

    assert server.is_https is True
    ssl_context_cls.assert_called_once_with(phone_companion.ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain.assert_called_once_with(
        certfile="/tmp/companion-cert.pem",
        keyfile="/tmp/companion-key.pem",
    )
    ssl_context.wrap_socket.assert_called_once_with(original_socket, server_side=True)
    assert fake_server.socket is wrapped_socket


def test_companion_server_stop_shuts_down_active_server():
    server = CompanionServer()
    server.server = MagicMock()

    server.stop()

    server.server.shutdown.assert_called_once_with()
    server.server.server_close.assert_called_once_with()


def test_companion_server_get_config_returns_current_global_config():
    server = CompanionServer()

    assert server.get_config() is None

    phone_companion.GLOBAL_CONFIG = {"hostname": "bluefin"}

    assert server.get_config() == {"hostname": "bluefin"}


def test_handler_get_root_serves_html():
    handler = _make_handler("/")

    handler.do_GET()

    handler.send_response.assert_called_once_with(200)
    handler.send_header.assert_called_once_with("Content-Type", "text/html")
    handler.end_headers.assert_called_once_with()
    assert handler.wfile.getvalue() == COMPANION_HTML.encode("utf-8")


def test_handler_get_config_returns_current_config():
    phone_companion.GLOBAL_CONFIG = {"hostname": "bluefin", "username": "jorge"}
    handler = _make_handler("/config")

    handler.do_GET()

    handler.send_response.assert_called_once_with(200)
    handler.send_header.assert_called_once_with("Content-Type", "application/json")
    assert json.loads(handler.wfile.getvalue().decode("utf-8")) == phone_companion.GLOBAL_CONFIG


def test_handler_get_unknown_path_returns_404():
    handler = _make_handler("/missing")

    handler.do_GET()

    handler.send_error.assert_called_once_with(404, "Not Found")


def test_handler_post_valid_config_updates_global_state_and_event():
    payload = {
        "fullname": "John Doe",
        "username": "johndoe",
        "password": "secret",
        "hostname": "bluefin",
        "sshkey": "ssh-ed25519 AAA",
    }
    handler = _make_handler("/api/config", json.dumps(payload).encode("utf-8"))

    handler.do_POST()

    assert phone_companion.GLOBAL_CONFIG == payload
    assert CONFIG_RECEIVED_EVENT.is_set()
    handler.send_response.assert_called_once_with(200)
    handler.send_header.assert_called_once_with("Content-Type", "application/json")
    assert json.loads(handler.wfile.getvalue().decode("utf-8")) == {"status": "success"}


def test_handler_post_invalid_json_returns_error_without_setting_state():
    handler = _make_handler("/api/config", b"{not-json")

    with patch("bootc_installer.utils.phone_companion.logger.error") as error_mock:
        handler.do_POST()

    assert phone_companion.GLOBAL_CONFIG is None
    assert not CONFIG_RECEIVED_EVENT.is_set()
    handler.send_response.assert_called_once_with(400)
    assert json.loads(handler.wfile.getvalue().decode("utf-8")) == {"status": "error"}
    error_mock.assert_called_once()


def test_handler_post_unknown_path_returns_404():
    handler = _make_handler("/api/other", b"{}")

    handler.do_POST()

    handler.send_error.assert_called_once_with(404, "Not Found")
