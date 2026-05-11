# Thailand Easy Pass — Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/thititongumpun/ha-easypass-th)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Monitor your **Thailand Easy Pass** (การทางพิเศษแห่งประเทศไทย) card balance and account info directly in Home Assistant.

![screenshot](screenshot.png)

---

## Features

- 💰 Real-time card balance (THB)
- 🚗 License plate associated with the card
- 🪪 Card serial number (SmartCard S/N)
- 👤 Account owner name
- 🛣️ M-Flow registration status
- Polls automatically every 30 minutes
- Session auto-renewal (re-login on expiry)
- Re-authentication UI when credentials change

---

## Installation

### Via HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=thititongumpun&repository=ha-easypass-th&category=integration)

Or manually:

1. Open HACS → **⋮** → **Custom repositories**
2. Add URL: `https://github.com/thititongumpun/ha-easypass-th`
3. Category: **Integration**
4. Click **Add** → search **Thailand Easy Pass** → **Download**
5. Restart Home Assistant

### Manual

1. Download this repository
2. Copy `custom_components/easypass_th/` into your HA config `custom_components/` folder
3. Restart Home Assistant

---

## Setup

1. Settings → Integrations → **+ Add Integration**
2. Search **Thailand Easy Pass**
3. Enter your **email** and **password** from [member-thaieasypass.exat.co.th](https://member-thaieasypass.exat.co.th)
4. Click **Submit**

---

## Entities

| Entity | Description | Unit |
|--------|-------------|------|
| `sensor.easy_pass_*_easy_pass_balance` | Card balance | THB |
| `sensor.easy_pass_*_easy_pass_license_plate` | Vehicle license plate | — |
| `sensor.easy_pass_*_easy_pass_card_serial` | SmartCard serial (S/N) | — |
| `sensor.easy_pass_*_easy_pass_account_owner` | Account holder name | — |
| `sensor.easy_pass_*_easy_pass_m_flow_status` | M-Flow registration status | — |

> `*` is your email address slug (e.g. `example@gmail_com`)

Find your exact entity IDs: **Developer Tools → States** → filter `easy_pass`

---

## Dashboard Examples

### Balance card with low-balance alert colour

```yaml
type: custom:mushroom-template-card
primary: >
  {{ states('sensor.easy_pass_YOUR_EMAIL_easy_pass_balance') | float(0) | round(2) }} ฿
secondary: >
  อัปเดต {{ relative_time(states.sensor.easy_pass_YOUR_EMAIL_easy_pass_balance.last_updated) }} ที่แล้ว
icon: mdi:cash
icon_color: >
  {% set bal = states('sensor.easy_pass_YOUR_EMAIL_easy_pass_balance') | float(0) %}
  {% if bal < 100 %}red{% elif bal < 300 %}orange{% else %}green{% endif %}
badge_icon: >
  {% if states('sensor.easy_pass_YOUR_EMAIL_easy_pass_balance') | float(0) < 100 %}
    mdi:alert
  {% endif %}
badge_color: red
```

### Balance gauge

```yaml
type: gauge
entity: sensor.easy_pass_YOUR_EMAIL_easy_pass_balance
name: ยอดเงินคงเหลือ
unit: ฿
min: 0
max: 1000
needle: true
severity:
  green: 300
  yellow: 100
  red: 0
```

### Low balance automation

```yaml
alias: Easy Pass ยอดเงินต่ำ
trigger:
  - platform: numeric_state
    entity_id: sensor.easy_pass_YOUR_EMAIL_easy_pass_balance
    below: 100
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "⚠️ Easy Pass ยอดเงินต่ำ"
      message: >
        ยอดเงินคงเหลือ {{ states('sensor.easy_pass_YOUR_EMAIL_easy_pass_balance') }} ฿
        กรุณาเติมเงินที่ https://member-thaieasypass.exat.co.th
```

> See `dashboard_examples.yaml` in this repo for more complete examples.

---

## How it works

1. **Login** — POSTs credentials to `/eservice/login` (Laravel AJAX endpoint), receives session cookies
2. **Data fetch** — GETs `/eservice/easypasscardlist/get-all` JSON API every 30 minutes
3. **HA sensors** — `DataUpdateCoordinator` distributes data to all sensor entities automatically
4. **Session renewal** — On session expiry the scraper re-logs in automatically (up to 3 retries)
5. **Re-auth UI** — If credentials are rejected, HA shows a notification to re-enter your password

---

## Requirements

- Home Assistant 2024.1+
- [Mushroom Cards](https://github.com/piitaya/lovelace-mushroom) (for dashboard examples, optional)
- Python packages (auto-installed by HA): `requests`, `beautifulsoup4`, `lxml`

---

## License

MIT — see [LICENSE](LICENSE)
