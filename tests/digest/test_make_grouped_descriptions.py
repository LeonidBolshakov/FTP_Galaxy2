from DIGEST_APP.APP.SERVICES.make_grouped_descriptions import MakeGroupedDescriptions
from tests.utils import d, get_by_task


def test_empty_tasks():
    assert MakeGroupedDescriptions().run([]) == []


def test_all_unique_tasks():
    a1 = d("A", "AA")
    t1 = d("T", "TT")
    b1 = d("B", "BB")

    res = MakeGroupedDescriptions().run([a1, t1, b1])

    assert len(res) == 3
    assert get_by_task(res, "A").components == ["AA"]
    assert get_by_task(res, "T").components == ["TT"]
    assert get_by_task(res, "B").components == ["BB"]


def test_two_components_grouped_by_task():
    a1 = d("A", "AA")
    c1 = d("C", "CC")
    a2 = d("A", "DD")
    e1 = d("E", "EE")

    res = MakeGroupedDescriptions().run([a1, c1, a2, e1])

    assert len(res) == 3
    assert get_by_task(res, "A").components == ["AA", "DD"]
    assert get_by_task(res, "C").components == ["CC"]
    assert get_by_task(res, "E").components == ["EE"]


def test_make_grouped_descriptions_mutates_input_objects():
    a1 = d("A", "AA")
    a2 = d("A", "DD")

    assert a1.components == ["AA"]
    assert a2.components == ["DD"]

    _ = MakeGroupedDescriptions().run([a1, a2])

    # Проверка на Side-effect
    assert a1.components == ["AA"]
    assert a2.components == ["DD"]
