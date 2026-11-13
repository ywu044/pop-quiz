"""Tests for the timers module."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from pop_quiz.models import Question, Quiz, QuizPhase
from pop_quiz.state import GameState
from pop_quiz.timers import (
    COUNTDOWN_DURATION_SECONDS,
    REVEAL_DURATION_SECONDS,
    check_all_answered,
    run_countdown,
    schedule_question_timer,
)


def make_quiz(time_limit: int = 30) -> Quiz:
    """Create a simple quiz for testing."""
    return Quiz(
        title="Test Quiz",
        questions=[
            Question(
                text="Q1?",
                choices=["A", "B", "C", "D"],
                correct_index=0,
                time_limit_seconds=time_limit,
            ),
            Question(
                text="Q2?",
                choices=["X", "Y", "Z"],
                correct_index=1,
            ),
        ],
    )


class TestTimerConstants:
    """Tests for timer constants."""

    def test_countdown_duration_positive(self) -> None:
        """Countdown duration should be positive."""
        assert COUNTDOWN_DURATION_SECONDS > 0

    def test_reveal_duration_positive(self) -> None:
        """Reveal duration should be positive."""
        assert REVEAL_DURATION_SECONDS > 0


@pytest.mark.asyncio
class TestRunCountdown:
    """Tests for run_countdown function."""

    async def test_does_nothing_for_none_state(self) -> None:
        """Should return immediately for None state."""
        with patch("pop_quiz.timers.asyncio.sleep", new_callable=AsyncMock):
            await run_countdown(None)
            # Should not raise

    async def test_does_nothing_for_wrong_phase(self) -> None:
        """Should return immediately if not in countdown phase."""
        state = GameState.create(make_quiz())
        state.add_participant("p1")
        # Still in LOBBY phase

        with patch(
            "pop_quiz.timers.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            await run_countdown(state)
            mock_sleep.assert_not_called()

    async def test_transitions_to_question_phase(self) -> None:
        """Should transition to question phase after countdown."""
        state = GameState.create(make_quiz())
        state.add_participant("p1")
        state.start_quiz()  # Now in COUNTDOWN

        with (
            patch(
                "pop_quiz.timers.asyncio.sleep", new_callable=AsyncMock
            ) as mock_sleep,
            patch("pop_quiz.timers.broadcast_all", new_callable=AsyncMock),
            patch(
                "pop_quiz.timers.schedule_question_timer",
                new_callable=AsyncMock,
            ),
        ):
            await run_countdown(state)

            mock_sleep.assert_called_with(COUNTDOWN_DURATION_SECONDS)
            assert state.phase == QuizPhase.QUESTION


@pytest.mark.asyncio
class TestCheckAllAnswered:
    """Tests for check_all_answered function."""

    async def test_does_nothing_for_none_state(self) -> None:
        """Should return immediately for None state."""
        await check_all_answered(None)
        # Should not raise

    async def test_does_nothing_for_wrong_phase(self) -> None:
        """Should return immediately if not in question phase."""
        state = GameState.create(make_quiz())
        state.add_participant("p1")
        state.start_quiz()
        # Still in COUNTDOWN

        with patch(
            "pop_quiz.timers.broadcast_all", new_callable=AsyncMock
        ) as mock_broadcast:
            await check_all_answered(state)
            mock_broadcast.assert_not_called()

    async def test_does_nothing_if_not_all_answered(self) -> None:
        """Should not advance if not all participants answered."""
        state = GameState.create(make_quiz())
        p1 = state.add_participant()
        state.add_participant()
        state.start_quiz()
        state.start_question()

        # Only p1 answers
        state.participants[p1.id].answers[0] = 0

        with patch(
            "pop_quiz.timers.broadcast_all", new_callable=AsyncMock
        ) as mock_broadcast:
            await check_all_answered(state)
            mock_broadcast.assert_not_called()
            assert state.phase == QuizPhase.QUESTION

    async def test_advances_when_all_answered(self) -> None:
        """Should advance to reveal when all answered."""
        state = GameState.create(make_quiz())
        p1 = state.add_participant()
        p2 = state.add_participant()
        state.start_quiz()
        state.start_question()

        # Both answer
        state.participants[p1.id].answers[0] = 0
        state.participants[p2.id].answers[0] = 1

        with (
            patch("pop_quiz.timers.asyncio.sleep", new_callable=AsyncMock),
            patch(
                "pop_quiz.timers.broadcast_all", new_callable=AsyncMock
            ) as mock_broadcast,
        ):
            await check_all_answered(state)

            # Should have called broadcast (at least for reveal)
            assert mock_broadcast.called
            # Phase should have advanced past QUESTION
            assert state.phase != QuizPhase.QUESTION

    async def test_does_nothing_with_no_participants(self) -> None:
        """Should not advance with no participants."""
        state = GameState.create(make_quiz())
        state.phase = QuizPhase.QUESTION

        with patch(
            "pop_quiz.timers.broadcast_all", new_callable=AsyncMock
        ) as mock_broadcast:
            await check_all_answered(state)
            mock_broadcast.assert_not_called()


@pytest.mark.asyncio
class TestScheduleQuestionTimer:
    """Tests for schedule_question_timer function."""

    async def test_creates_task(self) -> None:
        """Should create an asyncio task."""
        state = GameState.create(make_quiz())
        state.add_participant("p1")
        state.start_quiz()
        state.start_question()
        import pop_quiz.timers as timers_module

        def fake_create_task(coro: object) -> AsyncMock:
            close = getattr(coro, "close", None)
            if callable(close):
                close()
            return AsyncMock()

        try:
            with patch(
                "pop_quiz.timers.asyncio.create_task",
                side_effect=fake_create_task,
            ) as mock_create:
                await schedule_question_timer(state)
                mock_create.assert_called_once()
        finally:
            timers_module._question_timer_task = None

    async def test_cancels_previous_task(self) -> None:
        """Should cancel previous timer task."""
        state = GameState.create(make_quiz())
        state.add_participant()
        state.start_quiz()
        state.start_question()

        import pop_quiz.timers as timers_module

        # Create a real coroutine that we can cancel
        async def dummy_coro() -> None:
            await asyncio.sleep(100)

        # Set up first timer manually to avoid the create_task mock issues
        first_task = asyncio.create_task(dummy_coro())
        timers_module._question_timer_task = first_task

        # Create second timer - should cancel first
        await schedule_question_timer(state)

        # First task should have been cancelled
        assert first_task.cancelled()

        # Clean up
        if timers_module._question_timer_task:
            timers_module._question_timer_task.cancel()
            try:
                await timers_module._question_timer_task
            except asyncio.CancelledError:
                pass
