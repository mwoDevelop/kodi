# QNAP Kodi Control Plane

Ta część dokumentacji opisuje wdrażaną architekturę, w której QNAP przejmuje
rutynową obserwowalność, a następnie sterowanie konwergencją konfiguracji Kodi.
Sieciowy interfejs pozostaje celowo **tylko do odczytu**: nie przyjmuje sekretów,
nie tworzy assignmentów i nie zmienia urządzeń. Drugi przyrost dodaje lokalnemu
CLI QNAP niemutowalny `convergence_bundle_v1`, exact-artifact evidence i atomową
publikację head przez CAS. Nie jest to jeszcze assignment dla urządzenia.

## Nawigacja

- [Architektura i przepływ danych](architecture.md)
- [Model zagrożeń](threat-model.md)
- [Instalacja pierwszego przyrostu na QNAP](qnap-install.md)
- [ADR](adr/README.md)
- [Review planu panelu administracyjnego z 2026-08-21](../QNAP_ADMIN_MODULE_PLAN_REVIEW_2026-08-21.md)

Plan całości znajduje się w
[`QNAP_CONTROL_PLANE_DEVICE_CONVERGENCE_PLAN.md`](../../QNAP_CONTROL_PLANE_DEVICE_CONVERGENCE_PLAN.md).

## Aktualna granica release 3A1

Control Plane udostępnia przez mTLS wyłącznie:

- `GET /v1/fleet`;
- `GET /v1/rollouts`;
- `GET /v1/services`;
- `GET /v1/audit/checkpoint`.
- `GET /v1/desired-state/<channel>`.
- `GET /v1/dashboard`, `/v1/schedules`, `/v1/alerts`;
- `GET /api/v1/{dashboard,schedules,services,alerts}` oraz statyczny panel `/`.

Panel jest nadal chroniony istniejącym mTLS i nie ma logowania przeglądarkowego
WebAuthn ani żadnych akcji mutujących. Każdy status zawiera osobne pochodzenie i
świeżość; proces cykliczny rozdziela obecność schedulera, wynik runu i stale dane.
Kanoniczne katalogi są w `manifests/control-plane-{schedules,status-sources}.json`.

Profile Sync udostępnia mu osobny kontrakt mTLS
`/v1/integration/{fleet,rollouts}` w prywatnej sieci Compose. Consumer API nadal
jest jedynym interfejsem publikowanym do LAN, a loopback admin API nie jest
publikowane ani do LAN, ani do Control Plane.

Mutacje bundle (`prepare`, `ready`, `publish`) są dostępne wyłącznie z lokalnego
CLI w kontenerze/hoście QNAP i zapisują audit w tej samej transakcji co zmiana
stanu. Przykłady i kontrakt znajdują się w repo
[`kodi-control-plane`](https://github.com/mwoDevelop/kodi-control-plane/blob/main/docs/convergence-bundle-v1.md).
