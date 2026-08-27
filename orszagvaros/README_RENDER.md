# Országváros – Render telepítés

## 1. GitHub
- Hozz létre egy új GitHub repositoryt, pl. `orszagvaros`.
- Töltsd fel a projekt teljes tartalmát ebbe a mappába.

## 2. Render
- Nyisd meg a Render dashboardot.
- New → Web Service.
- Csatlakoztasd a GitHub repositoryt.
- Build Command: `pip install -r requirements.txt`
- Start Command: `python app.py`
- Free plan választható.

Az alkalmazás a Render által megadott `PORT` környezeti változón figyel.

## 3. Játék
A deploy után a Render ad egy `https://...onrender.com` címet. Ezt lehet megosztani a játékosokkal; nem kell ugyanazon Wi-Fi-n lenniük.
