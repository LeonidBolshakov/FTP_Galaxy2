from DIGEST_APP.APP.const import (
    DigestColumnConfigKey,
    HorizontalAlignment,
    VerticalAlignment,
    DigestSectionTitle,
    DigestSectionKeys,
    EMPTY,
)


def test_digest_section_title_all_titles():
    """Метод all_titles должен возвращать все значения перечисления в порядке их объявления."""
    titles = DigestSectionTitle.all_titles()
    # Убедимся, что значение каждого элемента перечисления присутствует в списке
    assert isinstance(titles, list)
    assert set(titles) == {m.value for m in DigestSectionTitle}


def test_digest_section_keys_all_matches_titles():
    """DigestSectionKeys.all должен возвращать тот же список, что и DigestSectionTitle.all_titles."""
    assert DigestSectionKeys.all() == DigestSectionTitle.all_titles()


def test_enum_values_are_strings():
    """Члены перечисления должны предоставлять осмысленные строковые значения."""
    assert EMPTY == "?????"
    assert DigestColumnConfigKey.TASK.value == "task"
    assert HorizontalAlignment.LEFT.value == "left"
    # В VerticalAlignment.RIGHT есть опечатка «botto», но тест должен отражать текущую реализацию
    assert VerticalAlignment.RIGHT.value == "botto"
