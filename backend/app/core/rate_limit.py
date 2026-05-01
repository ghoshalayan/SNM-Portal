"""
Simple in-memory rate limiter for login endpoint.
Tracks failed attempts per IP and blocks after threshold.
"""

import time
from collections import defaultdict
from fastapi import Request, HTTPException, status


class RateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 300, lockout_seconds: int = 600):
        """
        max_attempts:    Number of failed attempts before lockout.
        window_seconds:  Time window to count failures (default 5 min).
        lockout_seconds: How long to lock out after exceeding attempts (default 10 min).
        """
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        # { ip: [(timestamp, success), ...] }
        self._attempts: dict[str, list[float]] = defaultdict(list)
        self._lockouts: dict[str, float] = {}

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _cleanup(self, ip: str) -> None:
        """Remove attempts older than the window."""
        cutoff = time.time() - self.window_seconds
        self._attempts[ip] = [t for t in self._attempts[ip] if t > cutoff]

    def check(self, request: Request) -> None:
        """Raise 429 if the IP is locked out."""
        ip = self._get_client_ip(request)

        # Check lockout
        lockout_until = self._lockouts.get(ip)
        if lockout_until and time.time() < lockout_until:
            remaining = int(lockout_until - time.time())
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed login attempts. Try again in {remaining} seconds.",
            )
        elif lockout_until:
            # Lockout expired — clear
            del self._lockouts[ip]
            self._attempts.pop(ip, None)

    def record_failure(self, request: Request) -> None:
        """Record a failed login attempt. Enforce lockout if threshold exceeded."""
        ip = self._get_client_ip(request)
        self._cleanup(ip)
        self._attempts[ip].append(time.time())

        if len(self._attempts[ip]) >= self.max_attempts:
            self._lockouts[ip] = time.time() + self.lockout_seconds
            self._attempts.pop(ip, None)

    def record_success(self, request: Request) -> None:
        """Clear attempts on successful login."""
        ip = self._get_client_ip(request)
        self._attempts.pop(ip, None)
        self._lockouts.pop(ip, None)


# Singleton instance: 5 failed attempts in 5 min → locked out for 10 min
login_rate_limiter = RateLimiter(max_attempts=5, window_seconds=300, lockout_seconds=600)
