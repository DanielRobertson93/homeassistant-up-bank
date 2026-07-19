Home Assistant Up Bank Integration forked from [here](https://github.com/jamespdat-spec/homeassistant-up-bank)

Uses the Up bank API [docs](https://developer.up.com.au), [github](https://github.com/up-banking/api), to pull account balances and latest transaction information.

Webhook updates are now supported!

## Getting an external URL for webhooks
A few ways to get that external URL:

- **Home Assistant Cloud (Nabu Casa)** - the official, supported option if you're already a subscriber. Gives you a
  stable HTTPS URL with no networking setup at all. Easiest choice if you have it.
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
There is an included a docker-compose file with mapping, so make sure you have docker, and docker-compose installed. Then you can start it with `docker compose up -d`. Every time you change the files you will need to restart the server inside the HA GUI for the changes to kick in.

## Tooling (ruff, mypy)
This repo uses `ruff` (lint + format) and `mypy` (type checking), configured in `pyproject.toml`.

```
ruff check --fix .   # lint
ruff format .        # format
mypy                 # type check (reads pyproject.toml, resolves through the symlink)
```
