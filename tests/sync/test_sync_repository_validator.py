from SYNC_APP.APP.SERVICES.repository_validator import RepositoryValidator


def test_get_component_names_and_duplicates():
    rv = RepositoryValidator()
    files = ["COMP_1.zip", "COMP_2.zip", "OTHER_3.zip", "OTHER_3.zip", "no_suffix.txt"]
    names = rv.get_component_names(files)
    # Учитываются только имена с числовым суффиксом
    assert names.count("COMP") == 2
    assert names.count("OTHER") == 2
    dups = rv.get_dublicate_component(names)
    # И "COMP", и "OTHER" встречаются дважды, поэтому счётчик дублей должен быть {имя: 1}
    assert dups == {"COMP": 1, "OTHER": 1}
    reports = rv.output_to_reports(dups)
    assert len(reports) == 2
    # Каждый отчёт должен иметь статус ERROR
    from SYNC_APP.APP.types import StatusReport

    assert all(r.status is StatusReport.ERROR for r in reports)


def test_run_aggregates_results():
    rv = RepositoryValidator()
    files = ["A_1.txt", "A_2.txt", "B_3.txt"]
    # Метод run возвращает элементы отчёта (одна запись о дублирующемся компоненте 'A')
    res = rv.run(data=type("Input", (), {"names": files}))
    assert len(res) == 1
    item = res[0]
    assert item.name == "A"
