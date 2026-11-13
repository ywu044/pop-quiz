# Pop Quiz

A real-time, self-hosted, browser-based quiz application with a FastAPI backend serving both HTTP and WebSocket endpoints. Perfect for classrooms, meetups, or any gathering where you want to run an interactive quiz.

## Table of Contents

- [Quick Start](#quick-start)
- [Features](#features)
- [Command-line Options](#command-line-options)
- [Portable Zipapp](#portable-zipapp)
- [Quiz Format](#quiz-format)
- [How It Works](#how-it-works)
- [Scoring](#scoring)
- [Edge Cases Handled](#edge-cases-handled)
- [Project Structure](#project-structure)
- [Development](#development)
- [License](#license)

## Quick Start

1.  **Install dependencies:**
    ```sh
    uv sync
    ```

2.  **Run the quiz:**
    ```sh
    uv run pop-quiz /path/to/quiz.yaml
    ```
    Or, to generate a random quiz using OpenAI:
    ```sh
    export OPENAI_API_KEY=your_key
    uv run pop-quiz
    ```

This will start a local server, open the host dashboard in your browser, and display a QR code for participants to join.

## Features

- **Simple hosting**: Run from the terminal with a single command
- **Easy joining**: Participants scan a QR code, use the copy link button, or enter a PIN
- **Fun names**: Each participant gets a random animal name (e.g., "Brave 🐼 Panda")
- **Real-time updates**: Live leaderboard and answer counts powered by WebSockets
- **Kahoot-style scoring**: Faster correct answers earn more points (500-1000)
- **YAML quizzes**: Define quizzes with 2-6 choices per question, optional images, and custom time limits
- **Markdown support**: Use markdown in questions and answers for formatting and code blocks
- **Mobile friendly**: Fullscreen mode available on mobile devices
- **Connection resilience**: Participants can refresh and keep their name; disconnected players shown as grayed out

## Screenshots

| Host View (Lobby) | Participant View (Answering) |
|---|---|
| ![Host View](https://via.placeholder.com/400x300.png?text=Host+View) | ![Participant View](https://via.placeholder.com/400x300.png?text=Participant+View) |

#### Command-line Options

```
pop-quiz [OPTIONS] [QUIZ_FILE]

Arguments:
  QUIZ_FILE          Path to the quiz YAML file (optional if OPENAI_API_KEY is set)

Options:
  --port, -p PORT    Port to run the server on (default: 8000)
  --host HOST        Host to bind to (default: 0.0.0.0)
  --no-browser       Don't open the browser automatically
  --no-images        Disable image generation
  --difficulty LEVEL Difficulty level: easy, medium, hard, progressive
  --num-questions, -n NUM
                     Number of questions to generate (default: 10)
  --theme, -t THEME  Theme for the quiz (default: random)
  --language, -l LANG
                     Language for generated quiz content (default: English)
  -h, --help         Show help message
```

#### Portable Zipapp

You can also build a self-contained executable that bundles all dependencies:

```sh
./scripts/build-zipapp.sh
python dist/pop-quiz.pyz quiz.yaml
```

The `.pyz` file only requires Python 3.11+ to run and can be copied to other machines.

## Quiz Format

Quizzes are defined in YAML format:

```yaml
title: "My Quiz"
description: "An optional description shown on the host dashboard"

questions:
  - question: "What is 2 + 2?"
    choices:
      - "3"
      - "4"
      - "5"
      - "6"
    correct: 1  # Index of correct answer (0-based)
    time_limit: 30  # Seconds (optional, default: 30)

  - question: "What does this code print?"
    choices:
      - "`Hello`"
      - "`World`"
      - "`Hello World`"
    correct: 2
    time_limit: 45
    image: "https://example.com/code-snippet.png"  # Optional image
```

### Question Requirements

- **Choices**: 2-6 options per question
- **Correct index**: Zero-based index of the correct answer
- **Time limit**: 1-300 seconds (default: 30)
- **Images**: Optional URL to display above the question
- **Markdown**: Questions and choices support markdown formatting

## How It Works

### For the Host

1. Run `pop-quiz` with your quiz file
2. The dashboard opens showing a QR code, join URL, and PIN
3. Share the join link using the copy button or let participants scan the QR code
4. Wait for participants to join (count updates in real-time)
5. Click **Start Quiz** when ready
6. Questions auto-advance after the time limit, or when everyone has answered
7. After each question, see the reveal phase showing correct answers and points earned
8. Final leaderboard and winner displayed at the end

### For Participants

1. Scan the QR code or visit the join URL
2. Enter the 6-digit PIN shown on the host screen
3. You'll be assigned a random animal name (preserved if you refresh)
4. Wait in the lobby until the host starts the quiz
5. Answer each question as fast as possible for maximum points
6. Your score updates after each reveal phase
7. Review all questions and your answers at the end

## Scoring

Points are awarded based on speed and correctness:

| Answer | Points |
|--------|--------|
| Correct (instant) | 1000 |
| Correct (at time limit) | 500 |
| Correct (in between) | 500-1000 (linear scale) |
| Wrong or no answer | 0 |

The leaderboard is sorted by total score. During the reveal phase, you can see how many points each player gained on that question (e.g., "+750").

## Edge Cases Handled

- **Page refresh**: Participants keep their animal name and can rejoin
- **Disconnection**: Shown as grayed out on host dashboard; can reconnect anytime
- **Late joiners**: Cannot join after the quiz has started
- **Reconnection mid-quiz**: Allowed - participant keeps their score and can continue answering
- **Late answers**: Submissions after the time limit are rejected
- **Double answers**: Only the first answer to each question is accepted
- **Early finish**: If all participants answer before time runs out, the reveal phase starts immediately
- **Choice shuffling**: Answer choices are randomized per-game to prevent memorization

## Project Structure

```
pop-quiz/
├── pyproject.toml
├── README.md
├── scripts/
│   └── build-zipapp.sh    # Build portable executable
├── src/pop_quiz/
│   ├── __init__.py
│   ├── cli.py             # Command-line interface
│   ├── models.py          # Data models (Quiz, Question, Participant, etc.)
│   ├── animals.py         # Random animal name generator
│   ├── scoring.py         # Points calculation
│   ├── state.py           # Game state management
│   ├── server.py          # FastAPI application & WebSocket handlers
│   ├── handlers.py        # WebSocket message handlers
│   ├── connections.py     # Connection tracking & broadcasting
│   ├── generator.py       # Quiz generation via AI
│   ├── timers.py          # Async timers for game flow
│   ├── qr.py              # QR code generation & URL building
│   └── static/
│       ├── common.css     # Shared styles
│       ├── common.js      # Shared JavaScript utilities
│       ├── host.html      # Host dashboard template
│       ├── host.css       # Host-specific styles
│       ├── host.js        # Host dashboard logic
│       ├── participant.html  # Participant view template
│       ├── participant.css   # Participant-specific styles
│       ├── participant.js    # Participant view logic
│       ├── join.html      # PIN entry page
│       └── join.css       # Join page styles
└── tests/
    ├── test_animals.py
    ├── test_models.py
    ├── test_scoring.py
    ├── test_state.py
    ├── test_qr.py
    ├── test_handlers.py
    ├── test_connections.py
    └── test_timers.py
```

## Development

```sh
# Install dev dependencies
uv sync

# Run tests
uv run pytest

# Run linter
uv run ruff check src/ tests/

# Format code
uv run ruff format src/ tests/
```

## License

MIT
