from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, emit, join_room
import random
import string
import time

app = Flask(__name__)
app.config["SECRET_KEY"] = "orszagvaros-v2-secret"
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

BASE_CATEGORIES = [
    ("country", "Ország"),
    ("city", "Város"),
    ("boy", "Fiú"),
    ("girl", "Lány"),
    ("plant", "Növény"),
    ("animal", "Állat"),
    ("object", "Tárgy"),
]

# A magyar ábécé használható betűi, amelyekkel érdemes játszani.
LETTERS = list("ABCDEFGHIJKLMNOPRSTUVZ")


def new_code():
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
        if code not in games:
            return code


def all_categories(game):
    return BASE_CATEGORIES + game.get("custom_categories", [])


def new_game():
    return {
        "host": None,
        "players": {},          # sid -> player
        "state": "lobby",       # lobby / playing / review / finished
        "round": 0,
        "total_rounds": 5,
        "letter": None,
        "used_letters": [],
        "deadline": None,
        "ready": set(),
        "answers": {},          # sid -> answers
        "accepted": {},         # sid -> category -> bool
        "round_points": {},     # sid -> points in current round
        "custom_categories": [], # [(key, label)]
    }


games = {}


def game_state(game):
    return {
        "state": game["state"],
        "round": game["round"],
        "total_rounds": game["total_rounds"],
        "letter": game["letter"],
        "used_letters": game["used_letters"],
        "deadline": game["deadline"],
        "categories": all_categories(game),
        "players": [
            {
                "sid": sid,
                "name": player["name"],
                "score": player["score"],
                "is_host": sid == game["host"],
                "ready": sid in game["ready"],
            }
            for sid, player in game["players"].items()
        ],
    }


def broadcast(code):
    if code in games:
        socketio.emit("state", game_state(games[code]), room=code)


def build_review(game):
    return [
        {
            "sid": sid,
            "name": player["name"],
            "answers": game["answers"].get(sid, {}),
            "accepted": game["accepted"].get(sid, {}),
            "score": player["score"],
            "round_points": game["round_points"].get(sid, 0),
        }
        for sid, player in game["players"].items()
    ]


def send_current_view(sid, code):
    """A már folyamatban lévő játék állapotát elküldi egy újracsatlakozó kliensnek."""
    game = games[code]

    emit("state", game_state(game), to=sid)

    if game["state"] == "playing":
        remaining = 0
        if game["deadline"]:
            remaining = max(0, int(game["deadline"] - time.time()))

        emit("round_started", {
            "round": game["round"],
            "total_rounds": game["total_rounds"],
            "letter": game["letter"],
            "duration": remaining,
            "categories": all_categories(game),
        }, to=sid)

        if sid in game["ready"]:
            emit("answers_submitted", {}, to=sid)

    elif game["state"] == "review":
        emit("round_review", {
            "round": game["round"],
            "letter": game["letter"],
            "categories": all_categories(game),
            "players": build_review(game),
            "is_host": sid == game["host"],
        }, to=sid)

    elif game["state"] == "finished":
        results = sorted(
            [
                {"sid": psid, "name": p["name"], "score": p["score"]}
                for psid, p in game["players"].items()
            ],
            key=lambda x: x["score"],
            reverse=True,
        )
        emit("game_finished", {"players": results, "total_rounds": game["total_rounds"]}, to=sid)


def choose_new_letter(game):
    available = [letter for letter in LETTERS if letter not in game["used_letters"]]
    if not available:
        return None
    letter = random.choice(available)
    game["used_letters"].append(letter)
    return letter


def start_round(code):
    game = games[code]

    letter = choose_new_letter(game)
    if letter is None:
        finish_game(code)
        return

    game["round"] += 1
    game["letter"] = letter
    game["state"] = "playing"
    game["deadline"] = None
    game["ready"] = set()
    game["answers"] = {}
    game["accepted"] = {}
    game["round_points"] = {}

    socketio.emit("round_started", {
        "round": game["round"],
        "total_rounds": game["total_rounds"],
        "letter": game["letter"],
        "used_letters": game["used_letters"],
        "duration": 0,
        "categories": all_categories(game),
    }, room=code)

    broadcast(code)
    socketio.start_background_task(round_timer, code, game["round"])


