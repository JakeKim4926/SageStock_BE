from typing import Final

# feature-spec §4.6 가상매매 고정값(코드 레벨).
# 계정 생성 시 초기 예수금 = 시드. 서버 귀속 후 계정별 관리(api-spec §4).
VIRTUAL_CASH_SEED: Final = 10_000_000.0
