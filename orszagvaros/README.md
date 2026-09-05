# Országváros – v8 játékmódok + automatikus egyezés

Ez a verzió az előző v8 + plusz kategóriák + ranglista javítás továbbfejlesztése.

## Játékmódok
- Korlátlan idő: a kör akkor ér véget, amikor minden játékos KÉSZ-re nyom.
- 2 perces: 120 másodperc után a szerver automatikusan lezárja a kört. Ha mindenki előbb kész, akkor előbb zárul.
- Első KÉSZ: amint bármelyik játékos KÉSZ-re nyom, az egész kör azonnal véget ér.

A módot kizárólag a Host állíthatja a lobbyban.

## Automatikus egyezés
Kategóriánként történik az egyezésvizsgálat. A kis-/nagybetű és a felesleges szóköz nem számít. Ha legalább két játékos ugyanazt a nem üres választ adja, az automatikusan helytelenként jelenik meg. A Host ettől függetlenül a HELYES gombbal jóváhagyhatja, vagy a ROSSZ gombbal elutasíthatja.

A 7 alap kategória és a plusz kategóriák továbbra is működnek.
