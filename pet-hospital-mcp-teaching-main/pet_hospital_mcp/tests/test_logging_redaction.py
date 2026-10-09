"""Sensitive fields must be masked recursively in logs."""

from pet_hospital_mcp.logging_config import REDACTED, redact


def test_redact_camel_and_snake_keys_at_all_depths() -> None:
    payload = {
        "ownerPhone": "13800001111",
        "ownerAddr": "北京市朝阳区某路1号",
        "chipNo": "CHIP-001",
        "nested": {
            "owner_phone": 13900002222,
            "list": [
                {"chip_no": "C-9", "name": "旺财"},
                {"owner_addr": "上海某地址", "q": "肠胃炎"},
            ],
        },
        "other": "kept",
    }

    masked = redact(payload)

    assert masked["ownerPhone"] == REDACTED
    assert masked["ownerAddr"] == REDACTED
    assert masked["chipNo"] == REDACTED
    assert masked["nested"]["owner_phone"] == REDACTED
    assert masked["nested"]["list"][0]["chip_no"] == REDACTED
    assert masked["nested"]["list"][1]["owner_addr"] == REDACTED
    # Non-sensitive values survive.
    assert masked["nested"]["list"][0]["name"] == "旺财"
    assert masked["other"] == "kept"
    # Original is untouched.
    assert payload["ownerPhone"] == "13800001111"


def test_redact_scalars_and_lists() -> None:
    assert redact("13800001111") == "13800001111"
    assert redact(42) == 42
    assert redact(None) is None
    assert redact(["x", {"ownerPhone": "1"}]) == ["x", {"ownerPhone": REDACTED}]
