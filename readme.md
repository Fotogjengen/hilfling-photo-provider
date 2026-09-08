# Vår bildeserver hostet hos ITK

Dette prosjektet er vår bildeserver hostet på samfundet og håndterer alle bildeoperasjoner (hente, opplasting, slette osv).

Aktiver venv:

`source venv/bin/activate`

Lag venv:
`virtualenv venv`

## Frie bilder og profilbilder

Frie bilder trenger ikke album, motiv eller arkivnummer. Klienten sender filen til
backenden, som eier databaseposten, kontrollerer brukeren og kaller photoprovideren.
Filene lagres her; metadata og profilbildereferansen lagres i backendens database.

Backend- og frontendendringene ligger i søsterprosjektene `hilfling-photo-backend`
og `hilfling-frontend`. Start backenden på nytt for å kjøre Flyway-migreringen
`V2__internal_images.sql`. Sett `IMAGE_PROVIDER_URL` i backendmiljøet til adressen
backenden kan nå denne tjenesten på (standard `http://localhost:8888`).
Photoprovideren bruker eksisterende `JWKS_URL` til å verifisere backendens RSA-signatur.
Ingen ny delt hemmelighet er nødvendig.

### Endepunkter på backenden

Alle endepunktene under krever en innlogget FG-bruker (`fgToken` eller
`X-hilfling-token`). Eier hentes fra tokenet, aldri fra klientens skjema.

| Metode | Sti | Innhold/resultat |
| --- | --- | --- |
| POST | `/api/images/upload` | Multipart: `media`, valgfri `securityLevel` (`FG` som standard, også `ALLE` og `HUSFOLK`) |
| GET | `/api/images` | Egne bilder og opplastings-/slettestatus |
| GET | `/api/images/{id}` | Bildets metadata og `prod`, `web`, `thumb`-lenker |
| DELETE | `/api/images/{id}` | Slett eget bilde; `USER_MANAGE` kan også slette andres. Gjentakelser gir 204. |
| GET | `/api/photo_gang_bangers/me` | Innlogget medlems profil |
| POST | `/api/photo_gang_bangers/me/profile-picture` | Multipart: `media`. Lagrer nytt profilbilde og erstatter det gamle. |
| DELETE | `/api/photo_gang_bangers/me/profile-picture` | Fjerner eget profilbilde og returnerer oppdatert profil. |

Profilbilder er `ALLE`, fordi de også vises offentlig på «Om oss». Vanlige frie
bilder er `FG` som standard. Frontendens `InternalImageApi` kan brukes til nye
bruksområder; profilsiden har ferdig opplasting og fjerning av profilbilde.

### Filer og tilgang

Bildene lagres under `IMAGE_STORAGE_PATH` (lokalt `media`):

```text
<alle|fg|husfolk>/internal/<uuid>/prod.<jpg|png|webp>
<alle|fg|husfolk>/internal/<uuid>/web.png
<alle|fg|husfolk>/internal/<uuid>/thumb.png
```

Fullversjonen beholder oppløsningen. Webversjonen er maks 1000 × 1000, og
miniatyren er kvadratisk 300 × 300. Filformat bestemmes fra bildeinnholdet;
klientens filnavn brukes ikke som lagringssti. Bildene normaliseres, orienteres
etter EXIF og lagres uten EXIF/GPS. PNG-transparens beholdes. JPEG og WebP kodes
på nytt, så fullversjonen er ikke en identisk kopi av den opplastede filen.

Bildelenkene fungerer med eksisterende `/media`-ruting og tilgangskontroll.
Legg til `?download=1` på en lenke for nedlasting som vedlegg.
La også `/media` gå gjennom photoprovideren i produksjon slik at tilgangskontrollen brukes.
De nye klientendepunktene går til backenden; Vites eksisterende `/api`-proxy dekker dem.

Bare backenden kan kalle `POST` og `DELETE /internal/images/{uuid}` på
photoprovideren. Hvert kall krever en signert tillatelse med riktig bilde-ID,
operasjon, tilgangsnivå og audience, gyldig i to minutter. Vanlige brukertokener
gir ikke skrivetilgang her.

### Grenser og feilhåndtering

JPEG, PNG og WebP støttes, maks 10 MiB og 25 millioner piksler som standard.
`INTERNAL_IMAGE_MAX_BYTES` og `INTERNAL_IMAGE_MAX_PIXELS` konfigurerer provideren.
Ved endring av filgrensen må også backendens `image-provider.max-upload-bytes`
og Spring multipart-grenser, samt frontendens filgrense, oppdateres.

Backendposter går fra `PENDING` til `READY` først når alle bildeversjonene er
skrevet. Profilbytter låser medlemsraden og kobler inn det nye bildet før det gamle
slettes. Ved opplastingsfeil forsøkes opprydding; ved slettingsfeil beholdes posten
som `DELETING`. Disse postene finnes i `GET /api/images`, og sletting kan forsøkes
igjen med samme ID. Profilbytte/fjerning kan lykkes selv om opprydding av den gamle
filen må forsøkes igjen. Det finnes ingen automatisk bakgrunnsjobb for opprydding.
Et prosesskrasj kan etterlate en `PENDING`-post som også kan slettes via API-et.

Providerens tomme `.deleted`-markør blir liggende etter sletting for å hindre at
en forsinket opplasting publiserer et bilde etter en timeout. Selve bildefilene
slettes. Eksterne eller gamle arkivbilder som er brukt som profilbilde kobles bare
fra profilen; de slettes ikke fra arkivet.

Kjør provider-testene med:

```sh
python manage.py test hilfling_image_proxy.shared.test_internal_images --settings=hilfling_image_proxy.settings.dev
```

Kjør prosjektet i dev med `python3 manage.py runserver 127.0.0.1:8888 --settings=hilfling_image_proxy.settings.dev`
