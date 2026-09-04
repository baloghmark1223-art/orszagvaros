# Országváros v4 – Neon

## Jellemzők
- Kék-fekete neon látványvilág
- 1–10 kör választható a Hostnál
- Egy meccsen belül nincs betűismétlés
- Nincs időkorlát: a kör addig tart, amíg minden játékos meg nem nyomja a KÉSZ gombot
- Host értékeli a válaszokat
- Elfogadott válasz = 1 pont
- Körönkénti értékelés és végeredmény
- ÚJ JÁTÉK csak a végeredménynél
- Socket.IO polling, Windows alatt websocket-kiegészítő nélkül

## Indítás
```text
py -m pip install -r requirements.txt
py app.py
```
Nyisd meg: http://localhost:5000

Hálózaton a szerver gép IP-címét használd, például: http://192.168.0.14:5000
