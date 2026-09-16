import os
import random
import secrets
import sqlite3
from datetime import datetime, time, timedelta
from flask import Flask, redirect, render_template, request, session, url_for
from pathlib import Path
from zoneinfo import ZoneInfo

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "local-development-key")

BASE_DIR = Path(__file__).resolve().parent
PLAYERS_FILE = BASE_DIR / "players.txt"
TRIVIA_FILE = BASE_DIR / "trivia.txt"
ANALYTICS_DB = BASE_DIR / "analytics.db"
EASTERN_TIME = ZoneInfo("America/New_York")


def get_db_connection():
    database_url = os.environ.get("DATABASE_URL")

    if database_url:
        import psycopg
        from psycopg.rows import dict_row

        database_url = database_url.replace("postgres://", "postgresql://", 1)
        return psycopg.connect(database_url, row_factory=dict_row)

    connection = sqlite3.connect(ANALYTICS_DB)
    connection.row_factory = sqlite3.Row
    return connection


def init_analytics_db():
    database_url = os.environ.get("DATABASE_URL")
    id_column = (
        "BIGSERIAL PRIMARY KEY"
        if database_url
        else "INTEGER PRIMARY KEY AUTOINCREMENT"
    )

    with get_db_connection() as connection:
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS submissions (
                id {id_column},
                challenge_number INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                result TEXT NOT NULL,
                submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()


def log_submission(challenge_number, event_type, result):
    with get_db_connection() as connection:
        database_url = os.environ.get("DATABASE_URL")
        placeholder = "%s" if database_url else "?"
        connection.execute(
            f"""
            INSERT INTO submissions (
                challenge_number,
                event_type,
                result,
                submitted_at
            ) VALUES ({placeholder}, {placeholder}, {placeholder}, CURRENT_TIMESTAMP)
            """,
            (challenge_number, event_type, result),
        )
        connection.commit()


def require_admin_access():
    auth = request.authorization
    expected_user = os.environ.get("ADMIN_USERNAME", "admin")
    expected_password = os.environ.get("ADMIN_PASSWORD", "change-me")

    if auth is None:
        return False

    return (
        auth.username == expected_user
        and auth.password == expected_password
    )


CARD_RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
CARD_SUITS = ["Clubs", "Diamonds", "Hearts", "Spades"]
CARD_SUIT_SYMBOLS = {
    "Clubs": "♣",
    "Diamonds": "♦",
    "Hearts": "♥",
    "Spades": "♠",
}
CARD_VALUES = {
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "10": 10,
    "J": 10,
    "Q": 10,
    "K": 10,
    "A": 11,
}
BET_OPTIONS = (10, 50, 100)


def create_deck():
    deck = [
        {
            "rank": rank,
            "suit": suit,
            "suit_symbol": CARD_SUIT_SYMBOLS[suit],
            "suit_color": "red" if suit in {"Diamonds", "Hearts"} else "black",
        }
        for suit in CARD_SUITS
        for rank in CARD_RANKS
    ]
    secrets.SystemRandom().shuffle(deck)
    return deck


def hand_value(hand):
    value = sum(CARD_VALUES[card["rank"]] for card in hand)
    aces = sum(card["rank"] == "A" for card in hand)

    while value > 21 and aces:
        value -= 10
        aces -= 1

    return value


def hand_is_blackjack(hand):
    return len(hand) == 2 and hand_value(hand) == 21


def deal_card(game, hand):
    hand.append(game["deck"].pop())


def play_dealer_hand(game):
    while hand_value(game["dealer_hand"]) < 17:
        deal_card(game, game["dealer_hand"])

def settle_blackjack_hand(game):
    play_dealer_hand(game)

    player_hand = game["player_hand"]
    dealer_hand = game["dealer_hand"]
    player_value = hand_value(player_hand)
    dealer_value = hand_value(dealer_hand)
    player_blackjack = hand_is_blackjack(player_hand)
    dealer_blackjack = hand_is_blackjack(dealer_hand)

    if player_value > 21:
        outcome = "loss"
        net_amount = -game["bet"]
    elif player_blackjack and not dealer_blackjack:
        outcome = "blackjack"
        net_amount = int(game["bet"] * 1.5)
    elif dealer_blackjack and not player_blackjack:
        outcome = "loss"
        net_amount = -game["bet"]
    elif dealer_value > 21 or player_value > dealer_value:
        outcome = "win"
        net_amount = game["bet"]
    elif player_value == dealer_value:
        outcome = "push"
        net_amount = 0
    else:
        outcome = "loss"
        net_amount = -game["bet"]

    resolution = {
        "hand_number": game["hand_number"] + 1,
        "player_hand": player_hand,
        "dealer_hand": dealer_hand,
        "player_value": player_value,
        "dealer_value": dealer_value,
        "bet": game["bet"],
        "outcome": outcome,
        "net_amount": net_amount,
    }

    game["results"].append(resolution)
    game["total_amount"] += net_amount
    game["last_resolution"] = resolution

    if len(game["results"]) == 3:
        game["phase"] = "reveal"
        game["final_result_ready"] = True
        return

    game["phase"] = "reveal"
    game["final_result_ready"] = False

    # Keep a separate complete state for the final net-winnings modal.
    if len(game["results"]) >= 3:
        game["phase"] = "complete"
        game["final_result_ready"] = True


def start_blackjack_game():
    game = {
        "deck": create_deck(),
        "hand_number": 0,
        "player_hand": [],
        "dealer_hand": [],
        "bet": None,
        "results": [],
        "total_amount": 0,
        "phase": "betting",
    }
    return game


def blackjack_view(game):
    return render_template(
        "blackjack.html",
        game=game,
        bet_options=BET_OPTIONS,
        player_value=hand_value(game["player_hand"]),
        dealer_value=(
            hand_value(game["dealer_hand"])
            if game["phase"] == "complete"
            else None
        ),
    )


init_analytics_db()


def scramble_word(word, random_generator):
    word = word.upper()
    letters = list(word)

    while True:
        random_generator.shuffle(letters)
        scrambled = "".join(letters)

        if scrambled != word:
            return scrambled


def load_players():
    players = []

    with PLAYERS_FILE.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if line:
                hint, player_name = line.split("|", 1)

                players.append({
                    "hint": hint.strip(),
                    "name": player_name.strip()
                })

    return players


def load_trivia():
    trivia_questions = []

    with TRIVIA_FILE.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if line:
                parts = [part.strip() for part in line.split("|")]

                if len(parts) != 6:
                    continue

                question, answer, *options = parts

                if answer in options:
                    trivia_questions.append({
                        "question": question,
                        "answer": answer,
                        "options": options
                    })

    return trivia_questions


@app.route("/", methods=["GET", "POST"])
def home():
    players = load_players()
    trivia_questions = load_trivia()

    if not players:
        return "No players found in players.txt", 500

    if not trivia_questions:
        return "No trivia questions found in trivia.txt", 500

    today = datetime.now(EASTERN_TIME).date()
    challenge_number = today.toordinal()
    next_midnight = datetime.combine(
        today + timedelta(days=1),
        time.min,
        tzinfo=EASTERN_TIME
    )

    player_index = challenge_number % len(players)
    selected_player = players[player_index]

    hint = selected_player["hint"]
    player_name = selected_player["name"]

    # Using today's challenge number as the seed makes
    # the scrambled letters remain the same all day.
    daily_random = random.Random(challenge_number)

    name_parts = player_name.split()

    scrambled_name = " ".join(
        scramble_word(part, daily_random)
        for part in name_parts
    )

    trivia_index = challenge_number % len(trivia_questions)
    selected_trivia = trivia_questions[trivia_index]
    trivia_options = selected_trivia["options"][:]
    daily_random.shuffle(trivia_options)

    if len(trivia_options) > 1 and trivia_options[0] == selected_trivia["answer"]:
        trivia_options[0], trivia_options[1] = (
            trivia_options[1],
            trivia_options[0]
        )

    result = session.get("scramble_result")
    trivia_result = session.get("trivia_result")
    blackjack_result = session.get("blackjack_result")

    if request.method == "POST":
        if request.form.get("action") == "trivia":
            result = request.form.get("scramble_result")
            trivia_answer = request.form.get("trivia_answer", "")

            if trivia_answer == selected_trivia["answer"]:
                trivia_result = "correct"
            else:
                trivia_result = "incorrect"

            session["trivia_result"] = trivia_result
            log_submission(challenge_number, "trivia", trivia_result)
            return redirect(url_for("blackjack"))
        else:
            guess = request.form.get("guess", "")

            cleaned_guess = " ".join(guess.upper().split())
            correct_answer = player_name.upper()

            if cleaned_guess == correct_answer:
                result = "correct"
            else:
                result = "incorrect"

            session["scramble_result"] = result
            log_submission(challenge_number, "scramble", result)

    return render_template(
        "index.html",
        challenge_number=challenge_number,
        hint=hint,
        scrambled_name=scrambled_name,
        result=result,
        trivia_question=selected_trivia["question"],
        trivia_options=trivia_options,
        trivia_answer=selected_trivia["answer"],
        trivia_result=trivia_result,
        blackjack_result=blackjack_result,
        player_name=player_name,
        next_midnight=next_midnight.isoformat()
    )


@app.route("/blackjack", methods=["GET", "POST"])
def blackjack():
    if request.method == "POST":
        action = request.form.get("action")

        game = session.get("blackjack_game")

        if game and "phase" not in game:
            game = start_blackjack_game()
            session["blackjack_game"] = game

        if game and game["phase"] != "complete":
            if action == "bet" and game["phase"] == "betting":
                try:
                    amount = int(request.form.get("amount", ""))
                except ValueError:
                    amount = None

                if amount in BET_OPTIONS:
                    game["bet"] = amount
                    game["player_hand"] = []
                    game["dealer_hand"] = []

                    for _ in range(2):
                        deal_card(game, game["player_hand"])
                        deal_card(game, game["dealer_hand"])

                    game["phase"] = "playing"

                    if hand_is_blackjack(game["player_hand"]):
                        settle_blackjack_hand(game)

            elif action == "hit" and game["phase"] == "playing":
                deal_card(game, game["player_hand"])

                if hand_value(game["player_hand"]) >= 21:
                    settle_blackjack_hand(game)

            elif action == "stand" and game["phase"] == "playing":
                settle_blackjack_hand(game)

            elif action == "continue-reveal" and game["phase"] == "reveal":
                if game.get("final_result_ready"):
                    game["phase"] = "complete"
                    session["blackjack_game"] = game
                    return redirect(url_for("blackjack"))

                game["hand_number"] += 1
                game["player_hand"] = []
                game["dealer_hand"] = []
                game["bet"] = None
                game["last_resolution"] = None
                game["phase"] = "betting"

            elif action == "finalize-results" and game["phase"] == "complete":
                session["blackjack_result"] = game["total_amount"]
                session.pop("blackjack_game", None)
                return redirect(url_for("home"))

            session["blackjack_game"] = game

        elif game and game["phase"] == "complete":
            if action == "finalize-results":
                session["blackjack_result"] = game["total_amount"]
                session.pop("blackjack_game", None)
                return redirect(url_for("home"))

            return redirect(url_for("blackjack"))

        return redirect(url_for("blackjack"))

    game = session.get("blackjack_game")

    if game is None or "phase" not in game:
        game = start_blackjack_game()
        session["blackjack_game"] = game

    return blackjack_view(game)


@app.route("/blackjack/results")
def blackjack_results():
    return redirect(url_for("home"))


@app.route("/admin/analytics")
def analytics_summary():
    if not require_admin_access():
        return (
            "Unauthorized",
            401,
            {"WWW-Authenticate": "Basic realm='Admin Area'"},
        )

    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                event_type,
                result,
                COUNT(*) AS count
            FROM submissions
            GROUP BY event_type, result
            ORDER BY event_type, result
            """
        ).fetchall()
        daily_rows = connection.execute(
            """
            SELECT
                DATE(submitted_at) AS submission_date,
                event_type,
                COUNT(*) AS count
            FROM submissions
            GROUP BY DATE(submitted_at), event_type
            ORDER BY submission_date DESC, event_type
            """
        ).fetchall()

    summary = []
    for row in rows:
        summary.append(f"{row['event_type']} {row['result']}: {row['count']}")

    if not summary:
        summary.append("No submissions yet.")

    daily_summary = [
        f"{row['submission_date']} - {row['event_type']}: {row['count']}"
        for row in daily_rows
    ]

    if not daily_summary:
        daily_summary.append("No daily submissions yet.")

    html = (
        "<h1>Buffalo Scramble Analytics</h1>"
        "<h2>Overall totals</h2><ul><li>"
        + "</li><li>".join(summary)
        + "</li></ul>"
        "<h2>Engagement by date</h2><ul><li>"
        + "</li><li>".join(daily_summary)
        + "</li></ul>"
    )
    return html


if __name__ == "__main__":
    app.run(debug=True)