def round_timer(code, round_number):
    while True:
        socketio.sleep(0.2)

        game = games.get(code)
        if not game:
            return

        if game["state"] != "playing" or game["round"] != round_number:
            return

        everyone_ready = (
            len(game["players"]) > 0
            and game["ready"] == set(game["players"].keys())
        )

        if everyone_ready:
            finish_round(code)
            return


def finish_round(code):
    game = games.get(code)
    if not game or game["state"] != "playing":
        return

    game["state"] = "review"
    game["deadline"] = None

    # Minden üresen maradt játékoshoz is létrehozunk válaszszótárat.
    for sid in game["players"]:
        game["answers"].setdefault(sid, {})
        game["accepted"].setdefault(sid, {})
        game["round_points"].setdefault(sid, 0)

    socketio.emit("round_review", {
        "round": game["round"],
        "total_rounds": game["total_rounds"],
        "letter": game["letter"],
        "categories": all_categories(game),
        "players": build_review(game),
        "is_host": True if game["host"] else False,
    }, room=code)

    broadcast(code)


def finish_game(code):
    game = games.get(code)
    if not game:
        return

    game["state"] = "finished"
    game["deadline"] = None

    results = sorted(
        [
            {"sid": sid, "name": p["name"], "score": p["score"]}
            for sid, p in game["players"].items()
        ],
        key=lambda x: x["score"],
        reverse=True,
    )

    socketio.emit("game_finished", {"players": results, "total_rounds": game["total_rounds"]}, room=code)
    broadcast(code)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/create")
def create():
    code = new_code()
    games[code] = new_game()
    return redirect(url_for("lobby", code=code))


@app.route("/join")
def join():
    code = request.args.get("code", "").strip().upper()
    if code not in games:
        return render_template("error.html", message="Nincs ilyen szoba."), 404
    return redirect(url_for("lobby", code=code))


@app.route("/lobby/<code>")
def lobby(code):
    if code not in games:
        return render_template("error.html", message="Nincs ilyen szoba."), 404
    return render_template("lobby.html", code=code)


@app.route("/game/<code>")
def game_page(code):
    if code not in games:
        return render_template("error.html", message="Nincs ilyen szoba."), 404
    return render_template("game.html", code=code)


@socketio.on("join_game")
def on_join(data):
    code = str(data.get("code", "")).strip().upper()
    name = str(data.get("name", "")).strip()

    if code not in games:
        emit("error_message", {"message": "Nincs ilyen szoba."})
        return

    if not name:
        emit("error_message", {"message": "Adj meg egy játékosnevet."})
        return

    if len(name) > 20:
        emit("error_message", {"message": "A név legfeljebb 20 karakter lehet."})
        return

    game = games[code]

    # Már bent lévő játékos újracsatlakozása / lobby -> game navigáció.
    existing_sid = None
    for psid, player in game["players"].items():
        if player["name"].lower() == name.lower():
            existing_sid = psid
            break

    if existing_sid is not None:
        player = game["players"].pop(existing_sid)
        game["players"][request.sid] = player

        if game["host"] == existing_sid:
            game["host"] = request.sid

        if existing_sid in game["ready"]:
            game["ready"].remove(existing_sid)
            if game["state"] == "playing":
                game["ready"].add(request.sid)

        if existing_sid in game["answers"]:
            game["answers"][request.sid] = game["answers"].pop(existing_sid)

        if existing_sid in game["accepted"]:
            game["accepted"][request.sid] = game["accepted"].pop(existing_sid)

        if existing_sid in game["round_points"]:
            game["round_points"][request.sid] = game["round_points"].pop(existing_sid)

        join_room(code)
        session["code"] = code
        session["name"] = player["name"]

        emit("joined", {
            "code": code,
            "name": player["name"],
            "is_host": request.sid == game["host"],
            "state": game["state"],
        })

        send_current_view(request.sid, code)
        broadcast(code)
        return

    # Új játékos csak lobbyban csatlakozhat.
    if game["state"] != "lobby":
        emit("error_message", {
            "message": "A játék már elkezdődött. Csak a már korábban csatlakozott játékos léphet vissza."
        })
        return

    if any(p["name"].lower() == name.lower() for p in game["players"].values()):
        emit("error_message", {"message": "Ez a név már foglalt."})
        return

    game["players"][request.sid] = {
        "name": name,
        "score": 0,
    }

    if game["host"] is None:
        game["host"] = request.sid

    join_room(code)
    session["code"] = code
    session["name"] = name

    emit("joined", {
        "code": code,
        "name": name,
        "is_host": request.sid == game["host"],
        "state": game["state"],
    })

    broadcast(code)


