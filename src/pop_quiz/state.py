"""Game state management for the quiz."""

import asyncio
import logging
import secrets
import time
import uuid
from dataclasses import dataclass, field
from operator import attrgetter
from random import shuffle
from typing import Self

from pop_quiz.animals import random_animal_name
from pop_quiz.models import Answer, Participant, Question, Quiz, QuizPhase
from pop_quiz.scoring import calculate_points

logger = logging.getLogger(__name__)

MAX_PARTICIPANTS = 100
LEADERBOARD_DISPLAY_LIMIT = 10


@dataclass
class GameState:
    """Manages the state of an active quiz game.

    All mutable operations must be performed while holding the lock to prevent
    concurrent modification from multiple WebSocket handlers.
    """

    quiz: Quiz
    pin: str
    phase: QuizPhase = QuizPhase.LOBBY
    current_question: int = 0
    question_start_time: float = 0.0
    participants: dict[str, Participant] = field(default_factory=dict)
    shuffled_indices: dict[int, list[int]] = field(default_factory=dict)
    scores_at_question_start: dict[str, int] = field(default_factory=dict)
    _cached_qr_code: str | None = field(default=None, repr=False)
    _cached_join_url: str | None = field(default=None, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @classmethod
    def create(cls, quiz: Quiz) -> Self:
        """Create a new game with a random 6-digit PIN."""
        pin = secrets.randbelow(900_000) + 100_000
        state = cls(quiz=quiz, pin=str(pin))
        state._generate_shuffled_indices()
        return state

    def get_join_url(self, host_header: str) -> str:
        """Get the join URL, caching based on host header."""
        from pop_quiz.qr import build_join_url

        # Cache is invalidated if host changes (shouldn't happen in practice)
        if (
            self._cached_join_url is None
            or host_header not in self._cached_join_url
        ):
            self._cached_join_url = build_join_url(host_header, self.pin)
        return self._cached_join_url

    def get_qr_code(self, host_header: str) -> str:
        """Get the QR code as base64, generating and caching if needed."""
        from pop_quiz.qr import generate_qr_code_base64

        if self._cached_qr_code is None:
            join_url = self.get_join_url(host_header)
            self._cached_qr_code = generate_qr_code_base64(join_url)
        return self._cached_qr_code

    def _generate_shuffled_indices(self) -> None:
        for question_index, question in enumerate(self.quiz.questions):
            indices = list(range(len(question.choices)))
            shuffle(indices)
            self.shuffled_indices[question_index] = indices

    def get_shuffled_question(
        self, question_index: int
    ) -> tuple[list[str], int]:
        """Get shuffled choices and the shuffled correct index for a question."""
        question = self.quiz.questions[question_index]
        indices = self.shuffled_indices.get(
            question_index, list(range(len(question.choices)))
        )
        shuffled_choices = [question.choices[i] for i in indices]
        shuffled_correct_index = indices.index(question.correct_index)
        return shuffled_choices, shuffled_correct_index

    def _to_original_choice_index(
        self, question_index: int, shuffled_index: int
    ) -> int:
        question = self.quiz.questions[question_index]
        indices = self.shuffled_indices.get(
            question_index, list(range(len(question.choices)))
        )
        return indices[shuffled_index]

    def _to_shuffled_choice_index(
        self, question_index: int, original_index: int
    ) -> int | None:
        indices = self.shuffled_indices.get(question_index, [])
        return (
            indices.index(original_index)
            if original_index in indices
            else None
        )

    def add_participant(
        self, stored_id: str | None = None
    ) -> Participant | None:
        """Add a new participant or reconnect an existing one.

        Args:
            stored_id: ID from a previous session for reconnection. Only accepted
                if it matches an existing participant to prevent impersonation.

        Returns:
            The participant if added/reconnected, None if not allowed.
        """
        # Pick a fresh animal name for this join
        display_name = random_animal_name()

        # Reconnection: keep the existing participant but freshen the name
        if stored_id and stored_id in self.participants:
            existing = self.participants[stored_id]
            existing.display_name = display_name
            return existing

        # New participants can only join during lobby phase
        if self.phase != QuizPhase.LOBBY:
            return None

        if len(self.participants) >= MAX_PARTICIPANTS:
            logger.warning("Participant limit reached: %d", MAX_PARTICIPANTS)
            return None

        # Always generate server-side ID for new participants to prevent impersonation
        new_id = str(uuid.uuid4())
        participant = Participant(id=new_id, display_name=display_name)
        self.participants[new_id] = participant
        return participant

    def remove_participant(self, participant_id: str) -> bool:
        """Remove a participant. Only allowed in lobby phase."""
        if self.phase != QuizPhase.LOBBY:
            return False
        if participant_id in self.participants:
            del self.participants[participant_id]
            return True
        return False

    def start_quiz(self) -> bool:
        """Start the quiz. Returns False if cannot start."""
        if not self.participants or self.phase != QuizPhase.LOBBY:
            return False
        self.phase = QuizPhase.COUNTDOWN
        self.current_question = 0
        return True

    def start_question(self) -> None:
        """Transition from countdown to question phase."""
        self.phase = QuizPhase.QUESTION
        self.question_start_time = time.time()
        self.scores_at_question_start = {
            p.id: p.score for p in self.participants.values()
        }

    def submit_answer(self, answer: Answer) -> bool:
        """Submit an answer for a participant. Returns True if accepted."""
        if self.phase != QuizPhase.QUESTION:
            return False

        if not (participant := self.participants.get(answer.participant_id)):
            return False

        if answer.question_index in participant.answers:
            return False
        if answer.question_index != self.current_question:
            return False

        question = self.quiz.questions[answer.question_index]

        # Validate choice_index bounds
        if not 0 <= answer.choice_index < len(question.choices):
            logger.warning(
                "Invalid choice_index %d for question with %d choices",
                answer.choice_index,
                len(question.choices),
            )
            return False

        # Calculate time taken server-side (not trusted from client)
        time_taken = time.time() - self.question_start_time
        if time_taken > question.time_limit_seconds:
            # Clamp to time limit - late answers are accepted but scored at max time
            time_taken = question.time_limit_seconds

        original_choice = self._to_original_choice_index(
            answer.question_index, answer.choice_index
        )
        participant.answers[answer.question_index] = original_choice
        participant.answer_times_seconds[answer.question_index] = time_taken

        if original_choice == question.correct_index:
            participant.score += calculate_points(
                time_taken, question.time_limit_seconds
            )

        return True

    def reveal_answer(self) -> None:
        """Transition to reveal phase."""
        self.phase = QuizPhase.REVEAL

    def next_question(self) -> bool:
        """Move to the next question. Returns False if quiz is finished."""
        self.current_question += 1
        if self.current_question >= len(self.quiz.questions):
            self.phase = QuizPhase.FINISHED
            return False
        self.phase = QuizPhase.COUNTDOWN
        return True

    @property
    def leaderboard(self) -> list[Participant]:
        """Get participants sorted by score descending."""
        if self.phase == QuizPhase.QUESTION:
            # Sort by score at start of question to keep order stable
            return sorted(
                self.participants.values(),
                key=lambda p: self.scores_at_question_start.get(p.id, p.score),
                reverse=True,
            )
        return sorted(
            self.participants.values(), key=attrgetter("score"), reverse=True
        )

    @property
    def answers_count(self) -> int:
        """Count how many participants answered the current question."""
        return sum(
            1
            for p in self.participants.values()
            if self.current_question in p.answers
        )

    def get_current_question(self) -> Question | None:
        """Get the current question or None if out of range."""
        if self.current_question < len(self.quiz.questions):
            return self.quiz.questions[self.current_question]
        return None

    def _build_question_data(
        self,
        question_index: int,
        include_correct: bool = False,
        participant: Participant | None = None,
    ) -> dict:
        question = self.quiz.questions[question_index]
        shuffled_choices, shuffled_correct = self.get_shuffled_question(
            question_index
        )
        data: dict = {
            "text": question.text,
            "choices": shuffled_choices,
            "time_limit": question.time_limit_seconds,
            "image": question.image_url,
        }
        if include_correct:
            data["correct"] = shuffled_correct
        if participant and question_index in participant.answers:
            selected_index = self._to_shuffled_choice_index(
                question_index, participant.answers[question_index]
            )
            # Only include if we could map the index (handles edge cases)
            if selected_index is not None:
                data["selected"] = selected_index

        # Add reveal stats for participant (time taken, points gained)
        if include_correct and participant:
            if question_index in participant.answer_times_seconds:
                data["time_taken"] = participant.answer_times_seconds[
                    question_index
                ]
            # Calculate points gained for this question
            if question_index in participant.answers:
                # Check if answer was correct (compare original indices)
                if (
                    participant.answers[question_index]
                    == question.correct_index
                ):
                    time_taken = participant.answer_times_seconds.get(
                        question_index, question.time_limit_seconds
                    )
                    data["points_gained"] = calculate_points(
                        time_taken, question.time_limit_seconds
                    )
                else:
                    data["points_gained"] = 0
            else:
                data["points_gained"] = 0  # Timed out

        # Add server timing info for timer synchronization during question phase
        if self.phase == QuizPhase.QUESTION:
            current_time = time.time()
            elapsed = current_time - self.question_start_time
            data["server_time"] = current_time
            data["question_start_time"] = self.question_start_time
            data["time_remaining"] = max(
                0, question.time_limit_seconds - elapsed
            )

        return data

    def _base_state(self) -> dict:
        """Build the common state fields shared by host and participant views."""
        return {
            "phase": self.phase,
            "quiz_title": self.quiz.title,
            "current_question_index": self.current_question,
            "total_questions": len(self.quiz.questions),
        }

    def _all_questions_data(
        self, participant: Participant | None = None
    ) -> list[dict]:
        """Build question data for all questions (used in finished phase)."""
        return [
            self._build_question_data(
                i, include_correct=True, participant=participant
            )
            for i in range(len(self.quiz.questions))
        ]

    def _get_participant_score_for_host(
        self, participant: Participant
    ) -> dict:
        """Get participant score info based on current phase."""
        base = {
            "id": participant.id,
            "display_name": participant.display_name,
            "answered": self.current_question in participant.answers,
        }

        match self.phase:
            case QuizPhase.QUESTION:
                base["score"] = self.scores_at_question_start.get(
                    participant.id, participant.score
                )
            case QuizPhase.REVEAL:
                previous = self.scores_at_question_start.get(
                    participant.id, participant.score
                )
                base["score"] = participant.score
                base["points_gained"] = participant.score - previous
            case _:
                base["score"] = participant.score

        return base

    def get_state_for_host(self) -> dict:
        """Get the full game state for the host view."""
        state = self._base_state() | {
            "question": self._build_question_data(
                self.current_question, include_correct=True
            )
            if self.get_current_question()
            else None,
            "participants": [
                self._get_participant_score_for_host(p)
                for p in self.leaderboard
            ],
            "answers_count": self.answers_count,
        }

        if self.phase == QuizPhase.FINISHED:
            state["all_questions"] = self._all_questions_data()

        return state

    def _get_participant_score(self, participant: Participant) -> int:
        """Get participant score, using saved score during question phase."""
        if self.phase == QuizPhase.QUESTION:
            return self.scores_at_question_start.get(
                participant.id, participant.score
            )
        return participant.score

    def _get_participant_rank(
        self, leaderboard: list[Participant], participant: Participant
    ) -> int | None:
        for index, entry in enumerate(leaderboard, start=1):
            if entry.id == participant.id:
                return index
        return None

    def _leaderboard_snapshot(
        self, leaderboard: list[Participant], participant: Participant | None
    ) -> list[dict]:
        return [
            {
                "display_name": entry.display_name,
                "score": entry.score,
                "is_self": participant is not None
                and entry.id == participant.id,
            }
            for entry in leaderboard[:LEADERBOARD_DISPLAY_LIMIT]
        ]

    def get_state_for_participant(self, participant_id: str) -> dict:
        """Get the game state for a specific participant."""
        participant = self.participants.get(participant_id)
        state = self._base_state()
        leaderboard = self.leaderboard

        if participant:
            state |= {
                "display_name": participant.display_name,
                "score": self._get_participant_score(participant),
                "has_answered": self.current_question in participant.answers,
            }
            rank = self._get_participant_rank(leaderboard, participant)
            if rank is not None:
                state["rank"] = rank
                state["total_participants"] = len(leaderboard)

        match self.phase:
            case QuizPhase.COUNTDOWN | QuizPhase.QUESTION:
                if self.get_current_question():
                    state["question"] = self._build_question_data(
                        self.current_question
                    )
                if (
                    self.phase == QuizPhase.COUNTDOWN
                    and self.current_question > 0
                ):
                    state["leaderboard"] = self._leaderboard_snapshot(
                        leaderboard, participant
                    )

            case QuizPhase.REVEAL:
                if self.get_current_question():
                    state["question"] = self._build_question_data(
                        self.current_question,
                        include_correct=True,
                        participant=participant,
                    )

            case QuizPhase.FINISHED:
                state["leaderboard"] = self._leaderboard_snapshot(
                    leaderboard, participant
                )
                state["all_questions"] = self._all_questions_data(participant)

        return state
