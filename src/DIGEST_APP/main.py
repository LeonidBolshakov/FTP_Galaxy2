import traceback
from GENERAL.errors import ConfigLoadError, ConfigError


def main():
    from DIGEST_APP.APP.controller import DigestController
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
        print(f"Ошибка при загрузке параметров\n{e}")
    except ConfigError as e:
        print(f"Ошибка в параметрах:\n{e}")
    except FileNotFoundError as e:
        print(f"Файл не найден:\n{e}")
    except PermissionError as e:
        print(f"❌ Excel файл открыт. Закройте его и попробуйте снова.\n{e}")
    except OSError as e:
        print(f"Ошибка ввода-вывода:\n{e}")
    except Exception as e:
        print(f"Неизвестная ошибка:\n{e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
