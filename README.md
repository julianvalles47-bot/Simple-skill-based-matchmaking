a small python tool for 1v1 matchmaking in indie fighting games.

it has elo ratings, queues, leaderboards, private games and an api so ur game can use it. works with unity, godot, gamemaker and probly anything that can send http requests.

its a simple starter project, not some perfect anti cheat system. it trusts the game server to report who won, so dont expect it to stop every cheater.

## quick start (windows)

1. install python 3.10+ from [python.org](https://www.python.org/downloads/)
2. make sure u check **Add Python to PATH**
3. unzip the project
4. double click `start.bat`
5. wait for it to start then open http://127.0.0.1:8000/docs

the first run sets everything up for u. keep the terminal open while its running. press `Ctrl+C` to stop it.

for mac/linux, run:

```bash
./start.sh
```

or use docker:

```bash
docker compose up --build
```

## testing it

create a test game using the api, then run:

```bash
python examples/client_example.py http://127.0.0.1:8000 demo-game alice
```

run it again in another terminal but change `alice` to `bob`.

the first player waits in the queue. when another player with a similar rating joins, they get matched.

u can also test the api at `/docs`.

## how it works

everyone starts with 1000 elo for each game.

- win = more points
- lose = less points
- beating a better player gives u more points
- every game has its own rank and leaderboard

it tries to match players with similar ratings. if u wait too long, it starts accepting bigger rating differences.

after the match, the game server reports who won and the ratings update. draws arent supported yet.

## using it with ur game

your game sends requests to the api. thats basically it.

1. ur game identifies the player
2. ur backend gets them a player token
3. the player joins the queue
4. after the match, ur backend reports who won

it can work with unity, godot, unreal, gamemaker and browser games on itch.io.

check `docs/API.md` for more details.

### public vs private

**public games:** anyone can find them and see the leaderboard.

**private games:** dont show up in the public list. players need an invite code to access them. its not super secure tho, since people can share the code.

each game has its own ratings, so ur rank in one game wont affect another.

## putting it online

by default, it only runs on ur own computer. other people on the internet cant connect to it.

if u want real players to use it, u need online hosting, HTTPS and proper security settings.

**dont put server keys inside ur game files or public github repo.** people can steal them. keep them on ur backend instead.

development mode is only for testing. dont expose it to the internet because people can fake results.

this project doesnt have built in anti cheat, rate limits, account recovery or proper abuse protection yet. its a starter project, so theres still work to do before using it for serious ranked matches.

## setup gui

run:

```bash
python setup_gui.py
```

this opens a small window where u can change settings and start or stop the server.

## running tests

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

## project files

- `matchmaker/app.py` - main api and matchmaking
- `matchmaker/db.py` - saves game and player data
- `matchmaker/security.py` - handles tokens and server keys
- `docs/API.md` - api guide
- `examples/client_example.py` - example client
- `tests/` - tests
- `setup_gui.py` - optional setup window

## credits n license

made using python, fastapi, uvicorn, sqlite and other open source tools.

uses the standard elo rating system. the matchmaking logic was made for this project.

license is MIT, so u can use and modify it under the license terms.