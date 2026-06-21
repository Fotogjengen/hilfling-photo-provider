# Vår bildeserver hostet hos ITK

Dette prosjektet er vår bildeserver hostet på samfundet og håndterer alle bildeoperasjoner (hente, opplasting, slette osv).

Aktiver venv:

`source venv/bin/activate`

Lag venv:
`virtualenv venv`

Kjør prosjektet i dev med `python3 manage.py runserver 127.0.0.1:8888 --settings=hilfling_image_proxy.settings.dev`
