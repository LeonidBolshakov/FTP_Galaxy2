from typing import Final, cast
from pathlib import Path
import re
from collections.abc import Iterator

from SRC.DIGEST_APP.APP.dto import RuntimeContext, DescriptionOfNewTask

EMPTY = "?????"


class DigestSectionKeys:
    TASK: Final[str] = "ЗАДАЧА В JIRA"
    FIRST_SOLUTION: Final[str] = "ПЕРВОЕ РЕШЕНИЕ"
    DESCRIPTION: Final[str] = "КРАТКОЕ ОПИСАНИЕ"
    WHAT_HAS_CHANGED: Final[str] = "ЧТО ИЗМЕНЕНО"
    HOW_IT_CHANGED: Final[str] = "КАК ИЗМЕНЕНО"

    @classmethod
    def all(cls) -> list[str]:
        return [
            v
            for k, v in cls.__dict__.items()
            if not k.startswith("__") and isinstance(v, str)
        ]


keys_re = "|".join(re.escape(k) for k in DigestSectionKeys.all())
# noinspection RegExpUnnecessaryNonCapturingGroup
pattern = re.compile(
    rf"^[#*]\s*({keys_re})\s*:\s*" rf"(.*?)" rf"(?=^\s*[#*]\s*(?:{keys_re})\s*:|\Z)",
    re.MULTILINE | re.DOTALL,
)


class GetDescriptionOfNewTasks:
    def run(self, ctx: RuntimeContext) -> list[DescriptionOfNewTask]:
        new_dir = self._get_new_dir(ctx)
        files = self._iter_files(new_dir)

        result: list[DescriptionOfNewTask] = []
        for file in files:
            text = self._read_text(file)
            result += self._parse_file_text(text, file.name)

        return result

    def _get_new_dir(self, ctx: RuntimeContext) -> Path:
        return cast(Path, ctx.app.new_dir)

    def _iter_files(self, new_dir: Path) -> Iterator[Path]:
        for file in new_dir.iterdir():
            if file.is_file():
                yield file

    def _read_text(self, file: Path) -> str:
        return file.read_text(encoding="ANSI")

    def _parse_file_text(self, text: str, file_name: str) -> list[DescriptionOfNewTask]:
        descriptions = self._split_record(text)
        return self._parse_descriptions(descriptions, file_name)

    def _split_record(self, text: str) -> list[str]:
        blocks = re.split(r"^\* \* \*$", text, flags=re.MULTILINE)
        return [block.strip() for block in blocks if block.strip()]

    def _extract_sections(self, block: str) -> dict[str, str]:
        matches = list(pattern.finditer(block))
        result: dict[str, str] = {}
        for m in matches:
            result[m.group(1).rstrip()] = m.group(2).rstrip()

        return result

    def _parse_descriptions(
            self, descriptions: list[str], file_name: str
    ) -> list[DescriptionOfNewTask]:

        result: list[DescriptionOfNewTask] = []
        for block in descriptions[1:]:
            sections: dict[str, str] = self._extract_sections(block)
            if not self._is_new_solution(sections):
                continue

            result.append(
                self._build_description_task(sections=sections, file_name=file_name)
            )

        return result

    def _is_new_solution(self, sections: dict[str, str]) -> bool:
        return sections.get(DigestSectionKeys.FIRST_SOLUTION) == "NEW"

    def _build_description_task(
            self, sections: dict[str, str], file_name: str
    ) -> DescriptionOfNewTask:
        return DescriptionOfNewTask(
            task=sections.get(DigestSectionKeys.TASK, EMPTY),
            first_solution=sections.get(DigestSectionKeys.FIRST_SOLUTION, EMPTY),
            component=[file_name],
            description=sections.get(DigestSectionKeys.DESCRIPTION, EMPTY),
            what_has_changed=sections.get(DigestSectionKeys.WHAT_HAS_CHANGED, EMPTY),
            how_it_changed=sections.get(DigestSectionKeys.HOW_IT_CHANGED, EMPTY),
        )
