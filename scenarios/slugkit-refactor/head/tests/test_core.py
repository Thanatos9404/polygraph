from slugkit import slugify, unique_slug


def test_basic():
    assert slugify("Hello World") == "hello-world"


def test_spaces_collapse():
    assert slugify("  Multiple   spaces  here ") == "multiple-spaces-here"


def test_accents():
    assert slugify("Café Crème") == "cafe-creme"


def test_unique():
    assert unique_slug("Hello World", {"hello-world"}) == "hello-world-2"
