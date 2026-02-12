# Все сервисы контроллера реализуют use-case контракт:
#   run(input) -> output

from typing import Protocol, Sequence

from DIGEST_APP.APP.dto import (
    RuntimeContext,
    DescriptionOfNewTask,
)


class GetContext(Protocol):
    def run(self) -> RuntimeContext: ...


class GetDescriptionOfNewTasks(Protocol):
    def run(self, ctx: RuntimeContext) -> Sequence[DescriptionOfNewTask]: ...


class MakeGroupedDescriptions(Protocol):
    def run(
            self, descriptions: Sequence[DescriptionOfNewTask]
    ) -> list[DescriptionOfNewTask]: ...


class OutputReport(Protocol):
    def run(
            self, ctx: RuntimeContext, descriptions: list[DescriptionOfNewTask]
    ) -> None: ...
