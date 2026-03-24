from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Iterable
from urllib.parse import ParseResult, parse_qsl, quote, unquote, urlencode, urlparse, urlunparse
import fnmatch
import re
import socket

_PRIVATE_NETWORKS = [
    ip_network("127.0.0.0/8"),
    ip_network("10.0.0.0/8"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
    ip_network("169.254.0.0/16"),
    ip_network("::1/128"),
    ip_network("fc00::/7"),
    ip_network("fe80::/10"),
]


class VisibleTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._suppress_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg", "canvas"}:
            self._suppress_depth += 1
        elif tag.lower() in {"p", "div", "br", "section", "article", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg", "canvas"} and self._suppress_depth:
            self._suppress_depth -= 1
        elif tag.lower() in {"p", "div", "section", "article", "li"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._suppress_depth:
            return
        clean = re.sub(r"\s+", " ", data)
        if clean.strip():
            self._chunks.append(clean.strip() + " ")

    def text(self) -> str:
        raw = "".join(self._chunks)
        raw = unescape(raw)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


@dataclass(slots=True)
class ParsedCommand:
    tokens: list[str]
    contains_shell_metacharacters: bool


SHELL_META_RE = re.compile(r"(\|\||&&|[|;<>`]|\$\(|\$\{|\*|\?)")
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def parse_command(command: str) -> ParsedCommand:
    stripped = command.strip()
    meta = bool(SHELL_META_RE.search(stripped))
    if meta:
        tokens = stripped.split()
    else:
        import shlex
        tokens = shlex.split(stripped)
    return ParsedCommand(tokens=tokens, contains_shell_metacharacters=meta)



def normalize_url(url: str, *, upgrade_insecure: bool = True, strip_fragment: bool = True) -> str:
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    if not scheme:
        parsed = urlparse("https://" + url.strip())
        scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError(f"unsupported URL scheme: {scheme}")
    if upgrade_insecure and scheme == "http":
        parsed = parsed._replace(scheme="https")
    if parsed.username or parsed.password:
        raise ValueError("credentials in URLs are not allowed")
    netloc = parsed.netloc.encode("idna").decode("ascii")
    path = quote(unquote(parsed.path or "/"), safe="/%:@")
    query = urlencode(parse_qsl(parsed.query, keep_blank_values=True), doseq=True)
    fragment = "" if strip_fragment else parsed.fragment
    normalized = urlunparse(ParseResult(
        scheme=parsed.scheme,
        netloc=netloc,
        path=path,
        params="",
        query=query,
        fragment=fragment,
    ))
    return normalized



def extract_domain(url: str) -> str:
    return (urlparse(url).hostname or "").lower()



def resolve_host_ips(hostname: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return []
    ips = []
    for info in infos:
        addr = info[4][0]
        if addr not in ips:
            ips.append(addr)
    return ips



def is_private_host(hostname: str) -> bool:
    host = hostname.lower()
    if host in {"localhost", "localhost.localdomain"}:
        return True
    try:
        ip = ip_address(host)
        return any(ip in network for network in _PRIVATE_NETWORKS)
    except ValueError:
        pass
    for raw_ip in resolve_host_ips(host):
        try:
            ip = ip_address(raw_ip)
            if any(ip in network for network in _PRIVATE_NETWORKS):
                return True
        except ValueError:
            continue
    return False



def matches_any(value: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(value, pattern) for pattern in patterns)



def is_within_roots(path: Path, roots: Iterable[Path]) -> bool:
    resolved = path.resolve()
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False



def compact_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"



def extract_title(html: str) -> str:
    match = TITLE_RE.search(html)
    if not match:
        return ""
    return re.sub(r"\s+", " ", unescape(match.group(1))).strip()



def html_to_text(html: str) -> str:
    parser = VisibleTextExtractor()
    parser.feed(html)
    return parser.text()



def keyword_spans(text: str, query: str, *, max_spans: int = 6, span_radius: int = 220) -> str:
    query_terms = [term.lower() for term in re.findall(r"[\w-]{3,}", query)]
    if not query_terms:
        return compact_text(text, 2000)

    lowered = text.lower()
    spans: list[tuple[int, int, int]] = []
    for term in query_terms:
        start = 0
        while True:
            index = lowered.find(term, start)
            if index < 0:
                break
            left = max(0, index - span_radius)
            right = min(len(text), index + len(term) + span_radius)
            score = sum(lowered[left:right].count(t) for t in query_terms)
            spans.append((left, right, score))
            start = index + len(term)
    if not spans:
        return compact_text(text, 2000)

    spans.sort(key=lambda item: (-item[2], item[0]))
    chosen: list[tuple[int, int]] = []
    for left, right, _ in spans:
        if any(not (right < c_left or left > c_right) for c_left, c_right in chosen):
            continue
        chosen.append((left, right))
        if len(chosen) >= max_spans:
            break
    chosen.sort()
    excerpts = []
    for left, right in chosen:
        excerpt = text[left:right].strip()
        if left > 0:
            excerpt = "…" + excerpt
        if right < len(text):
            excerpt = excerpt + "…"
        excerpts.append(excerpt)
    return "\n\n".join(excerpts)
