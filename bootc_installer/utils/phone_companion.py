import http.server
import ssl
import socket
import threading
import json
import logging
import subprocess

logger = logging.getLogger("Installer::PhoneCompanion")

GLOBAL_CONFIG = None
CONFIG_RECEIVED_EVENT = threading.Event()

def get_local_ip():
    """Finds the local IP address of the primary active interface."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        # Fallback
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"

# Premium Dark-Mode HTML Form to serve on mobile devices
COMPANION_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bluefin Installer Companion</title>
    <style>
        :root {
            --bg-color: #0b0b0f;
            --card-bg: rgba(26, 26, 36, 0.6);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-color: #f3f4f6;
            --text-dim: #9ca3af;
            --primary: #3b82f6;
            --primary-glow: rgba(59, 130, 246, 0.5);
            --success: #10b981;
        }

        body {
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }

        .container {
            width: 100%;
            max-width: 440px;
            padding: 24px;
            box-sizing: border-box;
        }

        .card {
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-color);
            border-radius: 24px;
            padding: 32px 24px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
            text-align: center;
            position: relative;
            overflow: hidden;
        }

        .card::before {
            content: '';
            position: absolute;
            top: -2px;
            left: -2px;
            right: -2px;
            bottom: -2px;
            background: linear-gradient(135deg, var(--primary), transparent, transparent);
            border-radius: 24px;
            z-index: -1;
            opacity: 0.3;
        }

        h1 {
            font-size: 24px;
            margin: 0 0 8px 0;
            font-weight: 700;
        }

        p.subtitle {
            color: var(--text-dim);
            font-size: 14px;
            margin: 0 0 28px 0;
        }

        .form-group {
            text-align: left;
            margin-bottom: 20px;
        }

        label {
            display: block;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 6px;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        input, textarea {
            width: 100%;
            background: rgba(0, 0, 0, 0.2);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 12px 16px;
            box-sizing: border-box;
            color: var(--text-color);
            font-size: 15px;
            transition: all 0.2s ease;
        }

        input:focus, textarea:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 8px var(--primary-glow);
        }

        button {
            width: 100%;
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 12px;
            padding: 14px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            margin-top: 10px;
            transition: all 0.2s ease;
        }

        button:active {
            transform: scale(0.98);
        }

        #success-state {
            display: none;
        }

        .success-icon {
            font-size: 48px;
            color: var(--success);
            margin-bottom: 16px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card" id="form-state">
            <h1>Bluefin Setup</h1>
            <p class="subtitle">Complete your installation settings from your phone</p>
            
            <div class="form-group">
                <label for="fullname">Full Name</label>
                <input type="text" id="fullname" placeholder="e.g. John Doe" required>
            </div>
            
            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" placeholder="e.g. johndoe" required>
            </div>
            
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" placeholder="Create user password" required>
            </div>
            
            <div class="form-group">
                <label for="hostname">Hostname</label>
                <input type="text" id="hostname" placeholder="e.g. bluefin-desktop" value="bluefin-desktop" required>
            </div>
            
            <div class="form-group">
                <label for="sshkey">SSH Public Key (Optional)</label>
                <textarea id="sshkey" rows="3" placeholder="ssh-rsa ..."></textarea>
            </div>
            
            <button onclick="submitConfig()">Submit Setup</button>
        </div>

        <div class="card" id="success-state">
            <div class="success-icon">✓</div>
            <h1>Setup Completed!</h1>
            <p class="subtitle">You can now look back at the installer screen to confirm and finish the installation.</p>
        </div>
    </div>

    <script>
        // Auto-suggest username from full name
        document.getElementById('fullname').addEventListener('input', function(e) {
            const name = e.target.value.toLowerCase();
            const username = name.replace(/[^a-z0-9]/g, '');
            document.getElementById('username').value = username;
        });

        function submitConfig() {
            const fullname = document.getElementById('fullname').value;
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            const hostname = document.getElementById('hostname').value;
            const sshkey = document.getElementById('sshkey').value;

            if (!fullname || !username || !password || !hostname) {
                alert('Please fill out all required fields');
                return;
            }

            const payload = {
                fullname: fullname,
                username: username,
                password: password,
                hostname: hostname,
                sshkey: sshkey
            };

            fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    document.getElementById('form-state').style.display = 'none';
                    document.getElementById('success-state').style.display = 'block';
                } else {
                    alert('Submission failed, please try again.');
                }
            })
            .catch(err => {
                console.error(err);
                alert('Connection error.');
            });
        }
    </script>
</body>
</html>
"""

class CompanionRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress noisy HTTP logging in the installer logs
        pass

    def do_GET(self):
        if self.path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(COMPANION_HTML.encode('utf-8'))
        elif self.path in ["/config", "/api/config"]:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(GLOBAL_CONFIG or {}).encode("utf-8"))
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path == "/api/config":
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                config = json.loads(post_data.decode('utf-8'))
                
                global GLOBAL_CONFIG
                GLOBAL_CONFIG = config
                CONFIG_RECEIVED_EVENT.set()
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"success"}')
            except Exception as e:
                logger.error("Failed to parse POST payload: %s", e)
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"status":"error"}')
        else:
            self.send_error(404, "Not Found")

def generate_self_signed_cert():
    """Tries to generate a self-signed certificate using openssl on the live ISO."""
    try:
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", "/tmp/companion-key.pem",
            "-out", "/tmp/companion-cert.pem",
            "-days", "1", "-nodes",
            "-subj", "/CN=bootc-companion"
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        logger.warning("Could not generate self-signed SSL cert: %s. Falling back to HTTP.", e)
        return False

class CompanionServer:
    def __init__(self, port=8443):
        self.port = port
        self.server = None
        self.thread = None
        self.is_https = False

    def start(self):
        global GLOBAL_CONFIG
        GLOBAL_CONFIG = None
        CONFIG_RECEIVED_EVENT.clear()
        
        # Try SSL first
        self.is_https = generate_self_signed_cert()
        
        try:
            self.server = http.server.HTTPServer(("0.0.0.0", self.port), CompanionRequestHandler)
            
            if self.is_https:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.load_cert_chain(certfile="/tmp/companion-cert.pem", keyfile="/tmp/companion-key.pem")
                self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
                logger.info("Started local HTTPS Phone Companion server on port %s", self.port)
            else:
                logger.info("Started local HTTP Phone Companion server on port %s", self.port)
                
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
        except Exception as e:
            logger.error("Failed to start CompanionServer: %s", e)

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            logger.info("Stopped Phone Companion server")

    def get_config(self):
        return GLOBAL_CONFIG