@socketio.on("set_rounds")
def on_set_rounds(data):
    code = str(data.get("code", "")).strip().upper()
    game = games.get(code)
    if not game:
        emit("error_message", {"message": "Nincs ilyen szoba."})
        return
    if request.sid != game["host"]:
        emit("error_message", {"message": "Csak a Host állíthatja a körök számát."})
        return
    if game["state"] != "lobby":
        emit("error_message", {"message": "A körök száma csak a játék indítása előtt módosítható."})
        return
    try:
        rounds = int(data.get("rounds", 5))
    except (TypeError, ValueError):
        rounds = 5
    game["total_rounds"] = max(1, min(10, rounds))
    broadcast(code)


@socketio.on("set_custom_categories")
def on_set_custom_categories(data):
    code = str(data.get("code", "")).strip().upper()
    game = games.get(code)

    if not game:
        emit("error_message", {"message": "Nincs ilyen szoba."})
        return

    if request.sid != game["host"]:
        emit("error_message", {"message": "Csak a Host állíthatja az egyedi kategóriákat."})
        return

    if game["state"] != "lobby":
        emit("error_message", {"message": "Az egyedi kategóriák csak a játék indítása előtt módosíthatók."})
        return

    raw_categories = data.get("categories", [])
    if not isinstance(raw_categories, list):
        raw_categories = []

    custom = []
    used_keys = {key for key, _label in BASE_CATEGORIES}
    used_labels = {label.casefold() for _key, label in BASE_CATEGORIES}

    for raw in raw_categories:
        label = str(raw).strip()
        if not label:
            continue
        label = label[:50]
        if label.casefold() in used_labels:
            continue

        # Stabil, kliensbarát kulcs az egyedi kategóriához.
        base = "custom_" + "".join(ch.lower() if ch.isalnum() else "_" for ch in label)
        base = base.strip("_") or "custom"
        key = base
        n = 2
        while key in used_keys:
            key = f"{base}_{n}"
            n += 1

        custom.append((key, label))
        used_keys.add(key)
        used_labels.add(label.casefold())

    game["custom_categories"] = custom
    broadcast(code)
    socketio.emit("categories_updated", {"categories": all_categories(game)}, room=code)


@socketio.on("start_game")
def on_start_game(data):
    code = str(data.get("code", "")).strip().upper()
    game = games.get(code)

    if not game:
        emit("error_message", {
            "message": "Nincs ilyen szoba."
        })
        return

    if request.sid != game["host"]:
        emit("error_message", {
            "message": "Csak a Host indíthatja a játékot."
        })
        return

    if game["state"] != "lobby":
        emit("error_message", {
            "message": "A játék már elindult."
        })
        return

    if not game["players"]:
        emit("error_message", {
            "message": "Nincs játékos."
        })
        return

    # -----------------------------
    # KÖRÖK SZÁMÁNAK BEÁLLÍTÁSA
    # -----------------------------

    try:
        total_rounds = int(game.get("total_rounds", 5))
    except (TypeError, ValueError):
        total_rounds = 5

    total_rounds = max(1, min(10, total_rounds))

    game["total_rounds"] = total_rounds
    game["round"] = 0

    # Játék indítása
    start_round(code)

