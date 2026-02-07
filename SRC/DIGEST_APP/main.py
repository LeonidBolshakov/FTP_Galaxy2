from SRC.GENERAL.errors import ConfigLoadError, ConfigError


def main():
    from SRC.DIGEST_APP.dummies import (
        MakeGroupedDescriptions,
        OutputReport,
    )

    from SRC.DIGEST_APP.APP.controller import DigestController
    from SRC.DIGEST_APP.APP.SERVICES.get_context import GetContext
    from SRC.DIGEST_APP.APP.SERVICES.get_description_of_new_tasks import (
        GetDescriptionOfNewTasks,
    )

    context = GetContext()
    digest_controller = DigestController(
        context=context,
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
        print(f"Ошибка доступа к файлу:\n{e}")
    except OSError as e:
        print(f"Ошибка ввода-вывода:\n{e}")
    except Exception as e:
        print(f"Неизвестная ошибка:\n{e}")


if __name__ == "__main__":
    main()
