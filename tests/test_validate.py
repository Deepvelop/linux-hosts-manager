import pytest

from hosts_manager.validate import ValidationError, validate_hostname, validate_ip


class TestValidateIp:
    def test_accepts_ipv4(self):
        validate_ip("127.0.0.1")
        validate_ip("192.168.1.50")
        validate_ip("0.0.0.0")

    def test_accepts_ipv6(self):
        validate_ip("::1")
        validate_ip("2001:db8::1")

    def test_rejects_empty(self):
        with pytest.raises(ValidationError):
            validate_ip("")

    def test_rejects_garbage(self):
        with pytest.raises(ValidationError):
            validate_ip("not-an-ip")
        with pytest.raises(ValidationError):
            validate_ip("127.0.0")
        with pytest.raises(ValidationError):
            validate_ip("999.0.0.1")


class TestValidateHostname:
    def test_accepts_localhost(self):
        validate_hostname("localhost")

    def test_accepts_dotted_names(self):
        validate_hostname("app.local")
        validate_hostname("api.app.local")

    def test_rejects_empty(self):
        with pytest.raises(ValidationError):
            validate_hostname("")

    def test_rejects_wildcard(self):
        with pytest.raises(ValidationError):
            validate_hostname("*")

    def test_rejects_spaces(self):
        with pytest.raises(ValidationError):
            validate_hostname("app local")

    def test_rejects_too_long(self):
        with pytest.raises(ValidationError):
            validate_hostname("a" * 254)

    def test_rejects_leading_hyphen(self):
        with pytest.raises(ValidationError):
            validate_hostname("-app.local")
