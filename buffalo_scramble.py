import random
from datetime import date


def scramble_word(word):
    word = word.upper()

    while True:
        letters = list(word)
        random.shuffle(letters)
        scrambled = "".join(letters)

        if scrambled != word:
            return scrambled


# Load player names from players.txt
with open("players.txt", "r") as file:
    players = []

    for line in file:
        line = line.strip()

        if line:
            team, player_name = line.split("|", 1)

            players.append({
                "team": team,
                "name": player_name
            })


# Stop the program if players.txt is empty
if not players:
    print("No players found in players.txt")
    quit()

# Select the daily player
today = date.today()
challenge_number = today.toordinal()

player_index = today.toordinal() % len(players)
selected_player = players[player_index]

team = selected_player["team"]
player_name = selected_player["name"]


# Separate and scramble each part of the player's name
name_parts = player_name.split()

scrambled_name = " ".join(
    scramble_word(part)
    for part in name_parts
)

# Display the challenge
print("BUFFALO SCRAMBLE")
print("----------------")
print(f"Challenge #{challenge_number}")
print(f"Hint: {team}")
print(f"\nScrambled Name: {scrambled_name}")


# Ask the user for one guess
guess = input("\nYour guess: ")

guess = " ".join(guess.upper().split())
answer = player_name.upper()


# Check the answer
if guess == answer:
    result_emoji = "🟩"
    print("\n✅ Correct!")
else:
    result_emoji = "🟥"
    print("\n❌ Incorrect!")


print(f"\nAnswer: {player_name}")


# Display a shareable result without revealing the answer
print("\n----------------")
print("SHARE YOUR RESULT")
print("----------------")
print(f"Buffalo Scramble #{challenge_number}")
print(result_emoji)
print(f"Hint: {team}")