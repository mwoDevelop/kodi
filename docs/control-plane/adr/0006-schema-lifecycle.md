# ADR-0006: expand/contract i N/N-1

Status: zaakceptowany

Każdy format ma osobny lifecycle. Reader N obsługuje wymagane N/N-1, nieznany
schemat jest fail-closed, a usunięcie readera/migratora następuje dopiero po
retencji i dowodzie braku aktywnych danych. Migracje bazy są expand/contract i
posiadają mixed-version E2E oraz tryb read-only/downgrade.

Pierwszy przyrost dodał schemat bazy 1 dla snapshotów i audytu. Drugi przyrost
dodaje schemat bazy 2 dla `convergence_bundle_v1` i head desired state. Migracja
jest expand-only, a restore nadal przyjmuje backup schematu 1 i migruje jego
odizolowaną kopię. Schemat przyszły jest odrzucany fail-closed.
