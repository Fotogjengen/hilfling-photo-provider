# Vår bildeserver hostet hos ITK

Dette prosjektet er vår bildeserver hostet på samfundet og håndterer alle bildeoperasjoner (hente, opplasting, slette osv).

## Installering

### uv

Vi bruker `uv` for avhengighetshåndtering. Dette kommer av at ITK kjører en rar versjon av python.

Mac: <br />
`brew install uv`

Windows (kjør denne greia her ig??) <br />
`powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

### Sett opp prosjektet

Kjør `uv sync`, den fikser alt for deg automatisk :)

### Uten uv

Lag venv manuelt med Python 3.11 (`python3.11 -m venv .venv`) og installer med `pip install -r requirements.txt` (fullt låst liste generert fra `uv.lock`).

## Kjøring

Kjør prosjektet i dev med `uv run python manage.py runserver 127.0.0.1:8888 --settings=hilfling_image_proxy.settings.dev`

Eller aktiver miljøet manuelt med `source .venv/bin/activate` og kjør `python3 manage.py runserver 127.0.0.1:8888 --settings=hilfling_image_proxy.settings.dev`
