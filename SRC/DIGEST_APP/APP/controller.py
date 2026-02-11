from SRC.DIGEST_APP.APP.ports import (
    GetContext,
    GetDescriptionOfNewTasks,
    MakeGroupedDescriptions,
    OutputReport,
)


class DigestController:
    def __init__(
            self,
            context: GetContext,
            get_description_of_new_tasks: GetDescriptionOfNewTasks,
            make_grouped_descriptions: MakeGroupedDescriptions,
            output_report: OutputReport,
    ):
        self.get_context = context
        self.get_description_of_new_tasks = get_description_of_new_tasks
        self.make_grouped_descriptions = make_grouped_descriptions
        self.output_report = output_report

    def run(self):
        runtime_context = self.get_context.run()

        description_of_new_tasks = self.get_description_of_new_tasks.run(
            ctx=runtime_context
        )

        grouped_descriptions = self.make_grouped_descriptions.run(
            descriptions=description_of_new_tasks
        )
        self.output_report.run(ctx=runtime_context, descriptions=grouped_descriptions)
