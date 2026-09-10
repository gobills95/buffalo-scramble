import random
from datetime import datetime, time, timedelta
from flask import Flask, render_template, request
from pathlib import Path
from zoneinfo import ZoneInfo

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
PLAYERS_FILE = BASE_DIR / "players.txt"
EASTERN_TIME = ZoneInfo("America/New_York")

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


@app.route("/", methods=["GET", "POST"])
def home():
    players = load_players()

    if not players:
        return "No players found in players.txt", 500

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

    result = None

    if request.method == "POST":
        guess = request.form.get("guess", "")

        cleaned_guess = " ".join(guess.upper().split())
        correct_answer = player_name.upper()

        if cleaned_guess == correct_answer:
            result = "correct"
        else:
            result = "incorrect"

    return render_template(
        "index.html",
        challenge_number=challenge_number,
        hint=hint,
        scrambled_name=scrambled_name,
        result=result,
        player_name=player_name,
        next_midnight=next_midnight.isoformat()
    )


if __name__ == "__main__":
    app.run(debug=True)