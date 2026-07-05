"""SEC EDGAR HTTP 클라이언트 — Form 4 / 13D·13G / 8-K collector 공용 (SPEC §4).

- User-Agent에 연락 이메일 포함 (EDGAR 접근 정책 요구)
- rate limit 준수: 요청 간 최소 간격 스로틀 (SEC 상한 10 req/s 대비 여유)
- 최근 filing 목록은 getcurrent Atom 피드, 개별 filing은 전문(.txt) 조회
- filing 전문(SGML) 공용 헬퍼: acceptance datetime, 내장 XML 블록, 헤더 CIK
"""
import asyncio
import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from zoneinfo import ZoneInfo

import httpx

from app.core.config import settings
from app.services.macro_events.normalize import to_kst

_BASE_URL = "https://www.sec.gov"
_GETCURRENT_URL = f"{_BASE_URL}/cgi-bin/browse-edgar"
_HTTP_TIMEOUT = 15.0
# 요청 간 최소 간격(초). ~6.6 req/s — SEC 상한 10 req/s 아래로 유지.
_MIN_REQUEST_INTERVAL_SECONDS = 0.15

# EDGAR ACCEPTANCE-DATETIME은 미 동부시각 (예: 20260703212345)
EDGAR_TIMEZONE = ZoneInfo("America/New_York")

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
# Atom entry title 예: "4 - Doe John (0001234567) (Reporting)"
_TITLE_CIK_PATTERN = re.compile(r"\((\d{10})\)")
_ACCESSION_PATTERN = re.compile(r"accession-number=(\d{10}-\d{2}-\d{6})")
_ACCEPTANCE_PATTERN = re.compile(r"<ACCEPTANCE-DATETIME>\s*(\d{14})")
_EMBEDDED_XML_PATTERN = re.compile(r"<XML>\s*(.*?)\s*</XML>", re.DOTALL)
_HEADER_SECTION_CIK_PATTERN = r"{section}:.*?CENTRAL INDEX KEY:\s*(\d{{10}})"


@dataclass(frozen=True)
class EdgarFiling:
    """getcurrent 피드의 filing 한 건 (문서 내용은 별도 조회)."""

    accession_number: str
    cik: str
    form_type: str
    filing_url: str


class EdgarClient:
    """async context manager로 사용 — 커넥션 재사용 + 전 요청 공통 스로틀."""

    def __init__(self, user_agent: str = settings.SEC_EDGAR_USER_AGENT) -> None:
        self._headers = {"User-Agent": user_agent}
        self._last_request_at = 0.0
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "EdgarClient":
        self._client = httpx.AsyncClient(headers=self._headers, timeout=_HTTP_TIMEOUT)
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, url: str, params: dict[str, str] | None = None) -> httpx.Response:
        if self._client is None:
            raise RuntimeError("EdgarClient는 async with로 사용해야 함")

        elapsed = monotonic() - self._last_request_at
        wait = _MIN_REQUEST_INTERVAL_SECONDS - elapsed
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request_at = monotonic()

        response = await self._client.get(url, params=params)
        response.raise_for_status()
        return response

    async def fetch_recent_filings(
        self,
        query_type: str,
        count: int = 100,
        include_types: Sequence[str] | None = None,
    ) -> list[EdgarFiling]:
        """getcurrent Atom 피드에서 최근 filing 목록. accession 기준 dedup.

        피드 type 파라미터는 prefix 매칭이라 amendment 등이 섞여 온다 —
        include_types(기본: query_type 정확 일치)에 있는 form type만 남긴다."""
        response = await self._get(
            _GETCURRENT_URL,
            params={
                "action": "getcurrent",
                "type": query_type,
                "count": str(count),
                "output": "atom",
            },
        )
        accepted = include_types if include_types is not None else (query_type,)
        return parse_getcurrent_feed(response.text, accepted)

    async def fetch_filing_text(self, cik: str, accession_number: str) -> str:
        """filing 전문(.txt, SGML+내장 문서). 헤더에 ACCEPTANCE-DATETIME 포함."""
        accession_nodash = accession_number.replace("-", "")
        url = (
            f"{_BASE_URL}/Archives/edgar/data/{int(cik)}/"
            f"{accession_nodash}/{accession_number}.txt"
        )
        response = await self._get(url)
        return response.text


def parse_getcurrent_feed(feed_xml: str, form_types: Sequence[str]) -> list[EdgarFiling]:
    """Atom 피드 파싱. 한 filing이 filer 역할별로 중복 entry로 올 수 있어 accession dedup."""
    root = ET.fromstring(feed_xml)
    filings: dict[str, EdgarFiling] = {}

    for entry in root.findall("atom:entry", _ATOM_NS):
        category = entry.find("atom:category", _ATOM_NS)
        entry_form_type = category.get("term", "") if category is not None else ""
        if entry_form_type not in form_types:
            continue

        entry_id = entry.findtext("atom:id", default="", namespaces=_ATOM_NS)
        accession_match = _ACCESSION_PATTERN.search(entry_id)
        title = entry.findtext("atom:title", default="", namespaces=_ATOM_NS)
        cik_match = _TITLE_CIK_PATTERN.search(title)
        link = entry.find("atom:link", _ATOM_NS)
        if accession_match is None or cik_match is None or link is None:
            continue

        accession_number = accession_match.group(1)
        if accession_number in filings:
            continue
        filings[accession_number] = EdgarFiling(
            accession_number=accession_number,
            cik=cik_match.group(1),
            form_type=entry_form_type,
            filing_url=link.get("href", ""),
        )

    return list(filings.values())


def extract_acceptance_datetime(filing_text: str) -> datetime | None:
    """SGML 헤더의 ACCEPTANCE-DATETIME(ET) → aware KST. publicly_observable_at 기준(§4)."""
    match = _ACCEPTANCE_PATTERN.search(filing_text)
    if match is None:
        return None
    accepted = datetime.strptime(match.group(1), "%Y%m%d%H%M%S")
    return to_kst(accepted, source_tz=EDGAR_TIMEZONE)


def iter_embedded_xml(filing_text: str) -> list[str]:
    """filing 전문(.txt)에 내장된 <XML>...</XML> 블록 목록."""
    return _EMBEDDED_XML_PATTERN.findall(filing_text)


def extract_header_cik(filing_text: str, section: str) -> str | None:
    """SGML 헤더 섹션(SUBJECT COMPANY / FILED BY)의 CENTRAL INDEX KEY."""
    pattern = re.compile(
        _HEADER_SECTION_CIK_PATTERN.format(section=re.escape(section)), re.DOTALL
    )
    match = pattern.search(filing_text)
    return match.group(1) if match else None


def extract_header_company_name(filing_text: str, section: str) -> str | None:
    """SGML 헤더 섹션의 COMPANY CONFORMED NAME."""
    pattern = re.compile(
        rf"{re.escape(section)}:.*?COMPANY CONFORMED NAME:\s*([^\r\n]+)", re.DOTALL
    )
    match = pattern.search(filing_text)
    return match.group(1).strip() if match else None
