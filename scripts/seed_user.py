"""단일 사용자 계정을 회원가입 흐름 없이 직접 생성한다.

1인 전용 앱이라 가입 UI를 거치지 않고 운영자가 계정을 미리 심어둔다.
비밀번호는 서비스와 동일한 bcrypt 해시로 저장하며, 평문은 인자/환경변수로만
받아 저장소에 남기지 않는다. 이미 같은 로그인 ID가 있으면 건너뛴다(멱등).

    python scripts/seed_user.py --login-id wns1915 --password 'forparents1!' --name Jake
    SEED_PASSWORD='forparents1!' python scripts/seed_user.py --login-id wns1915
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import async_session_factory  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.user_model import User  # noqa: E402
from app.repositories import user_repository  # noqa: E402


async def seed_user(login_id: str, password: str, name: str) -> None:
    async with async_session_factory() as db:
        existing = await user_repository.get_by_email(db, login_id)
        if existing is not None:
            print(f"이미 존재함 — 건너뜀: {login_id} (id={existing.id})")
            return

        user = User(email=login_id, password_hash=hash_password(password), name=name)
        user_repository.add(db, user)
        await db.commit()
        await db.refresh(user)
        print(f"생성 완료: {login_id} (id={user.id})")


def main() -> None:
    parser = argparse.ArgumentParser(description="단일 사용자 계정 생성")
    parser.add_argument("--login-id", required=True, help="로그인 ID(email 컬럼에 저장)")
    parser.add_argument(
        "--password",
        default=os.getenv("SEED_PASSWORD"),
        help="평문 비밀번호. 미지정 시 SEED_PASSWORD 환경변수 사용.",
    )
    parser.add_argument("--name", default=None, help="표시 이름. 기본값은 로그인 ID.")
    args = parser.parse_args()

    if not args.password:
        parser.error("비밀번호가 필요합니다(--password 또는 SEED_PASSWORD).")

    asyncio.run(seed_user(args.login_id, args.password, args.name or args.login_id))


if __name__ == "__main__":
    main()
