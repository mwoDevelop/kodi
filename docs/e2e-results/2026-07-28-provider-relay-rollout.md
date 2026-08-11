# Wdrożenie przekaźnika Umbrella 6.7.81.16 i MwoScrapers 0.1.5

Data: 28.07.2026

## Wynik

Kandydat testing przeszedł dalej BlueStacks, Sony TV i Bedroom TV. Umbrella nie oferuje
się już jako zewnętrzny dostawca, natomiast MwoScrapers pozostaje ważnym wyborem. Obydwa
urządzenia Android TV utrzymywały połączenie NordVPN podczas testów końcowych.

Bedroom TV ustalił przyczynę sieci przed wdrożeniem:

- bezpośrednie wywołania Torrentio przez wyjście VPN zwróciły HTTP 403;
- to samo środowisko wykonawcze Kodi za pośrednictwem przekaźnika metadanych QNAP
  zwróciło 5 kandydatów na filmy i 49 kandydatów na odcinki;
- BlueStacks direct, przekaźnik Sony i przekaźnik sypialni zwróciły te same wartości
  5/49.

Nie była wymagana zmiana dzielonego tunelu w NordVPN. Ostateczny stan łączności Android
ujawnił UID Kodi w zakresach UID przypisanych do podłączonej sieci NordVPN zarówno w
Sony, jak i Bedroom TV.

## Opublikowane komponenty

| Składnik | Wersja | Zatwierdzenie / niezmienna tożsamość |
| --- | --- | --- |
| Umbrella | 6.7.81.16 | `9ccb063e65463b4116d5c9ad2f09be189b051f29` |
| MwoScrapers | 0,1,5 | `6c4b7956734f902c94b51f593a989ef0b3a29510` |
| Przekaźnik MwoScrapers | 0.1.0 | `ghcr.io/mwodevelop/mwoscrapers-relay@sha256:837e070ef5106fcd294b56f1cdd74a5d0376839d173e4388a6b5361916803198` |

Publiczne podsumowania testing ZIP odpowiadają blokadzie repozytorium:

- Umbrella: `e97d3cb06792663b58b30097072e36f5de04122045a2f47d44ded95d9fd22855`;
- MwoScrapers: `ec9425baa334fbda2b9b106ec0aa558e5a8d37e03d5315e865fbcfb15762c58a`.

## Przekaźnik QNAP

Manifest wielu architektur przekazał CI dla `linux/amd64` i `linux/arm/v7`. Jednorazowy
dym ARMv7 QNAP przeszedł stan zdrowia, zwrócił niepuste metadane Torrentio i nie
utworzył żadnych woluminów. Posprzątanie pozostawiło zero pojemników na dym, sieci i
woluminów.

Produkcyjny projekt bezstanowy jest powiązany z prywatnym adresem LAN QNAP:

- jeden zdrowy kontener i jedna sieć Compose;
- zero woluminów i zero tajemnic;
- stała lista dozwolonych dostawców/ścieżek;
- QNAP Stan RAID `UU`;
- reakcja dotycząca zdrowia publicznego `ok`.

Autoryzacja Real-Debrid, przesłanie magnesu, rozdzielczość i odtwarzanie nie przechodzą
przez ten przekaźnik.

## Wyniki urządzenia

| Urządzenie | Kodi | Umbrella | MwoScrapers | Sintel | Breaking Bad S01E01 |
| --- | --- | --- | --- | --- | --- |
| BlueStacks | 21,3 | 6.7.81.16 | 0,1,5 | zagrał, 20,254 s | rozegrany, 12,144 s |
| Sony TV | 21,3 | 6.7.81.16 | 0,1,5 | zagrał, 46,481 s | zagrał, 27.000 s |
| Bedroom TV | 21,3 | 6.7.81.16 | 0,1,5 | rozegrany, 18,124 s | zagrał, 14,253 s |

Każde urządzenie wybierało ten sam oczyszczony odcisk palca źródłowego w każdym
przypadku:

- Sintel: `5a6b52180d6a015e`;
- Breaking Bad S01E01: `6f39c1e78d9c75c4`.

