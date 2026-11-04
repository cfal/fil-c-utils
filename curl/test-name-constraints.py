#!/usr/bin/env python3
"""Exercise the shipped HTTPS client's DNS name-constraint enforcement."""
import http.server
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urlsplit


class Handler(http.server.BaseHTTPRequestHandler):
    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError):
            # A client can abort immediately after rejecting the certificate.
            pass

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/repo/info/refs":
            body = b"1111111111111111111111111111111111111111\trefs/heads/main\n"
        elif path == "/repo/HEAD":
            body = b"ref: refs/heads/main\n"
        else:
            body = b"fixture-ok\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def generate(root):
    def openssl(*args):
        subprocess.run(["openssl", *args], cwd=root, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def key(name):
        openssl("ecparam", "-name", "prime256v1", "-genkey", "-noout",
                "-out", name + ".key")

    def sign(name, cn, issuer, serial, extensions):
        key(name)
        openssl("req", "-new", "-key", name + ".key", "-subj", "/CN=" + cn,
                "-out", name + ".csr")
        (root / (name + ".ext")).write_text(extensions)
        openssl("x509", "-req", "-sha256", "-days", "2", "-in", name + ".csr",
                "-CA", issuer + ".pem", "-CAkey", issuer + ".key",
                "-set_serial", str(serial), "-extfile", name + ".ext",
                "-out", name + ".pem")

    key("root")
    openssl("req", "-new", "-x509", "-sha256", "-days", "2", "-key", "root.key",
            "-subj", "/CN=Fixture root", "-out", "root.pem",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    sign("ca", "Constrained fixture CA", "root", 2,
         "basicConstraints=critical,CA:TRUE,pathlen:0\n"
         "keyUsage=critical,keyCertSign,cRLSign\n"
         "nameConstraints=critical,permitted;DNS:allowed.test\n")
    cases = [
        ("allowed-cn", "within.allowed.test", None, False),
        ("allowed-san", "within.allowed.test", "within.allowed.test", False),
        ("outside-cn", "outside.test", None, True),
        ("outside-san", "outside.test", "outside.test", True),
        ("outside-cn-with-san", "outside.test", "within.allowed.test", True),
    ]
    for serial, (name, cn, san, rejected) in enumerate(cases, start=3):
        extensions = ("basicConstraints=critical,CA:FALSE\n"
                      "keyUsage=critical,digitalSignature\n"
                      "extendedKeyUsage=serverAuth\n")
        if san:
            extensions += "subjectAltName=DNS:" + san + "\n"
        sign(name, cn, "ca", serial, extensions)
        (root / (name + ".chain.pem")).write_bytes(
            (root / (name + ".pem")).read_bytes() + (root / "ca.pem").read_bytes())
    return cases


def test(root, mode, binary, case):
    name, cn, san, rejected = case
    hostname = san or cn
    server = http.server.ThreadingHTTPServer(("0.0.0.0", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(root / (name + ".chain.pem"), root / (name + ".key"))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    resolve = f"{hostname}:{port}:127.0.0.1"
    url = f"https://{hostname}:{port}/"
    if mode == "curl":
        command = [binary, "-q", "--noproxy", "*", "--cacert", str(root / "root.pem"),
                   "--resolve", resolve, "--max-time", "10", "-sS", url]
        expected, body = (60 if rejected else 0), "fixture-ok\n"
    else:
        command = [binary, "-c", "http.sslVerify=true", "-c", "http.proxy=",
                   "-c", "http.sslCAInfo=" + str(root / "root.pem"),
                   "-c", "http.curloptResolve=" + resolve, "ls-remote", url + "repo"]
        expected, body = (128 if rejected else 0), "refs/heads/main"
    env = {**os.environ, "HOME": str(root), "NO_PROXY": "*",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_CONFIG_COUNT": "0", "GIT_TERMINAL_PROMPT": "0"}
    env.pop("GIT_SSL_NO_VERIFY", None)
    try:
        result = subprocess.run(command, cwd=root, env=env, text=True,
                                capture_output=True, timeout=15)
        if result.returncode != expected:
            raise AssertionError(f"{mode} {name}: expected {expected}, got "
                                 f"{result.returncode}\n{result.stdout}{result.stderr}")
        if rejected:
            assert "permitted subtree violation" in result.stderr.lower(), result.stderr
            assert not result.stdout, result.stdout
        else:
            assert body in result.stdout, result.stdout
        print(f"{mode} {name}: {'rejected' if rejected else 'accepted'}", flush=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def main():
    mode, binary = sys.argv[1:]
    assert mode in ("curl", "git")
    binary = str(Path(binary).resolve())
    temporary = Path.home() / "tmp"
    temporary.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="name-constraints-", dir=temporary) as tmp:
        root = Path(tmp)
        for case in generate(root):
            test(root, mode, binary, case)


if __name__ == "__main__":
    main()
