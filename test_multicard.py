"""
Quick smoke-test for multi-card logic.

Patches EasyPassScraper.fetch_cards to return two fake cards so you can
verify entity creation without owning a second physical card.

Usage:
    python test_multicard.py
"""

import sys
import types

# ---------------------------------------------------------------------------
# Stub homeassistant so the integration modules can be imported standalone
# ---------------------------------------------------------------------------
def _stub_ha():
    ha_mods = {
        "homeassistant": types.ModuleType("homeassistant"),
        "homeassistant.config_entries": types.ModuleType("homeassistant.config_entries"),
        "homeassistant.const": types.ModuleType("homeassistant.const"),
        "homeassistant.core": types.ModuleType("homeassistant.core"),
        "homeassistant.exceptions": types.ModuleType("homeassistant.exceptions"),
        "homeassistant.helpers": types.ModuleType("homeassistant.helpers"),
        "homeassistant.helpers.update_coordinator": types.ModuleType("homeassistant.helpers.update_coordinator"),
        "homeassistant.helpers.entity": types.ModuleType("homeassistant.helpers.entity"),
        "homeassistant.helpers.entity_platform": types.ModuleType("homeassistant.helpers.entity_platform"),
        "homeassistant.components": types.ModuleType("homeassistant.components"),
        "homeassistant.components.sensor": types.ModuleType("homeassistant.components.sensor"),
    }

    # Minimal stubs the sensor module actually uses
    ha_mods["homeassistant.const"].CONF_USERNAME = "username"
    ha_mods["homeassistant.const"].CONF_PASSWORD = "password"

    class _ConfigEntry: pass
    ha_mods["homeassistant.config_entries"].ConfigEntry = _ConfigEntry
    ha_mods["homeassistant.config_entries"].ConfigFlow = object
    ha_mods["homeassistant.core"].HomeAssistant = object

    class _CoordEntityMeta(type):
        def __getitem__(cls, item): return cls

    class _CoordEntity(metaclass=_CoordEntityMeta):
        def __init__(self, coordinator):
            self.coordinator = coordinator
        def async_on_remove(self, cb): pass

    class _SensorEntity: pass
    class _DeviceInfo(dict): pass
    class _SensorDeviceClass:
        MONETARY = "monetary"
    class _SensorStateClass:
        TOTAL = "total"
    class _DataUpdateCoordinatorMeta(type):
        def __getitem__(cls, item): return cls

    class _DataUpdateCoordinator(metaclass=_DataUpdateCoordinatorMeta):
        def __init__(self, *a, **kw): pass
        def async_add_listener(self, cb): return lambda: None
    class _UpdateFailed(Exception): pass
    class _ConfigEntryAuthFailed(Exception): pass
    class _ConfigEntryNotReady(Exception): pass

    ha_mods["homeassistant.helpers.update_coordinator"].CoordinatorEntity = _CoordEntity
    ha_mods["homeassistant.helpers.update_coordinator"].DataUpdateCoordinator = _DataUpdateCoordinator
    ha_mods["homeassistant.helpers.update_coordinator"].UpdateFailed = _UpdateFailed
    ha_mods["homeassistant.helpers.entity"].DeviceInfo = _DeviceInfo
    ha_mods["homeassistant.helpers.entity_platform"].AddEntitiesCallback = type(None)
    ha_mods["homeassistant.components.sensor"].SensorEntity = _SensorEntity
    ha_mods["homeassistant.components.sensor"].SensorDeviceClass = _SensorDeviceClass
    ha_mods["homeassistant.components.sensor"].SensorStateClass = _SensorStateClass
    ha_mods["homeassistant.exceptions"].ConfigEntryAuthFailed = _ConfigEntryAuthFailed
    ha_mods["homeassistant.exceptions"].ConfigEntryNotReady = _ConfigEntryNotReady

    for name, mod in ha_mods.items():
        sys.modules[name] = mod

_stub_ha()

# ---------------------------------------------------------------------------
# Now import integration modules
# ---------------------------------------------------------------------------
sys.path.insert(0, ".")
from custom_components.easypass_th.models import EasyPassCard
from custom_components.easypass_th.scraper import EasyPassScraper
from custom_components.easypass_th.sensor import _SENSOR_CLASSES

# ---------------------------------------------------------------------------
# Two fake cards (simulate account with 2 registered cards)
# ---------------------------------------------------------------------------
FAKE_CARDS = [
    EasyPassCard(
        serial_number="SN-001-FAKE",
        license_plate="กก 1234 กรุงเทพมหานคร",
        balance=543.50,
        owner_name="สมชาย ใจดี",
        mflow_message="ลงทะเบียนแล้ว",
        last_transaction_date="2026-05-10",
        last_topup_amount=500.0,
    ),
    EasyPassCard(
        serial_number="SN-002-FAKE",
        license_plate="ขข 5678 เชียงใหม่",
        balance=120.00,
        owner_name="สมหญิง รักดี",
        mflow_message="ยังไม่ลงทะเบียน",
        last_transaction_date="2026-05-09",
        last_topup_amount=200.0,
    ),
]


