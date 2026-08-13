# ADR-0007: QNAP właścicielem logicznego inventory po cutoverze

Status: zaakceptowany kierunek; cutover jeszcze niewykonany

Tożsamość stanowią `logical_device_id`, `enrollment_id` i monotoniczna generacja.
Adres ADB/SSH jest opcjonalnym atrybutem diagnostycznym z TTL, nigdy kluczem
głównym. Po migracji QNAP jest właścicielem logicznego inventory, desired state i
capabilities, a localhost pozostaje bootstrapem/break-glass.

Pierwszy release tylko odczytuje enrollmenty Profile Sync. `.env` pozostaje
źródłem prywatnego inventory aż do jawnego shadow importu i testu recovery.
