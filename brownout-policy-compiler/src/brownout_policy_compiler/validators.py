from __future__ import annotations

import ipaddress
import re
from typing import Iterable


PORT_RANGE_RE = re.compile(r"^(\d{1,5})-(\d{1,5})$")


def validate_ip_address(value: str) -> str:
    try:
        ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError(f"invalid IP address: {value}") from exc
    return value


def validate_ip_or_cidr(value: str) -> str:
    try:
        if "/" in value:
            ipaddress.ip_network(value, strict=False)
        else:
            ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError(f"invalid IP or CIDR: {value}") from exc
    return value


def validate_port_number(value: int) -> int:
    if value < 1 or value > 65535:
        raise ValueError(f"invalid port: {value}")
    return value


def validate_port_spec(value: int | str) -> int | str:
    if isinstance(value, int):
        return validate_port_number(value)
    match = PORT_RANGE_RE.match(value)
    if not match:
        raise ValueError(f"invalid port range: {value}")
    start = validate_port_number(int(match.group(1)))
    end = validate_port_number(int(match.group(2)))
    if start > end:
        raise ValueError(f"invalid port range: {value}")
    return value


def expand_port_spec(value: int | str) -> tuple[int, int]:
    validate_port_spec(value)
    if isinstance(value, int):
        return value, value
    start, end = value.split("-", 1)
    return int(start), int(end)


def ports_overlap(left: Iterable[int | str] | None, right: Iterable[int | str] | None) -> bool:
    if left is None or right is None:
        return True
    left_ranges = [expand_port_spec(item) for item in left]
    right_ranges = [expand_port_spec(item) for item in right]
    for left_start, left_end in left_ranges:
        for right_start, right_end in right_ranges:
            if left_start <= right_end and right_start <= left_end:
                return True
    return False


def ip_matches(event_ip: str, endpoint_ip: str) -> tuple[bool, bool]:
    event_addr = ipaddress.ip_address(event_ip)
    if "/" in endpoint_ip:
        network = ipaddress.ip_network(endpoint_ip, strict=False)
        return event_addr in network, True
    return event_addr == ipaddress.ip_address(endpoint_ip), False


def protocol_matches(event_protocol: str, endpoint_protocol: str) -> bool:
    return event_protocol == endpoint_protocol or event_protocol == "any" or endpoint_protocol == "any"


def normalize_ports(ports: Iterable[int | str] | None) -> list[int | str] | None:
    if ports is None:
        return None
    return list(ports)


def is_rfc1918_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return (
        address in ipaddress.ip_network("10.0.0.0/8")
        or address in ipaddress.ip_network("172.16.0.0/12")
        or address in ipaddress.ip_network("192.168.0.0/16")
    )


def is_cidr(value: str) -> bool:
    try:
        ipaddress.ip_network(value, strict=False)
        return "/" in value
    except ValueError:
        return False

