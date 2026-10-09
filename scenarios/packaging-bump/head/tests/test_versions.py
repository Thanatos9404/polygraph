from pluginhub import is_compatible, newest, sort_versions


def test_sort():
    assert sort_versions(["1.10", "1.2", "1.9"]) == ["1.2", "1.9", "1.10"]


def test_newest():
    assert newest(["0.9", "1.0rc1", "1.0"]) == "1.0"


def test_compatible():
    assert is_compatible("1.4.0", ">=1.2,<2")
