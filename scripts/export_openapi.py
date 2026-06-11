"""OpenAPI 스펙을 정적 파일로 추출한다.

서버를 띄우지 않고 FastAPI 앱에서 직접 OpenAPI 3.1 스펙을 뽑아
파일로 저장한다. 안드로이드 클라이언트 codegen / API 계약 공유용 SSOT.

`servers` URL은 기본적으로 placeholder로 덮어쓴다 — 공유/커밋용 스펙에
실제 호스트가 새어나가지 않도록. 실주소가 필요하면 env로 지정한다.

    python scripts/export_openapi.py                 # docs/openapi.json (placeholder server)
    python scripts/export_openapi.py build/spec.json  # 경로 지정
    OPENAPI_SERVER_URL=https://api.sagestock.app/v1 python scripts/export_openapi.py
"""

import json
import os
import sys
from pathlib import Path

# 프로젝트 루트를 import 경로에 추가 (스크립트 단독 실행 대비).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

DEFAULT_OUTPUT = Path("docs/openapi.json")
# 실주소 노출 방지용 기본값. 실제 base URL은 안드로이드 빌드 설정에서 주입한다.
PLACEHOLDER_SERVER = "https://api.example.com/v1"


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)

    spec = app.openapi()
    # env로 실주소를 명시하지 않는 한 placeholder로 덮어쓴다.
    server_url = os.getenv("OPENAPI_SERVER_URL", PLACEHOLDER_SERVER)
    spec["servers"] = [{"url": server_url}]

    # ensure_ascii=False: 한글 description 가독성 + 파일 크기 절감.
    output.write_text(
        json.dumps(spec, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    paths = len(spec.get("paths", {}))
    print(f"OpenAPI {spec['openapi']} → {output} ({paths} paths, server={server_url})")


if __name__ == "__main__":
    main()
