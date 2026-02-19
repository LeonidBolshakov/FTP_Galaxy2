from pathlib import Path
import re
from collections.abc import Iterator

from DIGEST_APP.APP.dto import RuntimeContext, DescriptionOfNewTask
from DIGEST_APP.APP.const import EMPTY, DigestSectionKeys, DigestSectionTitle

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
            result += self._parse_file_text(text, file)

        return result

    def _get_new_dir(self, ctx: RuntimeContext) -> Path:
        return Path(ctx.app.new_dir)

    def _iter_files(self, new_dir: Path) -> Iterator[Path]:
        if not new_dir.is_dir():
            return

        for file in new_dir.iterdir():
            if file.is_file():
                yield file

    def _read_text(self, file: Path) -> str:
        return file.read_text(encoding="cp1251", errors="replace")

    def _parse_file_text(
            self, text: str, file_name: Path
    ) -> list[DescriptionOfNewTask]:
        descriptions = self._split_record(text)
        return self._parse_descriptions(descriptions, file_name)

    def _split_record(self, text: str) -> list[str]:
        blocks = re.split(r"^\* \* \*$", text, flags=re.MULTILINE)
        return [block.strip() for block in blocks if block.strip()]

    def _extract_sections(self, block: str) -> dict[DigestSectionTitle, str]:
        matches = list(pattern.finditer(block))
        result: dict[DigestSectionTitle, str] = {}
        for m in matches:
            key_text = m.group(1).rstrip()
            value = m.group(2).rstrip()
            result[DigestSectionTitle(key_text)] = value

        return result

    def _parse_descriptions(
            self, descriptions: list[str], file: Path
    ) -> list[DescriptionOfNewTask]:

        result: list[DescriptionOfNewTask] = []
        for block in descriptions[1:]:
            sections = self._extract_sections(block)
            if not self._is_new_solution(sections):
                continue
            task_desc = self._build_description_task(sections, file)
            result.append(task_desc)

        return result

    def _is_new_solution(self, sections: dict[DigestSectionTitle, str]) -> bool:
        return sections.get(DigestSectionTitle.FIRST_SOLUTION) == "NEW"

    def _build_description_task(
            self, sections: dict[DigestSectionTitle, str], file: Path
    ) -> DescriptionOfNewTask:

        return DescriptionOfNewTask(
            task=sections.get(DigestSectionTitle.TASK, EMPTY),
            first_solution=sections.get(DigestSectionTitle.FIRST_SOLUTION, EMPTY),
            components=[file.stem],
            description=sections.get(DigestSectionTitle.DESCRIPTION, EMPTY),
            what_has_changed=sections.get(DigestSectionTitle.WHAT_HAS_CHANGED, EMPTY),
            how_it_changed=sections.get(DigestSectionTitle.HOW_IT_CHANGED, EMPTY),
        )
