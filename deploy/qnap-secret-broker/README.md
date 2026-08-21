# QNAP Secret Broker

Wewnętrzna usługa mTLS wydająca koperty `secret-envelope-v1` dla Profile Sync.
Nie publikuje portu do LAN, nie montuje Docker socketu i przechowuje bazę
zaszyfrowaną kluczem z pliku `0400`.

Produkcyjne importy oraz zmiany lifecycle wykonuje wyłącznie lokalny CLI QNAP.
Control Plane i GUI otrzymują tylko zredagowane metadane.
