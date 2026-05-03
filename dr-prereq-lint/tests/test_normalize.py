from dr_prereq_lint.normalize import normalize_fqdn, normalize_ip_list, short_name


def test_normalizes_fqdn_by_lowercasing_and_stripping_trailing_dot():
    assert normalize_fqdn("App01.Example.Internal.") == "app01.example.internal"


def test_normalizes_short_names():
    assert short_name("App01.Example.Internal.") == "app01"


def test_normalizes_ip_lists():
    assert normalize_ip_list("10.0.0.1; 192.168.1.2|bad") == ["10.0.0.1", "192.168.1.2"]
