# Niezależny audyt planu Favourites multi-writer

Data: 2026-09-01

Werdykt pierwotny: `CHANGES_REQUIRED`

Werdykt po korektach: `READY_FOR_IMPLEMENTATION`

## Zakres i wynik

Niezależny reviewer porównał plan z aktualnym dodatkiem Profile Sync, backendem QNAP,
adapterem `kodi_favourites_v1` oraz istniejącym playback-state LWW. Audyt objął wyścigi,
offline, idempotencję, bezpieczeństwo, migrację, backup, GC, rollback, monitoring i E2E.

Przyjęto wszystkie pięć uwag P0:

1. `dynamic_authority_fence` blokuje cofnięcie dynamicznego head przez rewizję statyczną.
2. Jedna maszyna stanów serializuje detect/pull/upload/apply i zachowuje inflight.
3. Autoryzacja rozdziela capability, serwerową flagę/scope, rolę, bearer, podpis
   urządzenia i dedykowany authority key.
4. Wspólna allowlista ogranicza możliwość lateralnego wykonania przez złośliwy skrót.
5. Dodatek dostaje jawny exporter; grafiki i kanonikalizacja nie są delegowane do
   hostowego skryptu.

Przyjęto także destructive debounce, prepare TTL/idempotency, bezpieczny GC/backup,
dedykowany ack, jawne stany monitoringu, klasyfikację enrollmentów offline, topologię
release, fault injection, jitter i limity.

Po dodatkowej decyzji użytkownika migrację uproszczono do ręcznego `seed` i jawnego
`cutover-enrollment`. Nie powstaje automatyczny dual-read ani migrator danych.

Istniejący mechanizm playback-state jest współdzielonym fundamentem transportowym, ale
nie wspólną tabelą domenową. Powstaje mały `ScopedStateEngine`; playback i favourites
zachowują osobne walidatory, storage oraz conflict policy.

## Świadomie odrzucone kierunki

Nie dodano per-item merge, CRDT, SMB/WebDAV, zegarów klientów, leader election,
WebSocket push, ręcznej akceptacji każdego konfliktu, automatycznej migracji ani
synchronizacji całej skórki. LWW pozostaje kolejnością commitów QNAP; mismatch base
revision jest audytowany, ale nie blokuje późniejszego zapisu.
