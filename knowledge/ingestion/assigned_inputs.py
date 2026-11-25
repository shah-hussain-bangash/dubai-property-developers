"""Bounded text/PDF extraction and public HTTPS snapshot import."""

from __future__ import annotations

import http.client
import ipaddress
import json
import os
import socket
import ssl
import subprocess
import sys
import time
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit

from core.exceptions.errors import DomainValidationError

MAX_IMPORT_BYTES = 2_000_000


class PageText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg", "template"}:
            self.hidden += 1
        if not self.hidden and tag in {"p", "div", "br", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg", "template"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def extract_input(data: bytes, mime: str) -> list[str]:
    if len(data) > MAX_IMPORT_BYTES:
        raise DomainValidationError("Files and web pages must be smaller than 2 MB.")
    if mime == "application/pdf":
        # Parse outside the API process with a hard lifetime and Unix resource caps.
        env = {
            key: os.environ[key] for key in ["PATH", "SYSTEMROOT", "WINDIR"] if key in os.environ
        }
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            result = subprocess.run(
                [sys.executable, "-m", "knowledge.ingestion.pdf_source_worker"],
                input=data,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
                env=env,
            )
            if result.returncode != 0:
                raise ValueError()
            payload = json.loads(result.stdout)
            pages = payload.get("pages")
            if not isinstance(pages, list) or not all(isinstance(page, str) for page in pages):
                raise ValueError()
            return pages
        except (OSError, ValueError, subprocess.TimeoutExpired):
            raise DomainValidationError(
                "This PDF could not be read. Use a readable, unencrypted PDF with at most 100 pages, or upload a smaller file."
            ) from None
    if mime not in {"text/plain", "text/markdown", "text/html"}:
        raise DomainValidationError("Use a PDF, text, Markdown or readable HTML source.")
    text = data.decode("utf-8", errors="replace")
    if mime == "text/html":
        parser = PageText()
        parser.feed(text)
        text = " ".join(parser.parts)
    return [text]


def public_target(url: str) -> tuple[str, str, str]:
    try:
        parsed = urlsplit(url)
        if (
            len(url) > 2048
            or any(ord(c) <= 32 or ord(c) == 127 for c in url)
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in {None, 443}
            or parsed.fragment
        ):
            raise ValueError()
        host = parsed.hostname.encode("idna").decode("ascii")
        addresses = {
            str(row[4][0]) for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        }
        if not addresses or any(
            not (value := ipaddress.ip_address(ip)).is_global
            or value.is_multicast
            or value.is_reserved
            for ip in addresses
        ):
            raise ValueError()
        return (
            host,
            sorted(addresses)[0],
            # Encode Unicode for the HTTP request line, retaining existing escapes.
            quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
            + ("?" + quote(parsed.query, safe="/%?:@!$&'()*+,;=-._~[]") if parsed.query else ""),
        )
    except (ValueError, OSError, UnicodeError):
        raise DomainValidationError(
            "Use a public HTTPS page without login details or a nonstandard port."
        ) from None


class PinnedHTTPS(http.client.HTTPSConnection):
    """Connect to the checked IP while verifying TLS against the original host."""

    def __init__(self, host: str, address: str) -> None:
        self.address = address
        self.tls = ssl.create_default_context()
        self.tls.set_alpn_protocols(["http/1.1"])
        super().__init__(host, timeout=8, context=self.tls)

    def connect(self) -> None:
        raw = socket.create_connection((self.address, 443), timeout=8)
        try:
            self.sock = self.tls.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


def _check_fetch_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise DomainValidationError("The website took too long. Paste its text instead.")


def import_website(url: str) -> tuple[list[str], str]:
    deadline = time.monotonic() + 20
    for _ in range(4):
        _check_fetch_deadline(deadline)
        host, address, path = public_target(url)
        _check_fetch_deadline(deadline)
        connection = PinnedHTTPS(host, address)
        try:
            _check_fetch_deadline(deadline)
            connection.request(
                "GET",
                path,
                headers={
                    "Accept": "text/html,text/plain,application/pdf",
                    "Accept-Encoding": "identity",
                    "User-Agent": "DubaiPropertyKnowledgeImporter/1.0",
                },
            )
            _check_fetch_deadline(deadline)
            response = connection.getresponse()
            _check_fetch_deadline(deadline)
            if response.status in {301, 302, 303, 307, 308}:
                url = urljoin(url, response.getheader("Location", ""))
                continue
            if (
                response.status != 200
                or response.getheader("Content-Encoding", "identity") != "identity"
            ):
                raise DomainValidationError(
                    "The page could not be imported. Use a readable public page or paste its text."
                )
            chunks = bytearray()
            while len(chunks) <= MAX_IMPORT_BYTES:
                _check_fetch_deadline(deadline)
                chunk = response.read1(min(65536, MAX_IMPORT_BYTES + 1 - len(chunks)))
                # EOF is still a network result and cannot bypass the fetch budget.
                _check_fetch_deadline(deadline)
                if not chunk:
                    break
                chunks.extend(chunk)
            content = bytes(chunks)
            mime = response.getheader("Content-Type", "").split(";")[0].strip().lower()
            return extract_input(content, mime), url
        except DomainValidationError:
            raise
        except (OSError, http.client.HTTPException, UnicodeError):
            raise DomainValidationError(
                "The website could not be reached. Check the link or paste the text."
            ) from None
        finally:
            connection.close()
    raise DomainValidationError("The link redirects too many times. Use the final public page URL.")
