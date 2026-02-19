from __future__ import annotations

from pathlib import Path
from typing import Final, Self, Iterable, Mapping, TypeVar, Any

from pydantic import BaseModel, Field, model_validator

from GENERAL.config import CommonConfig
from DIGEST_APP.APP.const import (
    DigestColumnConfigKey,
    HorizontalAlignment,
    VerticalAlignment,
)

# =============================================================================
# Base helpers
# =============================================================================

T = TypeVar("T", bound=BaseModel)


def merge_model_defaults(base: T, override: T | dict[str, Any] | None) -> T:
    """
    Возвращает НОВЫЙ объект модели:
    - override=None        -> глубокая копия base
    - override=BaseModel  -> base + override (по заданным полям)
    - override=dict       -> base + dict (как partial update)
    """
    if override is None:
        return base.model_copy(deep=True)

    if isinstance(override, BaseModel):
        update = override.model_dump(exclude_unset=True)
    elif isinstance(override, dict):
        update = override
    else:
        raise TypeError(f"Неподдерживаемый тип: {type(override)}")

    return base.model_copy(update=update, deep=True)


# =============================================================================
# Style configs
# =============================================================================


class FontConfig(BaseModel):
    name: str = "Calibri"
    size: int = Field(default=10, gt=0)
    bold: bool = False


class AlignmentConfig(BaseModel):
    horizontal: HorizontalAlignment = HorizontalAlignment.LEFT
    vertical: VerticalAlignment = VerticalAlignment.TOP
    wrap_text: bool = True


# =============================================================================
# Column + Header configs
# =============================================================================


class ColumnConfig(BaseModel):
    key: DigestColumnConfigKey
    header: str
    width: int = Field(gt=0)
    font: FontConfig = Field(default_factory=FontConfig)
    alignment: AlignmentConfig = Field(default_factory=AlignmentConfig)


ColumnsInDefaultOrder = tuple[ColumnConfig, ...]


class HeaderConfig(BaseModel):
    font: FontConfig = Field(default_factory=lambda: FontConfig(bold=True))


class DefaultConfig(BaseModel):
    auto_filter: bool = True
    font: FontConfig = Field(default_factory=FontConfig)


# =============================================================================
# Defaults registry (инвариант порядка и состава)
# =============================================================================


class DigestColumnsDefaults:
    ORDER: Final[tuple[DigestColumnConfigKey, ...]] = (
        DigestColumnConfigKey.TASK,
        DigestColumnConfigKey.COMPONENTS,
        DigestColumnConfigKey.DESCRIPTION,
        DigestColumnConfigKey.WHAT_CHANGED,
        DigestColumnConfigKey.HOW_CHANGED,
    )

    BASE_BY_KEY: Final[dict[DigestColumnConfigKey, ColumnConfig]] = {
        DigestColumnConfigKey.TASK: ColumnConfig(
            key=DigestColumnConfigKey.TASK,
            header="ЗАДАЧА В JIRA",
            width=13,
            font=FontConfig(size=11),
        ),
        DigestColumnConfigKey.COMPONENTS: ColumnConfig(
            key=DigestColumnConfigKey.COMPONENTS,
            header="КОМПОНЕНТЫ",
            width=30,
        ),
        DigestColumnConfigKey.DESCRIPTION: ColumnConfig(
            key=DigestColumnConfigKey.DESCRIPTION,
            header="КРАТКОЕ ОПИСАНИЕ",
            width=30,
            font=FontConfig(size=11),
        ),
        DigestColumnConfigKey.WHAT_CHANGED: ColumnConfig(
            key=DigestColumnConfigKey.WHAT_CHANGED,
            header="ЧТО ИЗМЕНЕНО",
            width=50,
        ),
        DigestColumnConfigKey.HOW_CHANGED: ColumnConfig(
            key=DigestColumnConfigKey.HOW_CHANGED,
            header="КАК ИЗМЕНЕНО",
            width=50,
        ),
    }


# =============================================================================
# Excel config
# =============================================================================


class ExcelConfig(BaseModel):
    excel_path: Path = Path(r"c:\Дистрибутив\digest.xlsx")

    default: DefaultConfig = Field(default_factory=DefaultConfig)
    header: HeaderConfig = Field(default_factory=HeaderConfig)
    alignment: AlignmentConfig = Field(default_factory=AlignmentConfig)
    columns: ColumnsInDefaultOrder = Field(default_factory=tuple)


# =============================================================================
# Normalization helpers
# =============================================================================


def _index_by_key(
        cols: Iterable[ColumnConfig],
) -> dict[DigestColumnConfigKey, ColumnConfig]:
    out: dict[DigestColumnConfigKey, ColumnConfig] = {}
    for c in cols:
        if c.key in out:
            raise ValueError(f"Дубликат key в excel.columns: {c.key}")
        out[c.key] = c
    return out


def merge_with_defaults(
        *,
        base_col: ColumnConfig,
        override_col: ColumnConfig | None,
        base_font: FontConfig,
        base_alignment: AlignmentConfig,
) -> ColumnConfig:
    merged = merge_model_defaults(base_col, override_col)

    merged.font = merge_model_defaults(base_font, merged.font)
    merged.alignment = merge_model_defaults(base_alignment, merged.alignment)

    # key фиксируем жёстко
    merged.key = base_col.key
    return merged


def normalize_columns(
        *,
        overrides: Iterable[ColumnConfig],
        base_by_key: Mapping[DigestColumnConfigKey, ColumnConfig],
        order: tuple[DigestColumnConfigKey, ...],
        base_font: FontConfig,
        base_alignment: AlignmentConfig,
) -> ColumnsInDefaultOrder:
    overrides_by_key = _index_by_key(overrides)

    unknown = [k for k in overrides_by_key if k not in base_by_key]
    if unknown:
        raise ValueError(f"Неизвестные колонки в excel.columns: {unknown}")

    result: list[ColumnConfig] = []
    for key in order:
        result.append(
            merge_with_defaults(
                base_col=base_by_key[key],
                override_col=overrides_by_key.get(key),
                base_font=base_font,
                base_alignment=base_alignment,
            )
        )

    return tuple(result)


# =============================================================================
# Root config
# =============================================================================


class DigestConfig(CommonConfig):
    excel: ExcelConfig = Field(default_factory=ExcelConfig)

    @model_validator(mode="after")
    def _finalize_excel(self) -> Self:
        base_font = self.excel.default.font
        base_alignment = self.excel.alignment

        # 1) нормализуем колонки (порядок + дефолты)
        self.excel.columns = normalize_columns(
            overrides=self.excel.columns,
            base_by_key=DigestColumnsDefaults.BASE_BY_KEY,
            order=DigestColumnsDefaults.ORDER,
            base_font=base_font,
            base_alignment=base_alignment,
        )

        # 2) header: base font + bold=True + override из YAML
        header_base = merge_model_defaults(base_font, FontConfig(bold=True))
        self.excel.header.font = merge_model_defaults(
            header_base, self.excel.header.font
        )

        return self
