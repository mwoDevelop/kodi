# ADR-0004: dowód artefaktu i uczciwy poziom weryfikacji

Status: zaakceptowany projekt; spike Kodi wymagany

Release manifest wiąże repo, workflow identity, commit, SHA-256 ZIP oraz
deterministyczny manifest plików. Agent ma policzyć digest oczekiwanego drzewa po
instalacji. Wynik dokładny może mieć status `VERIFIED` wyłącznie przy zgodnym
drzewie i dozwolonych plikach generowanych.

Jeżeli Kodi API nie pozwoli udowodnić pobranego ZIP ani drzewa, raport używa
`ORIGIN_VERSION_ONLY`, a dokumentacja jawnie przyjmuje zaufanie do GitHub Pages i
natywnego updatera. Nie wolno podnosić tego statusu na podstawie samego ID/wersji.
