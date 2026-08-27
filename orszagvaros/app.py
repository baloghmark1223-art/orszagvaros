from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, emit, join_room
import random
import os
import string

app = Flask(__name__)
app.config["SECRET_KEY"] = "orszagvaros-v3-secret"

# Pollinget használunk alapból: Windows alatt így nem függünk a websocket
# extra környezetétől, és ugyanúgy valós idejű marad a játék.
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

CATEGORIES = [
    ("country", "Ország", "🌍"),
    ("city", "Város", "🏙️"),
    ("boy", "Fiú", "👦"),
    ("girl", "Lány", "👧"),
    ("plant", "Növény", "🌿"),
    ("animal", "Állat", "🐾"),
    ("object", "Tárgy", "◈"),
]

# Biztonságosan választható, egyszerű latin betűk.
LETTERS = list("ABCDEFGHIJKLMNOPRSTUVZ")


games = {}


def new_code():
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
        if code not in games:
            return code


def new_game():
    return {
        "host": None,
        "players": {},              # sid -> {name, score}
        "state": "lobby",          # lobby / playing / review / finished
        "round": 0,
        "total_rounds": 5,
        "letter": None,
        "used_letters": [],
        "deadline": None,
        "ready": set(),
        "answers": {},              # sid -> {category: answer}
        "accepted": {},             # sid -> {category: bool}
        "round_points": {},         # sid -> current round points
        "round_base_scores": {},    # sid -> score before current round review
    }


