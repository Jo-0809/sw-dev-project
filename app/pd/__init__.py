"""PD 계층 (Problem Domain) — 6개 패키지: 사용자, 관심출처, 공지수집, 공고, 알림, 외부.

패키지 의존 (패키지 다이어그램, 10개, 순환 없음)
  공지수집(collect) → 관심출처(source) · 공고(notice) · 외부(external)
  알림(notify)      → 공고(notice) · 사용자(user) · 외부(external)
  공고(notice)      → 관심출처(source) · 사용자(user)
  관심출처(source)  → 사용자(user) · 외부(external)
tests/test_architecture.py 가 이 규칙을 검사한다.
"""
