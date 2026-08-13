# ADR-0001: osobne repozytorium Control Plane

Status: zaakceptowany

`mwoDevelop/kodi-control-plane` jest osobnym repo i obrazem. Profile Sync pozostaje
właścicielem consumer API i bazy enrollmentów. Integracja odbywa się przez
wersjonowane read-only API mTLS, nigdy przez współdzielone tabele SQLite.

Uzasadnienie: admin/control plane ma inną powierzchnię uprawnień, cykl release i
threat model. Kontrakt i macierz N/N-1 są testowane w obu repozytoriach.
