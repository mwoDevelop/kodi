# ADR-0006: expand/contract i N/N-1

Status: zaakceptowany

Każdy format ma osobny lifecycle. Reader N obsługuje wymagane N/N-1, nieznany
schemat jest fail-closed, a usunięcie readera/migratora następuje dopiero po
retencji i dowodzie braku aktywnych danych. Migracje bazy są expand/contract i
posiadają mixed-version E2E oraz tryb read-only/downgrade.

Pierwszy przyrost dodaje schematy read-only snapshot i audit. Schematy mutujące są
rejestrowane przed implementacją ich writera.
