"""Валидация репозитория после синхронизации.

Модуль содержит `RepositoryValidator` — набор дополнительных проверок целостности
локального репозитория после выполнения основного цикла синхронизации.

Текущая проверка
----------------
Проверяет, что в репозитории нет "дубликатов компонентов" по схеме именования:

- имя файла разбивается по последнему символу `_` (через `str.rpartition("_")`);
- если хвостовая часть (после `_`) состоит *только* из цифр, то "именем компонента"
  считается префикс до `_`;
- если один и тот же компонент встречается несколько раз (например, `COMP_1`, `COMP_2`),
  это отражается в отчёте как ошибка.

Сервис не выбрасывает исключения: он возвращает `ReportItems`, которые затем
агрегируются контроллером и выводятся в итоговом отчёте.
"""

from collections import defaultdict
from pathlib import Path

from src.SYNC_APP.APP.dto import (
    ValidateRepositoryInput,
    ReportItems,
    ReportItem,
    StatusReport,
)


class RepositoryValidator:
    """Дополнительные проверки репозитория после синхронизации.

    Основная цель — найти потенциально некорректные состояния, которые не ловятся
    на этапах diff/transfer/validate (например, несколько версий одного компонента).
    """

    def run(self, data: ValidateRepositoryInput) -> ReportItems:
        """Запускает проверки и возвращает отчёт.

        Parameters
        ----------
        data
            Входные данные: контекст и снимок репозитория (`RepositorySnapshot`).

        Returns
        -------
        ReportItems
            Список элементов отчёта. Пустой список означает, что проблем не обнаружено.
        """
        # `data.snapshot.files` — dict: имя файла -> FileSnapshot.
        # `list(dict)` в Python даёт список ключей (имён файлов).
        repositiry_files: list[str] = data.names
        component_names: list[str] = self.get_component_names(repositiry_files)
        dublicate_components = self.get_dublicate_component(component_names)
        return self.output_to_reports(dublicate_components)

    def get_component_names(self, repositiry_files: list[str]) -> list[str]:
        """Извлекает "имена компонентов" из списка имён файлов.

        Логика:
        - берётся последнее разделение по `_`;
        - если часть после `_` состоит только из цифр, то компонентом считается префикс.

        Parameters
        ----------
        repositiry_files
            Список имён файлов (ключи `RepositorySnapshot.files`).

        Returns
        -------
        list[str]
            Список имён компонентов (префиксы до `_`), потенциально содержащий повторы.
        """
        component_names = []
        for repositiry_file in repositiry_files:
            repositiry_path = Path(repositiry_file)
            component_name = repositiry_path.stem.rpartition("_")

            if component_name[2].isdigit():
                component_names.append(component_name[0])

        return component_names

    def get_dublicate_component(self, component_names: list[str]) -> dict[str, int]:
        """Подсчитывает количество повторов для каждого компонента.

        Parameters
        ----------
        component_names
            Имена компонентов (возможно с повторами).

        Returns
        -------
        dict[str, int]
            Словарь: имя компонента -> число "дополнительных" вхождений.
            Например, если компонент встретился 3 раза, значение будет 2.
        """
        dublicate_components: dict[str, int] = defaultdict(int)
        sorted_component_names = sorted(component_names)
        component_name_prev: str | None = None
        for component_name in sorted_component_names:
            if component_name == component_name_prev:
                dublicate_components[component_name] += 1
            component_name_prev = component_name

        return dublicate_components

    def output_to_reports(self, dublicate_components: dict[str, int]) -> ReportItems:
        """Преобразует найденные дубликаты в список `ReportItem`.

        Parameters
        ----------
        dublicate_components
            Словарь: имя компонента -> число дополнительных вхождений.

        Returns
        -------
        ReportItems
            Список ошибок уровня `StatusReport.ERROR`.
        """
        report: ReportItems = []
        for component_name, count in dublicate_components.items():
            report.append(
                ReportItem(
                    name=component_name,
                    status=StatusReport.ERROR,
                    comment=f"Компонент присутситвует в репозитории {count + 1} раза/раз",
                )
            )

        return report
