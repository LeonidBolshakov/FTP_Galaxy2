from typing import Sequence
from copy import deepcopy

from DIGEST_APP.APP.dto import DescriptionOfNewTask


class MakeGroupedDescriptions:
    def run(
            self, descriptions: Sequence[DescriptionOfNewTask]
    ) -> list[DescriptionOfNewTask]:

        by_task: dict[str, DescriptionOfNewTask] = {}

        for description in descriptions:
            if description.task not in by_task:
                by_task[description.task] = deepcopy(description)
            else:
                by_task[description.task].components.append(description.components[0])

        return list(by_task.values())
