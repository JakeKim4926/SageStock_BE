"""strong domain keyword 매칭 (SPEC §6.1·§6.7 공용).

SAM.gov title, Defense.gov 계약 항목 본문 등 짧은 텍스트에 대해
keyword_domain_map.yaml 기준의 strong 매칭을 판정한다.
도메인 할당(§9)은 Phase 2 파이프라인 소유 — 여기서는 수집 필터 판정만 한다.
"""
import re

from app.services.macro_events.config_loader import KeywordDomainMap


def strong_keyword_match(text: str, keyword_map: KeywordDomainMap) -> tuple[bool, list[str]]:
    """strong 기준: phrase 1개, 또는 같은 domain 핵심 keyword 2개 이상.

    ambiguous keyword는 핵심 keyword로 세지 않는다."""
    lowered = text.lower()
    for domain, rules in keyword_map.domains.items():
        matched: list[str] = []
        for phrase in rules.phrase_keywords:
            if phrase.lower() in lowered:
                return True, [phrase]
        for keyword in rules.keywords:
            if re.search(rf"\b{re.escape(keyword.lower())}\b", lowered):
                matched.append(keyword)
        if len(matched) >= 2:
            return True, matched
    return False, []
