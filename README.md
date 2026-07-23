# Home Assistant Up Bank Integration 
Forked from [here](https://github.com/jamespdat-spec/homeassistant-up-bank).

This integration uses the Up bank [API](https://developer.up.com.au) ([github](https://github.com/up-banking/api)), to pull account balances and latest transaction information. Leverages Up API's webhooks for close to live updates.

## Upgrading from a pre-0.5.0 version (domain rename)
As of 0.5.0 the integration's domain changed from `up-bank` to `up_bank`. This was to bring the integration in line with home assistant [style guide](https://developers.home-assistant.io/docs/development_guidelines/) and typing requirements. HA uses [mypy for typing](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/strict-typing/) and it's package name validation rejects hyphens. I suspect the hyphen in the domain name was also breaking the front end's ability to get the up bank icon. 

This is a one-time breaking change. HA ties a config entry to its domain, so unfortunately updating in place was not possible.
Your sensor entity IDs (e.g. `sensor.up_total_balance`) are set explicitly by the integration and don't contain the domain string, so history, dashboards, and automations referencing them keep working across this migration untouched - only the API key needs re-entering.

To upgrade:
1. Update to 0.5.0+ via HACS as normal.
2. Go to Settings -> Devices & Services, find the (now broken) old Up Bank entry, and delete it.
3. Add the integration again fresh (Settings -> Devices & Services -> Add Integration -> Up Bank) and re-enter your API key.

Likely overkill to go this hard on the strictly typing but I thought it was worth ripping the bandaid off now to make any eventual submissions to home assistant core easier. I'm also interested in building some tests as a learning experience and maybe trying to work up the integration quality scale in the future.

## Webhook updates are now supported!

Options for an getting an External URL to enable webhook functionality:

- **Home Assistant Cloud (Nabu Casa)** - the official, supported option if you're already a subscriber. Gives you a
  stable HTTPS URL with no networking setup at all. Easiest and supports the Home Assistant devs!
- **Tailscale Funnel** - what I used for testing (see `docker-compose.yml`/`config/configuration.yaml`).
- Cloudflare Tunnel 
- ngrok

Whichever you pick, set it as HA's `external_url` (Settings -> System -> Network, or `external_url:` under `homeassistant:`
in `configuration.yaml`) so the integration knows what URL to register with Up.

# Installation
The easiest way is to install via HACS, see https://github.com/hacs/integration to install HACS in your Home Assistant install if you haven't already.

1. Go to HACS on your home assistant site (usually a tab on the left)
2. Select Integrations
3. Top right click on the 3 dots, then Custom repositories
3. Enter this repository https://github.com/DanielRobertson93/homeassistant-up-bank then underneath, select category *integration* and add
4. Explore and Download
5. Search for HA UP in the list at the top and install this integration - it will have the little Up logo
6. Restart Home Assistant
7. Go to regular e.g. Integrations (e.g. Settings -> Devices & Services -> (ADD INTEGRATION) _(bottom right)_
8. Search for and add Up Bank for Home Assistant - click the three small dots on the right of the line and choose DOWNLOAD
9. Get your UP API key from: https://api.up.com.au/getting_started
10. Enter the API key on the config screen

# Development
There is an included a docker-compose, so make sure you have docker, and docker-compose installed. Then you can start it with `docker compose up -d`. Every time you change the files you will need to restart the server inside the HA GUI for the changes to kick in.

## Tooling (ruff, mypy)
This repo uses `ruff` (lint + format) and `mypy` (type checking), configured in `pyproject.toml`.

```
ruff check --fix .   # lint
ruff format .        # format
mypy                 # type check (reads pyproject.toml)
```
