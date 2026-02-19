import traceback
from GENERAL.errors import ConfigLoadError, ConfigError, NewDirError


def main():
    from DIGEST_APP.APP.controller import DigestController
    from DIGEST_APP.APP.message import show_error
    from DIGEST_APP.APP.SERVICES.get_context import GetContext
    from DIGEST_APP.APP.SERVICES.get_description_of_new_tasks import (
        GetDescriptionOfNewTasks,
    )
    from DIGEST_APP.APP.SERVICES.make_grouped_descriptions import (
        MakeGroupedDescriptions,
    )
    from DIGEST_APP.APP.SERVICES.output_report import OutputReport

    digest_controller = DigestController(
        context=GetContext(),
        get_description_of_new_tasks=GetDescriptionOfNewTasks(),
        make_grouped_descriptions=MakeGroupedDescriptions(),
        output_report=OutputReport(),
    )

    try:
        digest_controller.run()
    except ConfigLoadError as e:
        show_error(f"Ошибка при загрузке параметров\n{str(e)}")
    except ConfigError as e:
        show_error(f"{str(e)}")
    except PermissionError as e:
        show_error(f"Excel файл открыт. Закройте его и попробуйте снова.\n{str(e)}")
    except OSError as e:
        show_error(f"Ошибка ввода-вывода:\n{str(e)}")
    except NewDirError as e:
        show_error(f"{str(e)}")
    except Exception as e:
        show_error(f"Неизвестная ошибка:\n{str(e)}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
