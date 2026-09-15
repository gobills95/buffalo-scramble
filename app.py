import os
import random
import sqlite3
from datetime import datetime, time, timedelta
from flask import Flask, render_template, request
from pathlib import Path
from zoneinfo import ZoneInfo

app = Flask(__name__)

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
    with get_db_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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

    result = None
    trivia_result = None

    if request.method == "POST":
        if request.form.get("action") == "trivia":
            result = request.form.get("scramble_result")
            trivia_answer = request.form.get("trivia_answer", "")

            if trivia_answer == selected_trivia["answer"]:
                trivia_result = "correct"
            else:
                trivia_result = "incorrect"

            log_submission(challenge_number, "trivia", trivia_result)
        else:
            guess = request.form.get("guess", "")

            cleaned_guess = " ".join(guess.upper().split())
            correct_answer = player_name.upper()

            if cleaned_guess == correct_answer:
                result = "correct"
            else:
                result = "incorrect"

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
        player_name=player_name,
        next_midnight=next_midnight.isoformat()
    )


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

    summary = []
    for row in rows:
        summary.append(f"{row['event_type']} {row['result']}: {row['count']}")

    if not summary:
        summary.append("No submissions yet.")

    html = "<h1>Buffalo Scramble Analytics</h1><ul><li>" + "</li><li>".join(summary) + "</li></ul>"
    return html


if __name__ == "__main__":
    app.run(debug=True)