from SRC.DIGEST_APP.APP.dto import DescriptionOfNewTask, RuntimeContext


class MakeGroupedDescriptions:
    def run(
            self, ctx: RuntimeContext, descriptions: DescriptionOfNewTask
    ) -> DescriptionOfNewTask:
        print("MakeGroupedDescriptions.run")
        return descriptions


class OutputReport:
    def run(self, ctx: RuntimeContext, descriptions: DescriptionOfNewTask) -> None:
        print("OutputReport.run")
        return
