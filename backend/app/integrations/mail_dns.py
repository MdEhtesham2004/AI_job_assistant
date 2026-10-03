"""MX lookup: does the domain of an address accept email at all?"""

from typing import Protocol

import dns.asyncresolver
import dns.exception
import dns.resolver


class DomainChecker(Protocol):
    async def accepts_mail(self, domain: str) -> bool | None:
        """True / False, or None when DNS could not answer (unknown)."""


class DnsDomainChecker:
    def __init__(self, timeout: float = 5.0) -> None:
        self.timeout = timeout

    async def accepts_mail(self, domain: str) -> bool | None:
        resolver = dns.asyncresolver.Resolver()
        resolver.lifetime = self.timeout
        try:
            answer = await resolver.resolve(domain, "MX")
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            # No MX: mail falls back to the A record (RFC 5321 §5.1).
            try:
                await resolver.resolve(domain, "A")
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                return False
            except dns.exception.DNSException:
                return None
            return True
        except dns.exception.DNSException:
            return None
        # A "null MX" (RFC 7505, preference 0 and ".") says the domain takes no mail.
        return not all(str(record.exchange) == "." for record in answer)
