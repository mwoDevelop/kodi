# ADR-0002: offline release intent i ograniczony assignment key

Status: zaakceptowany projekt; implementacja zablokowana do fazy bundle

Offline promoter podpisuje dokładny `release_intent_id`, digest immutable bundle,
kanał, maksymalny zbiór urządzeń oraz czas. QNAP otrzyma osobny rotowalny klucz
online, zdolny jedynie do wystawienia krótkotrwałego assignmentu dla tego samego
bundle, enrollmentu, generacji i dozwolonej fali.

Klucz online nie ma ról `revision`, `promotion`, `admin` ani `publish`. Serwer ma
wymuszać delegację kryptograficznie. Do czasu wdrożenia i negatywnych testów tej
reguły Control Plane pozostaje read-only.
