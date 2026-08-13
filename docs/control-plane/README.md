# QNAP Kodi Control Plane

Ta część dokumentacji opisuje wdrażaną architekturę, w której QNAP przejmuje
rutynową obserwowalność, a następnie sterowanie konwergencją konfiguracji Kodi.
Pierwszy release jest celowo **tylko do odczytu**: nie przyjmuje sekretów, nie
tworzy assignmentów i nie zmienia urządzeń.

## Nawigacja

- [Architektura i przepływ danych](architecture.md)
- [Model zagrożeń](threat-model.md)
- [Instalacja pierwszego przyrostu na QNAP](qnap-install.md)
- [ADR](adr/README.md)

Plan całości znajduje się w
[`QNAP_CONTROL_PLANE_DEVICE_CONVERGENCE_PLAN.md`](../../QNAP_CONTROL_PLANE_DEVICE_CONVERGENCE_PLAN.md).

## Aktualna granica release

Control Plane udostępnia przez mTLS wyłącznie:

- `GET /v1/fleet`;
- `GET /v1/rollouts`;
- `GET /v1/services`;
- `GET /v1/audit/checkpoint`.

Profile Sync udostępnia mu osobny kontrakt mTLS
`/v1/integration/{fleet,rollouts}` w prywatnej sieci Compose. Consumer API nadal
jest jedynym interfejsem publikowanym do LAN, a loopback admin API nie jest
publikowane ani do LAN, ani do Control Plane.
