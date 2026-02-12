from pydantic import model_validator, BaseModel
from pathlib import Path
from typing import Self


class CommonConfig(BaseModel):
    local_dir: Path | None = None
    new_dir: Path | None = None

    @model_validator(mode="after")
    def _get_dirs(self) -> Self:
        if self.loca_dir is None:
            print("Не задан параметр local_dir")
        if self.new_dir is None:
            self.new_dir = self.local_dir / "NEW"
        return self
