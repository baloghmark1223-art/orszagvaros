# Országváros v2

## Telepítés

A projekt mappájában:

```bash
py -m pip install -r requirements.txt
```

vagy:

```bash
python -m pip install -r requirements.txt
```

## Indítás

```bash
py app.py
```

vagy:

```bash
python app.py
```

Helyben:

http://localhost:5000

Másik gépről ugyanazon a Wi-Fi/hálózaton:

http://SZERVER-GÉP-IP-CÍME:5000

Példa:

http://192.168.0.10:5000

## Játékmenet

1. Az első játékos automatikusan Host.
2. A Host létrehoz egy szobát.
3. A többiek a szobakóddal belépnek.
4. A Host elindítja a játékot.
5. Mindenki megkapja ugyanazt a véletlenszerű betűt.
6. Nincs időkorlát; a kör akkor zárul, amikor mindenki megnyomja a Kész gombot.
7. A Kész gomb leadja a válaszokat.
8. Minden válasz látható a kör végén.
9. A Host válaszonként elfogad/elutasít.
10. Elfogadott válasz: +1 pont.
11. Összesen 10 kör.
12. A végén eredménytábla.

## Ha a másik gép nem éri el

Windows tűzfalban engedélyezd a Python számára a privát hálózati hozzáférést, vagy hozz létre bejövő szabályt a TCP 5000 portra.

A szerver konzoljában a helyi IP-cím használatához például:

```text
ipconfig
```

majd az IPv4 Address értékét használd.

## Fontos

A játék állapota jelenleg memóriában van. A szerver újraindításával a szobák elvesznek.


v8: Az ÚJ JÁTÉK gomb kizárólag a végeredmény állapotban jelenik meg.


## Egyedi kategóriák

A Host a lobbyban tetszőleges számú saját kategóriát adhat hozzá. A 7 alap kategória mindig megmarad: Ország, Város, Fiú, Lány, Növény, Állat, Tárgy. Az egyedi kategóriák a válaszadásnál, az értékelésnél és a pontozásnál automatikusan megjelennek. A kategóriák csak az adott játékteremhez tartoznak.