def public_state(game):
    return {
        "state": game["state"],
        "round": game["round"],
        "total_rounds": game["total_rounds"],
        "letter": game["letter"],
        "used_letters": list(game["used_letters"]),
        "deadline": None,
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
    game = games.get(code)
    if game:
        socketio.emit("state", public_state(game), room=code)


def review_players(game):
    result = []
    for sid, player in game["players"].items():
        result.append({
            "sid": sid,
            "name": player["name"],
            "answers": game["answers"].get(sid, {}),
            "accepted": game["accepted"].get(sid, {}),
            "score": player["score"],
            "round_points": game["round_points"].get(sid, 0),
            "is_host": sid == game["host"],
        })
    return result


def final_results(game):
    return sorted(
        [
            {"sid": sid, "name": player["name"], "score": player["score"]}
            for sid, player in game["players"].items()
        ],
        key=lambda item: (-item["score"], item["name"].lower()),
    )


def emit_review_to_room(code):
    game = games[code]
    players = review_players(game)
    for sid in game["players"]:
        emit("round_review", {
            "round": game["round"],
            "total_rounds": game["total_rounds"],
            "letter": game["letter"],
            "categories": CATEGORIES,
            "players": players,
            "is_host": sid == game["host"],
        }, to=sid)


def send_current_view(sid, code):
    game = games[code]
    emit("state", public_state(game), to=sid)

    if game["state"] == "playing":
        emit("round_started", {
            "round": game["round"],
            "total_rounds": game["total_rounds"],
            "letter": game["letter"],
            "used_letters": list(game["used_letters"]),
            "duration": 0,
            "categories": CATEGORIES,
        }, to=sid)
        if sid in game["ready"]:
            emit("answers_submitted", {}, to=sid)

    elif game["state"] == "review":
        emit("round_review", {
            "round": game["round"],
            "total_rounds": game["total_rounds"],
            "letter": game["letter"],
            "categories": CATEGORIES,
            "players": review_players(game),
            "is_host": sid == game["host"],
        }, to=sid)

    elif game["state"] == "finished":
        emit("game_finished", {
            "players": final_results(game),
            "total_rounds": game["total_rounds"],
        }, to=sid)


def choose_new_letter(game):
    available = [letter for letter in LETTERS if letter not in game["used_letters"]]
    if not available:
        return None
    letter = random.choice(available)
    game["used_letters"].append(letter)
    return letter


def start_round(code):
    game = games.get(code)
    if not game:
        return

    if game["round"] >= game["total_rounds"]:
        finish_game(code)
        return

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
    game["round_base_scores"] = {
        sid: player["score"] for sid, player in game["players"].items()
    }

    socketio.emit("round_started", {
        "round": game["round"],
        "total_rounds": game["total_rounds"],
        "letter": game["letter"],
        "used_letters": list(game["used_letters"]),
        "duration": 0,
        "categories": CATEGORIES,
    }, room=code)

    broadcast(code)
def finish_round(code):
    game = games.get(code)
    if not game or game["state"] != "playing":
        return

    game["state"] = "review"
    game["deadline"] = None

    for sid in game["players"]:
        game["answers"].setdefault(sid, {})
        game["accepted"].setdefault(sid, {})
        game["round_points"].setdefault(sid, 0)

    emit_review_to_room(code)
    broadcast(code)


def finish_game(code):
    game = games.get(code)
    if not game:
        return

    game["state"] = "finished"
    game["deadline"] = None
    socketio.emit("game_finished", {
        "players": final_results(game),
        "total_rounds": game["total_rounds"],
    }, room=code)
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

    # Reconnect ugyanazzal a névvel.
    existing_sid = next(
        (psid for psid, player in game["players"].items()
         if player["name"].lower() == name.lower()),
        None,
    )

    if existing_sid is not None and existing_sid != request.sid:
        player = game["players"].pop(existing_sid)
        game["players"][request.sid] = player

        if game["host"] == existing_sid:
            game["host"] = request.sid

        if existing_sid in game["ready"]:
            game["ready"].remove(existing_sid)
            game["ready"].add(request.sid)

        for store_name in ("answers", "accepted", "round_points", "round_base_scores"):
            store = game[store_name]
            if existing_sid in store:
                store[request.sid] = store.pop(existing_sid)

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

    if game["state"] != "lobby":
        # Ha ugyanaz a SID már bent van, csak küldjük vissza az aktuális nézetet.
        if request.sid in game["players"]:
            join_room(code)
            send_current_view(request.sid, code)
            return
        emit("error_message", {"message": "A játék már elkezdődött."})
        return

    if any(p["name"].lower() == name.lower() for p in game["players"].values()):
        emit("error_message", {"message": "Ez a név már foglalt."})
        return

    game["players"][request.sid] = {"name": name, "score": 0}
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
        emit("error_message", {"message": "A körök száma csak indulás előtt módosítható."})
        return

    try:
        rounds = int(data.get("rounds", 5))
    except (TypeError, ValueError):
        rounds = 5
    game["total_rounds"] = max(1, min(10, rounds))
    broadcast(code)


@socketio.on("start_game")
def on_start_game(data):
    code = str(data.get("code", "")).strip().upper()
    game = games.get(code)
    if not game:
        emit("error_message", {"message": "Nincs ilyen szoba."})
        return
    if request.sid != game["host"]:
        emit("error_message", {"message": "Csak a Host indíthatja a játékot."})
        return
    if game["state"] != "lobby":
        emit("error_message", {"message": "A játék már elindult."})
        return
    if not game["players"]:
        emit("error_message", {"message": "Nincs játékos."})
        return

    game["total_rounds"] = max(1, min(10, int(game.get("total_rounds", 5))))
    game["round"] = 0
    game["used_letters"] = []
    start_round(code)


@socketio.on("submit_answers")
def on_submit_answers(data):
    code = str(data.get("code", "")).strip().upper()
    game = games.get(code)
    sid = request.sid

    if not game or game["state"] != "playing" or sid not in game["players"]:
        return
    if sid in game["ready"]:
        return
    raw = data.get("answers", {}) or {}
    clean = {}
    for key, _label, _icon in CATEGORIES:
        clean[key] = str(raw.get(key, "")).strip()[:100]

    game["answers"][sid] = clean
    game["ready"].add(sid)
    emit("answers_submitted", {}, to=sid)
    broadcast(code)

    if game["ready"] == set(game["players"].keys()):
        finish_round(code)


@socketio.on("set_answer_validity")
def on_set_answer_validity(data):
    """A Host egy konkrét választ helyesnek vagy hibásnak jelöl."""
    code = str(data.get("code", "")).strip().upper()
    player_sid = str(data.get("player_sid", ""))
    category = str(data.get("category", ""))
    raw_accepted = data.get("accepted")
    if isinstance(raw_accepted, bool):
        accepted = raw_accepted
    elif isinstance(raw_accepted, (int, float)):
        accepted = raw_accepted == 1
    elif isinstance(raw_accepted, str):
        accepted = raw_accepted.strip().lower() in {"true", "1", "yes", "helyes", "accepted"}
    else:
        accepted = False

    game = games.get(code)
    if not game or game["state"] != "review":
        return
    if request.sid != game["host"]:
        emit("error_message", {"message": "Csak a Host értékelhet."})
        return
    if player_sid not in game["players"]:
        return
    valid_categories = {key for key, _label, _icon in CATEGORIES}
    if category not in valid_categories:
        return

    answer = str(game["answers"].get(player_sid, {}).get(category, "") or "").strip()
    if not answer:
        accepted = False

    accepted_for_player = game["accepted"].setdefault(player_sid, {})
    accepted_for_player[category] = accepted

    # A kör pontszáma mindig újraszámolódik az összes kategória alapján.
    round_score = sum(1 for value in accepted_for_player.values() if value is True)
    game["round_points"][player_sid] = round_score

    # A teljes pontszám = kör előtti pont + aktuális kör pontjai.
    base = game["round_base_scores"].get(player_sid, 0)
    game["players"][player_sid]["score"] = base + round_score

    payload = {
        "player_sid": player_sid,
        "category": category,
        "accepted": accepted,
        "score": game["players"][player_sid]["score"],
        "round_points": round_score,
    }

    socketio.emit("evaluation_update", payload, room=code)
    socketio.emit("review_refresh", {"players": review_players(game)}, room=code)
    broadcast(code)


# Visszafelé kompatibilis alias, ha egy régebbi kliens még ezt az eseményt küldi.
@socketio.on("accept_answer")
def on_accept_answer(data):
    return on_set_answer_validity(data)


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
    else:
        start_round(code)


@socketio.on("disconnect")
def on_disconnect():
    # Lobbyban a kilépő játékos eltűnik; futó játékban megőrizzük, hogy vissza tudjon lépni.
    for code, game in list(games.items()):
        if request.sid not in game["players"]:
            continue

        if game["state"] == "lobby":
            was_host = request.sid == game["host"]
            del game["players"][request.sid]
            if was_host:
                if game["players"]:
                    game["host"] = next(iter(game["players"]))
                    socketio.emit("host_changed", {
                        "message": "A Host kilépett, új Host lett kijelölve."
                    }, room=code)
                else:
                    del games[code]
                    continue
            broadcast(code)
        return


if __name__ == "__main__":
    print("======================================")
    print("       ORSZÁGVÁROS - MULTIPLAYER")
    print("======================================")
    print("Helyi gépen: http://localhost:5000")
    print("Hálózaton:   http://SAJAT-IP-CIM:5000")
    print("Köridő:      nincs időkorlát")
    print("======================================")
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False,
        allow_unsafe_werkzeug=True,
    )
