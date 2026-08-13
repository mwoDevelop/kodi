# Architektura QNAP Control Plane

## Pierwszy przyrost: read-only

```text
GitHub Actions (publiczny read)
             |
             v
      kodi-control-plane -- mTLS API operatora --> klient w LAN
             |
             | mTLS, prywatna sieć mwodevelop-control
             v
     kodi-profile-sync-server integration API
             |
             v
   zredagowane enrollmenty, heartbeat i raporty
```

Control Plane utrwala tylko zredagowane snapshoty operacyjne. Nie montuje bazy
Profile Sync, nie montuje Docker socketu i nie dostaje klucza publishera,
promotora ani administratora. Nie może też wywołać żadnej mutacji HTTP.

Tożsamość wywołującego API jest zapisywana jako fingerprint SHA-256 certyfikatu
klienta. W audycie nie jest zapisywany certyfikat, subject ani credential.

## Źródła prawdy

| Dane | Właściciel pierwszego przyrostu | Uwagi |
|---|---|---|
| kod i artefakty dodatków | GitHub/stable Kodi repo | Control Plane tylko obserwuje |
| enrollment, rewizja, assignment, raport | Profile Sync | odczyt przez wersjonowany kontrakt |
| snapshot obserwacyjny i audit | Control Plane | bez sekretów i pełnych podpisanych dokumentów |
| prywatny inventory i sekrety | nadal localhost | migracja dopiero po bramie secret-envelope |

## Degraded mode

Gdy GitHub albo Profile Sync jest niedostępny, ostatni poprawny snapshot pozostaje
dostępny z `status=error`, czasem ostatniej próby i bezpiecznym `error_code`.
Control Plane nie usuwa poprzedniego payloadu i nie wpływa na działanie Kodi.
