# Все сервисы контроллера реализуют use-case контракт:
#   run(input) -> output

from typing import Protocol, Sequence

from SRC.DIGEST_APP.APP.dto import (
    RuntimeContext,
    DescriptionOfNewTask,
)


class GetContext(Protocol):
    def run(self) -> RuntimeContext: ...


class GetDescriptionOfNewTasks(Protocol):
    def run(self, ctx: RuntimeContext) -> Sequence[DescriptionOfNewTask]: ...


class MakeGroupedDescriptions(Protocol):
    def run(
            self, ctx: RuntimeContext, descriptions: Sequence[DescriptionOfNewTask]
    ) -> Sequence[DescriptionOfNewTask]: ...


class OutputReport(Protocol):
    def run(self, ctx: RuntimeContext, descriptions: DescriptionOfNewTask) -> None: ...
