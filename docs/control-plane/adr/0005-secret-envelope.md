# ADR-0005: koperty sekretów per enrollment

Status: proponowany; brak zgody na import sekretów

Preferencją jest X25519/HPKE po potwierdzeniu interoperacyjności ARMv7, Android i
Flatpak. Klucz Ed25519 raportów nie jest ponownie używany jako klucz szyfrowania.
Wariant przejściowy to losowy klucz AEAD provisionowany podczas parowania w
zweryfikowanym TLS.

Import plaintextu jest zablokowany do czasu spike'u, testu izolacji urządzeń,
rotacji, dwóch recovery copies i pełnego restore drill.
