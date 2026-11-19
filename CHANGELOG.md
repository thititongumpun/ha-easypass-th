# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.7] - 2026-11-19

### Fixed
- Monthly spend now covers only the current calendar month (1st through today) instead of the whole fetched window, and no longer depends on the history range.

### Changed
- History range `30` is now the current month and `90` is the current + previous 2 months (`7` is still a rolling 7 days).
- History range selector shows Thai/English labels (7 วัน / เดือนนี้ / 3 เดือน); stored values are unchanged.
- Monthly spend sensor exposes `last_reset` and a `period_start` attribute.

## [1.0.6] - 2026-09-24

### Fixed
- Last top-up, last toll location and monthly spend stayed unknown on multi-card accounts. The usage API was called with the shared customer ID (`CustomerID`, `A…`), which returns no history; it now uses each card's `AccountNumber` (falling back to `paymentMethod.accountId`, then `CustomerID`).
- Account ID is now looked up across both card lists when one list lacks it.

### Added
- Debug logging of each card's raw field names and of the full usage API response when it returns no transactions.

## [1.0.5] - 2026-09-13

### Added
- **Integration icon and logo** — `custom_components/easypass_th/brand/`
  ships `icon.png` / `logo.png` (plus `@2x`). Home Assistant 2026.3+ serves
  these in preference to the brands CDN, so Easy Pass now shows a real icon
  in Settings → Devices & Services. Older versions ignore the folder.
- Dedicated error for Social/Google-only accounts, so the config flow says
  the account has no website password instead of a generic auth failure.

### Fixed
- History range select is attached to the card device rather than the
  account device.

---

## [1.0.2] - 2026-05-20

### Added
- **Configurable transaction history range** — choose 7, 30, or 90 days via
  Settings → Integrations → Easy Pass → Configure. Previously locked to the
  current calendar month; now defaults to the last 30 days.
- **Manual refresh service** (`easypass_th.refresh`) — trigger an on-demand
  poll from Developer Tools → Services or an automation without waiting for
  the next 30-minute interval.
- `strings.json` and `services.yaml` for proper HA UI labels on the new
  options form and service.

### Changed
- Transaction history date range now counts back from today (rolling window)
  instead of starting on the 1st of the current calendar month.

### Upgrade notes
No migration required. Existing config entries automatically use the 30-day
default. To change the range, go to Settings → Integrations → Easy Pass → **Configure**.

---

## [1.0.1] - 2026-05-15

### Changed
- Removed the hardcoded `MAX_CARDS = 30` ceiling. Pagination now terminates
  naturally when the API returns an empty page or no new unique cards, so
  accounts with more than 30 cards are fully supported.

### Fixed
- Card discovery: prefer the dropdown list when it contains more entries than
  the paged data, fixing cases where some cards were silently skipped.
- Pagination no longer stops early when a mid-pagination page request fails —
  only a failure on page 1 is treated as a hard error.

### Upgrade notes
No migration required. Drop-in replacement for 1.0.0.

---

## [1.0.0] - 2026-05-10

### Added
- Initial release.
- Multi-card support — each card on the account becomes its own HA device,
  discovered automatically on every poll.
- 10 sensors per card: Balance, Reward Points, License Plate, Card Serial,
  Account Owner, M-Flow Status, Monthly Spend, Last Toll Location,
  Last Transaction, Last Top-up.
- Full transaction history exposed as attributes on the Balance sensor.
- Session auto-renewal on expiry (up to 3 retries before re-auth UI).
- Config Flow with re-authentication support.
- Thai and English translations.
- Dashboard examples and low-balance automation in README.
