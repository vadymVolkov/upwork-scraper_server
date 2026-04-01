from src.core.errors import CookiesMissingError, ValidationError, map_runtime_error


def test_map_runtime_error_validation():
    err = map_runtime_error(RuntimeError("search.limit is required and must be an integer from 1 to 100."))
    assert isinstance(err, ValidationError)


def test_map_runtime_error_cookies():
    err = map_runtime_error(RuntimeError("Cookies not found. Run login command first."))
    assert isinstance(err, CookiesMissingError)