# ---------------------------------------------------------------------------
# Minimal fake coordinator that mimics coordinator.data
# ---------------------------------------------------------------------------
class FakeCoordinator:
    def __init__(self, cards):
        self.data = cards

    def async_add_listener(self, cb):
        return lambda: None


# ---------------------------------------------------------------------------
# Simulate async_setup_entry entity creation
# ---------------------------------------------------------------------------
def simulate_setup(coordinator, entry_id="entry_abc123"):
    """Mirror the logic in sensor.async_setup_entry."""

    class FakeEntry:
        entry_id = "entry_abc123"
        data = {"username": "test@example.com", "password": "secret"}

        def async_on_unload(self, cb): pass

    entry = FakeEntry()
    known_card_ids: set[str] = set()
    created: list = []

    def _add_new_cards():
        for idx, card in enumerate(coordinator.data or []):
            card_id = card.serial_number or f"{entry.entry_id}_{idx}"
            if card_id not in known_card_ids:
                known_card_ids.add(card_id)
                for cls in _SENSOR_CLASSES:
                    created.append(cls(coordinator, entry, card_id))

    _add_new_cards()
    return created, known_card_ids


# ---------------------------------------------------------------------------
# Test 1: initial setup creates 7 sensors × 2 cards = 14 entities
# ---------------------------------------------------------------------------
def test_initial_setup():
    coord = FakeCoordinator(FAKE_CARDS)
    entities, known = simulate_setup(coord)

    assert len(entities) == 14, f"Expected 14 entities, got {len(entities)}"
    assert len(known) == 2, f"Expected 2 known card IDs, got {len(known)}"

    unique_ids = [e._attr_unique_id for e in entities]
    assert len(unique_ids) == len(set(unique_ids)), "Duplicate unique_ids found!"

    print(f"  [PASS] {len(entities)} entities created for {len(known)} cards")
    for uid in sorted(unique_ids):
        print(f"         {uid}")


# ---------------------------------------------------------------------------
# Test 2: polling adds 3rd card automatically without duplicating existing ones
# ---------------------------------------------------------------------------
def test_dynamic_card_discovery():
    coord = FakeCoordinator(FAKE_CARDS[:1])  # start with 1 card

    class FakeEntry:
        entry_id = "entry_abc123"
        data = {"username": "test@example.com", "password": "secret"}
        def async_on_unload(self, cb): pass

    entry = FakeEntry()
    known_card_ids: set[str] = set()
    all_entities: list = []

    def _add_new_cards():
        for idx, card in enumerate(coord.data or []):
            card_id = card.serial_number or f"{entry.entry_id}_{idx}"
            if card_id not in known_card_ids:
                known_card_ids.add(card_id)
                for cls in _SENSOR_CLASSES:
                    all_entities.append(cls(coord, entry, card_id))

    # Initial setup — 1 card
    _add_new_cards()
    assert len(all_entities) == 7, f"Expected 7 after initial setup, got {len(all_entities)}"
    print(f"  [PASS] Initial: {len(all_entities)} entities (1 card)")

    # Simulate coordinator poll — 2nd card appeared
    coord.data = FAKE_CARDS  # now returns 2 cards
    _add_new_cards()

    assert len(all_entities) == 14, f"Expected 14 after 2nd card discovered, got {len(all_entities)}"
    assert len(known_card_ids) == 2
    print(f"  [PASS] After poll: {len(all_entities)} entities (2 cards, no duplicates)")

    # Simulate another poll — no new cards
    _add_new_cards()
    assert len(all_entities) == 14, "Entities duplicated on re-poll!"
    print(f"  [PASS] Re-poll: still {len(all_entities)} entities (no duplicates)")


# ---------------------------------------------------------------------------
# Test 3: sensor values resolve to the correct card
# ---------------------------------------------------------------------------
def test_sensor_values():
    coord = FakeCoordinator(FAKE_CARDS)
    entities, _ = simulate_setup(coord)

    balance_sensors = [e for e in entities if e._sensor_key == "balance"]
    assert len(balance_sensors) == 2

    values = {e._card_id: e.native_value for e in balance_sensors}
    assert values["SN-001-FAKE"] == 543.50
    assert values["SN-002-FAKE"] == 120.00
    print(f"  [PASS] Balance card 1: {values['SN-001-FAKE']} THB")
    print(f"  [PASS] Balance card 2: {values['SN-002-FAKE']} THB")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("\n=== Multi-card sensor tests ===\n")

    print("Test 1: Initial setup creates 7 sensors × 2 cards")
    test_initial_setup()

    print("\nTest 2: New card discovered automatically on next poll")
    test_dynamic_card_discovery()

    print("\nTest 3: Each sensor resolves values from the correct card")
    test_sensor_values()

    print("\nAll tests passed.")
