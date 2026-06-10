from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    # 와이어 포맷은 camelCase(api-spec §0). 내부는 snake_case 유지.
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