Każde odtwarzanie tworzyło strumień wejściowy i demuxer i trwało co najmniej 12 sekund.
Raporty nie zawierają żadnych danych uwierzytelniających, magnesów ani ustalonych
adresów URL:

- [BlueStacks](2026-07-28-bluestacks-provider-relay-rollout.json)
- [Sony TV](2026-07-28-sony-provider-relay-rollout.json)
- [Bedroom TV](2026-07-28-bedroom-provider-relay-rollout.json)

## Promocja stable

Dokładny publiczny kandydat testing był promowany bajt po bajcie po wdrożeniu
urządzenia:

- bramka promocyjna `30383783693` pobrana i sprawdzona testing indeks
  `9bca766697af33afe56e1e1c83a3bdb48b4cfe6111a13542dfa9566ba378a01c`;
- promocja PR #55 zmieniła tylko `manifests/locks/stable.json` i przekazała repozytorium
  E2E w przebiegu `30383969637`;
- Wdrożenie stable `30384195482` przeszło repozytorium E2E, zbudowano tylko bajty z
  adresem blokady i wdrożono GitHub Pages;
- publiczne skróty ZIP stable dla wszystkich pięciu komponentów odpowiadają promowanej
  blokadzie, a publiczne `addons.xml` odpowiadają zadeklarowanej sumie kontrolnej;
- `repository.mwodevelop` pozostaje wersją `1.0.0`.

Porządkowanie własności po promocji również przeszło:

- Kodi odświeżył repozytorium stable do indeksowania sumy kontrolnej
  `01dac2b62f0138a99832607e42c442c0365597c4d9b9190ff75ebc14ff02f168`;
- migracja pochodzenia wymagała dokładnych sum kontrolnych indeksu stable i testing oraz
  pasujących wersji kandydujących przed zmianą bazy danych dodatku Kodi;
- każdy zainstalowany dodatek mwoDevelop na BlueStacks, Sony TV i Bedroom TV jest
  włączony i stanowi własność `repository.mwodevelop`;
- `repository.mwodevelop.testing` został usunięty z Sony TV i Bedroom TV po migracji i
  jest nieobecny na wszystkich trzech urządzeniach;
- odtwarzanie Sintel po oczyszczeniu odbyło się ponownie na wszystkich trzech
  urządzeniach przez ponad 12 sekund ze źródłowym odciskiem palca `5a6b52180d6a015e`;
- nie pozostają żadne tymczasowe pliki migracji ADB ani pliki migracji po stronie
  urządzenia.

Oczyszczone raporty po czyszczeniu:

- [BlueStacks](2026-07-28-bluestacks-stable-origin-cleanup.json)
- [Sony TV](2026-07-28-sony-stable-origin-cleanup.json)
- [Bedroom TV](2026-07-28-bedroom-stable-origin-cleanup.json)

## Znaleziono i naprawiono błąd podczas wdrażania

MwoScrapers 0.1.4 używał pustych domyślnych ustawień XML dla dwóch ustawień punktów
końcowych. Kodi zaakceptował wartości, ale zarejestrował błędy wartości domyślnych
`CSettingString`. Wersja 0.1.5 używa publicznych punktów końcowych dostawców jako
prawidłowych ustawień domyślnych.

Po zainstalowaniu dokładnego publicznego ZIP 0.1.5 na wszystkich urządzeniach:

- ta sama sonda dotycząca dostawców filmów/odcinków zwróciła 5/49 dla wszystkich trzech;
- w każdym nowym oknie dziennika pojawiały się zerowe błędy schematu ustawień punktu
  końcowego;
- wszystkie sześć końcowych przypadków odtwarzania zostało pomyślnie zrealizowanych.

## Powtarzalne bramki

- Widelec Umbrella: 41 testów;
- MwoScrapers: kryza, weryfikacja dodatkowa i 36 testów;
- repozytorium nadrzędne: dwie kompilacje o identycznych bajtach i 141 testów;
- publikacja workflow: `30382850144`;
- Cykl życia dymu i produkcji QNAP: `tools/qnap_provider_relay.py`;
- Kodi sonda dostawcy/filtrująca: `tests/e2e/kodi_provider_rollout_probe.py`;
- odtwarzanie: `tests/e2e/sony_kodi_matrix.py`.
