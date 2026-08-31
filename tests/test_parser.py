from hosts_manager.models import LineKind
from hosts_manager.parser import parse, serialize


SAMPLE = """\
127.0.0.1\tlocalhost
::1\tlocalhost ip6-localhost ip6-loopback

# The following lines are desirable
127.0.0.1 app.local  # Local application
# 127.0.0.1 old.app.local  # Old server (disabled)
this is not a hosts line
"""


def test_parses_enabled_entry_with_inline_comment():
    doc = parse("127.0.0.1 app.local  # Local application\n")
    line = doc.lines[0]
    assert line.kind == LineKind.ENTRY
    assert line.ip == "127.0.0.1"
    assert line.hostnames == ["app.local"]
    assert line.comment == "Local application"
    assert line.enabled is True


def test_parses_disabled_entry():
    doc = parse("# 127.0.0.1 app.local\n")
    line = doc.lines[0]
    assert line.kind == LineKind.DISABLED_ENTRY
    assert line.ip == "127.0.0.1"
    assert line.hostnames == ["app.local"]
    assert line.enabled is False


def test_standalone_comment_is_not_a_disabled_entry():
    doc = parse("# The following lines are desirable for IPv4 capable hosts\n")
    assert doc.lines[0].kind == LineKind.COMMENT


def test_preserves_unknown_lines():
    doc = parse("this is not a hosts line\n")
    assert doc.lines[0].kind == LineKind.UNKNOWN
    assert doc.lines[0].raw == "this is not a hosts line"


def test_parses_ipv6_and_aliases_as_one_line():
    doc = parse("::1 localhost ip6-localhost\n")
    line = doc.lines[0]
    assert line.kind == LineKind.ENTRY
    assert line.ip == "::1"
    assert line.hostnames == ["localhost", "ip6-localhost"]


def test_parses_managed_markers():
    text = "# BEGIN Hosts Manager\n# END Hosts Manager\n"
    doc = parse(text)
    assert doc.lines[0].kind == LineKind.MANAGED_BEGIN
    assert doc.lines[1].kind == LineKind.MANAGED_END


def test_round_trip_preserves_unmanaged_lines_exactly():
    assert serialize(parse(SAMPLE)) == SAMPLE


def test_blank_lines_are_preserved():
    text = "127.0.0.1 localhost\n\n# comment\n"
    assert serialize(parse(text)) == text


def test_comment_only_ip_without_hostname_stays_comment():
    doc = parse("# 127.0.0.1\n")
    assert doc.lines[0].kind == LineKind.COMMENT


def test_lines_carry_one_based_line_numbers():
    doc = parse("127.0.0.1 localhost\n\n# c\n")
    assert [line.lineno for line in doc.lines] == [1, 2, 3]


def test_unknown_line_reports_missing_hostname_fault():
    doc = parse("127.0.0.1\n")
    line = doc.lines[0]
    assert line.kind == LineKind.UNKNOWN
    assert line.fault == "Not a hosts entry (expected: IP hostname)"


def test_unknown_line_reports_invalid_ip_fault():
    doc = parse("999.999.999.999 foo.local\n")
    line = doc.lines[0]
    assert line.kind == LineKind.UNKNOWN
    assert line.fault == "Invalid IP address: 999.999.999.999"


def test_unknown_line_reports_invalid_hostname_fault():
    doc = parse("127.0.0.1 bad_hostname\n")
    line = doc.lines[0]
    assert line.kind == LineKind.UNKNOWN
    assert line.fault == "Invalid hostname: bad_hostname"


def test_valid_lines_have_empty_fault():
    doc = parse("127.0.0.1 app.local  # Local application\n")
    assert doc.lines[0].fault == ""