@socketio.on("submit_answers")
def on_submit_answers(data):
    code = str(data.get("code", "")).strip().upper()
    game = games.get(code)

    if not game or game["state"] != "playing":
        return

    sid = request.sid
    if sid not in game["players"]:
        return

    if sid in game["ready"]:
        return

    answers = data.get("answers", {}) or {}
    clean = {}

    for key, _label in all_categories(game):
        clean[key] = str(answers.get(key, "")).strip()[:100]

    game["answers"][sid] = clean
    game["ready"].add(sid)

    emit("answers_submitted", {})
    broadcast(code)

    if game["ready"] == set(game["players"].keys()):
        finish_round(code)


@socketio.on("accept_answer")
def on_accept_answer(data):
    code = str(data.get("code", "")).strip().upper()
    player_sid = data.get("player_sid")
    category = data.get("category")
    accepted = bool(data.get("accepted"))

    game = games.get(code)

    if not game or game["state"] != "review":
        return

    if request.sid != game["host"]:
        emit("error_message", {"message": "Csak a Host értékelhet."})
        return

    if player_sid not in game["players"]:
        return

    if category not in {key for key, _ in all_categories(game)}:
        return

    game["accepted"].setdefault(player_sid, {})

    old = game["accepted"][player_sid].get(category)
    game["accepted"][player_sid][category] = accepted

    # Újraszámoljuk az aktuális kör pontját.
    round_score = sum(
        1 for value in game["accepted"][player_sid].values()
        if value is True
    )
    game["round_points"][player_sid] = round_score

    # Az összpont = korábbi pontok + aktuális kör pontjai.
    # Ehhez a player "score" mezőjéből kivonjuk a korábbi aktuális kör pontot.
    previous_round_score = game["round_points"].get(
        player_sid + "__previous", 0
    )
    # A fenti technika helyett biztonságosan kiszámoljuk a kör előtt elmentett
    # alapot: ezt az első értékelésnél rögzítjük.
    if "__base" not in game["round_points"]:
        game["round_points"]["__base"] = {}

    if player_sid not in game["round_points"]["__base"]:
        game["round_points"]["__base"][player_sid] = game["players"][player_sid]["score"]

    base = game["round_points"]["__base"][player_sid]
    game["players"][player_sid]["score"] = base + round_score

    socketio.emit("evaluation_update", {
        "player_sid": player_sid,
        "category": category,
        "accepted": accepted,
        "score": game["players"][player_sid]["score"],
        "round_points": round_score,
    }, room=code)

    # A teljes review táblát is frissítjük, hogy újracsatlakozásnál se vesszen el.
    socketio.emit("review_refresh", {
        "players": build_review(game),
    }, room=code)


@socketio.on("next_round")
def on_next_round(data):
    code = str(data.get("code", "")).strip().upper()
    game = games.get(code)

    if not game:
        return

    if request.sid != game["host"]:
        emit("error_message", {"message": "Csak a Host indíthatja a következő kört."})
        return

    if game["state"] != "review":
        return

    if game["round"] >= game["total_rounds"]:
        finish_game(code)
        return

    # Az aktuális kör pontjai már beépültek a score-ba.
    start_round(code)


@socketio.on("disconnect")
def on_disconnect():
    # Nem töröljük azonnal a játékost. Ez fontos a rövid hálózati megszakadás
    # és az oldalváltás miatt. A játékos a neve alapján vissza tud csatlakozni.
    # Lobbyban viszont, ha mindenki kilépett, a szoba törölhető.
    for code, game in list(games.items()):
        if request.sid in game["players"]:
            if game["state"] == "lobby":
                was_host = request.sid == game["host"]
                del game["players"][request.sid]

                if was_host:
                    if game["players"]:
                        game["host"] = next(iter(game["players"]))
                        socketio.emit(
                            "host_changed",
                            {"message": "A Host kilépett, új Host lett kijelölve."},
                            room=code,
                        )
                    else:
                        del games[code]
                        continue

                broadcast(code)

            # Játék közben a játékos állapotát megtartjuk, hogy vissza tudjon lépni.
            return


if __name__ == "__main__":
    print("======================================")
    print("      ORSZÁGVÁROS - MULTIPLAYER")
    print("======================================")
    print("Helyi gépen: http://localhost:5000")
    print("Hálózaton:   http://SAJAT-IP-CIM:5000")
    print("======================================")
    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=True,
        allow_unsafe_werkzeug=True,
    )
