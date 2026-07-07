import pytest
from fastapi import HTTPException

from app.security import (
    LoginRateLimiter,
    mask_phone,
    sanitize_user_info,
    validate_password_strength,
)


class TestMaskPhone:
    def test_masks_turkish_number(self):
        assert mask_phone("+905551234567") == "+905***67"

    def test_empty(self):
        assert mask_phone("") == ""


class TestPasswordStrength:
    def test_weak_too_short(self):
        with pytest.raises(ValueError, match="8 karakter"):
            validate_password_strength("abc1")

    def test_requires_letter_and_digit(self):
        with pytest.raises(ValueError, match="rakam"):
            validate_password_strength("abcdefgh")
        with pytest.raises(ValueError, match="harf"):
            validate_password_strength("12345678")

    def test_valid_password(self):
        validate_password_strength("securepass1")


class TestLoginRateLimiter:
    def test_locks_after_max_attempts(self):
        limiter = LoginRateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=120)
        ip = "127.0.0.1"
        limiter.check_allowed(ip)
        limiter.record_failure(ip)
        limiter.record_failure(ip)
        limiter.record_failure(ip)
        with pytest.raises(HTTPException) as exc:
            limiter.check_allowed(ip)
        assert exc.value.status_code == 429

    def test_success_clears_attempts(self):
        limiter = LoginRateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=120)
        ip = "10.0.0.1"
        limiter.record_failure(ip)
        limiter.record_failure(ip)
        limiter.record_success(ip)
        limiter.check_allowed(ip)


class TestSanitizeUser:
    def test_masks_phone_in_user_dict(self):
        result = sanitize_user_info({"name": "Ali", "phone": "+905551234567"})
        assert result["phone"] == "+905***67"
        assert result["name"] == "Ali"
