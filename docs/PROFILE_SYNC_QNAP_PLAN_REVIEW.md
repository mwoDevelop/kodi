# Niezależny review planu QNAP Profile Sync

Data: 2026-07-27

Zakres: `PROFILE_SYNC_PLAN.md`, kontrakt
`deploy/qnap-profile-sync/compose.yaml`, aktualny serwer Profile Sync i jego
pipeline obrazu.

Review wykonano niezależnie od autora planu. Celem było znalezienie
sprzeczności między Etapem 0, nietrwałym smoke 6A i produkcją 6B oraz luk,
które mogłyby dać pozornie udany test bez bezpiecznej ścieżki wdrożenia.

## Werdykt

Architektura hybrydowa pozostaje sensowna: GitHub zarządza kodem i wydaniami,
QNAP przechowuje wersjonowane profile, a klienci Kodi pobierają przypisania.
Plan przed review nie dawał jednak wystarczającej izolacji smoke i nie
definiował kilku bram koniecznych przed produkcją. Aktualnego Compose nie
należy uruchamiać jako 6A ani 6B bez zmian wymienionych niżej.

## Uwagi przyjęte

1. **Izolacja smoke — P0.** Bazowy Compose ma stałą nazwę kontenera i
   `restart: unless-stopped`. Powstanie `compose.smoke.yaml`, osobny project
   name, port, katalog danych i rejestr kluczy; restart smoke będzie `no`.
2. **Transport 6A — P0.** Port serwera jest związany z loopback QNAP, a reverse
   proxy powstaje dopiero w 6B. Test urządzeń użyje tunelu SSH QNAP -> host i
   osobnego `adb reverse` host -> każde urządzenie. Kodi połączy się wyłącznie
   z lokalnym `http://127.0.0.1:<port>`.
3. **Autoryzacja administracyjna — P0.** Operacje publish, promote, rollback,
   revocation i zarządzanie rolami nie mogą być wystawione produkcyjnie bez
   uwierzytelnienia, roli i proof-of-possession. Podpis musi obejmować cały
   dokument operacji, w tym kanał, generację, revision i idempotency key.
4. **Migracje i rollback danych — P0.** Cofnięcie samego obrazu nie jest
   rollbackiem. 6B wymaga wersjonowanego schematu, migracji forward,
   preflightu na kopii, spójnego backupu SQLite i blobów oraz macierzy
   kompatybilności obrazu ze schematem.
5. **Jeden control plane — P1.** Źródłem prawdy będzie Compose CLI uruchamiany
   przez SSH przeciw daemonowi Container Station. GUI służy wyłącznie do
   obserwacji; tej samej aplikacji nie importuje się ponownie w GUI.
6. **UID/GID i bind mounty — P1.** Przed startem trzeba zweryfikować
   dedykowany UID/GID, właścicieli i ACL, regularny plik key registry oraz
   zapis/odczyt jako użytkownik kontenera. Bind mount nie może po cichu
   utworzyć katalogu w miejscu oczekiwanego pliku.
7. **Publikacja GHCR — P1.** Sam build wieloarchitekturowy z `push: false` nie
   spełnia bramy 6A. Pipeline musi opublikować manifest, zapisać digest i
   potwierdzić wariant `linux/arm/v7`.
8. **Backup — P1.** Katalog na tej samej macierzy jest tylko cache rollbacku.
   Backup produkcyjny musi być zaszyfrowany, znajdować się poza QNAP i
   obejmować spójny zestaw DB + bloby.
9. **TLS/LAN — P1.** 6B otrzymuje runbook nazwy DNS, certyfikatu, odnowienia,
   reguł LAN/VPN i testów zaufania na obu Androidach. Prywatny klucz TLS
   pozostaje w QNAP reverse proxy.
10. **Walidacja Compose — P1.** CI ma renderować konfigurację bazową i smoke,
    sprawdzać digest, loopback, read-only, capabilities, bind mounty oraz
    uruchamiać runtime smoke na katalogach tymczasowych.
11. **Kontrakt i wersje — P2.** Kanoniczna baza to `/data/state.sqlite`.
    Dokument rozróżnia istniejące endpointy od planowanych, a metadane
    serwisu/API/schematu/builda mają pochodzić z jednego źródła wersji.
12. **Liveness i readiness — P2.** `/health` pozostaje prostym liveness;
    `/ready` ma sprawdzać DB, wersję schematu, rejestr kluczy i możliwość
    obsługi żądań.

## Uwagi odłożone

- Automatyczne podpisywanie obrazu i attestations są zalecane, ale nie są
  blockerem 6A. Niezmienny digest, zweryfikowany manifest oraz pochodzenie z
  kontrolowanego workflow są obowiązkowe.
- Prywatny GHCR jest dopuszczalny, ale preferowany jest publiczny obraz bez
  sekretów. Jeśli obraz pozostanie prywatny, credential ma trafić do hostowego
  credential store Container Station, nigdy do Compose ani `.env`.

## Rezultat

Uwagi przyjęte zostały przeniesione do `PROFILE_SYNC_PLAN.md` jako jawne bramy
wejścia/wyjścia 6A i 6B. Review nie zatwierdza bieżącego wdrożenia; zatwierdza
zaktualizowaną kolejność prac i kryteria, które muszą zostać spełnione przed
uruchomieniem smoke lub produkcji.
