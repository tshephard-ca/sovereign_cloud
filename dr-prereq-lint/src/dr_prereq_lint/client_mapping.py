"""Map DNS client identities to protected systems."""

from __future__ import annotations

from dataclasses import dataclass

from .models import DnsQueryRow, ProtectedSystem
from .normalize import normalize_fqdn, normalize_ip, short_name
from .recovery_set import system_display_name


@dataclass(frozen=True)
class ClientMapResult:
    system: ProtectedSystem | None
    match_basis: str = ""


class ClientMapper:
    def __init__(self, protected_systems: list[ProtectedSystem]) -> None:
        self.by_ip: dict[str, ProtectedSystem] = {}
        self.by_fqdn: dict[str, ProtectedSystem] = {}
        self.by_short: dict[str, ProtectedSystem] = {}
        self.by_alias: dict[str, ProtectedSystem] = {}
        for system in protected_systems:
            for ip in system.ip_addresses:
                self.by_ip.setdefault(normalize_ip(ip), system)
            if system.fqdn:
                self.by_fqdn.setdefault(normalize_fqdn(system.fqdn), system)
            if system.short_name:
                self.by_short.setdefault(system.short_name, system)
            for alias in system.aliases:
                normalized_alias = normalize_fqdn(alias)
                if normalized_alias:
                    self.by_alias.setdefault(normalized_alias, system)
                    self.by_short.setdefault(short_name(normalized_alias), system)

    def map_query(self, query: DnsQueryRow) -> ClientMapResult:
        if query.client_ip and query.client_ip in self.by_ip:
            return ClientMapResult(self.by_ip[query.client_ip], "client_ip")
        if query.client_name and query.client_name in self.by_fqdn:
            return ClientMapResult(self.by_fqdn[query.client_name], "client_name_fqdn")
        if query.client_name and short_name(query.client_name) in self.by_short:
            return ClientMapResult(self.by_short[short_name(query.client_name)], "client_name_short")
        if query.client_name and query.client_name in self.by_alias:
            return ClientMapResult(self.by_alias[query.client_name], "client_name_alias")
        return ClientMapResult(None, "")


def protected_system_key(system: ProtectedSystem | None) -> str:
    if system is None:
        return "unmapped"
    return system_display_name(system)
