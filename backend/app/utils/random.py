"""
Random utilities for delays, jitter, and probabilistic operations.

This module provides tools for adding randomness to operations,
useful for rate limiting, backoff strategies, and simulation.
"""

import asyncio
import logging
import random
from collections.abc import Callable

logger = logging.getLogger(__name__)


def random_delay_ms(base_ms: int = 0, max_additional_ms: int = 1000, intensity: float = 1.0) -> int:
    """
    Calculate a random delay in milliseconds.

    Args:
        base_ms: Base delay in milliseconds
        max_additional_ms: Maximum additional random delay
        intensity: Intensity multiplier (0.0 to 1.0+) for the random component

    Returns:
        Total delay in milliseconds

    Example:
        >>> # Base 500ms + up to 1000ms random
        >>> delay = random_delay_ms(500, 1000)
        >>> # With 50% intensity: base 500ms + up to 500ms random
        >>> delay = random_delay_ms(500, 1000, intensity=0.5)
    """
    additional = int(max_additional_ms * intensity)
    if additional > 0:
        return base_ms + random.randint(0, additional)
    return base_ms


def random_int_range(base: int = 0, max_additional: int = 10, intensity: float = 1.0) -> int:
    """
    Generate a random integer with base and intensity-controlled variance.

    Args:
        base: Base value
        max_additional: Maximum additional random value
        intensity: Intensity multiplier for the random component

    Returns:
        Random integer

    Example:
        >>> # Base 1 retry + 0-4 additional based on intensity
        >>> retries = random_int_range(1, 4, intensity=0.5)
    """
    additional = int(max_additional * intensity)
    if additional > 0:
        return base + random.randint(0, additional)
    return base


def random_float_range(min_val: float, max_val: float) -> float:
    """
    Generate a random float within a range.

    Args:
        min_val: Minimum value
        max_val: Maximum value

    Returns:
        Random float between min_val and max_val

    Example:
        >>> jitter = random_float_range(-50, 50)
    """
    return random.uniform(min_val, max_val)


def random_drift(max_drift: int, intensity: float = 1.0) -> int:
    """
    Generate a random drift value (positive or negative).

    Useful for adding slight randomness to coordinates or positions.

    Args:
        max_drift: Maximum drift amount (will be scaled by intensity)
        intensity: Intensity multiplier (0.0 to 1.0+)

    Returns:
        Random integer between -max_drift and +max_drift (scaled by intensity)

    Example:
        >>> # Add random drift to coordinates
        >>> drift_x = random_drift(50, intensity=0.3)
        >>> drift_y = random_drift(50, intensity=0.3)
        >>> new_x = base_x + drift_x
        >>> new_y = base_y + drift_y
    """
    scaled_max = int(max_drift * intensity)
    if scaled_max <= 0:
        return 0
    return random.randint(-scaled_max, scaled_max)


def random_drift_2d(max_drift: int, intensity: float = 1.0) -> tuple[int, int]:
    """
    Generate 2D random drift (x, y).

    Args:
        max_drift: Maximum drift amount for each axis
        intensity: Intensity multiplier

    Returns:
        Tuple of (drift_x, drift_y)

    Example:
        >>> dx, dy = random_drift_2d(50, intensity=0.3)
    """
    return (random_drift(max_drift, intensity), random_drift(max_drift, intensity))


def should_trigger(probability: float, intensity: float = 1.0) -> bool:
    """
    Determine if a probabilistic event should trigger.

    Args:
        probability: Base probability (0.0 to 1.0)
        intensity: Intensity multiplier for the probability

    Returns:
        True if the event should trigger

    Example:
        >>> # 30% chance to apply a modifier
        >>> if should_trigger(0.3):
        ...     apply_modifier()

        >>> # With intensity: 30% * 0.5 = 15% chance
        >>> if should_trigger(0.3, intensity=0.5):
        ...     apply_modifier()
    """
    effective_probability = min(1.0, probability * intensity)
    return random.random() < effective_probability


async def sleep_ms(
    delay_ms: int, jitter_ms: int = 0, jitter_intensity: float = 1.0
) -> None:
    """
    Async sleep with optional jitter.

    Args:
        delay_ms: Base delay in milliseconds
        jitter_ms: Maximum additional random jitter
        jitter_intensity: Intensity for jitter

    Example:
        >>> # Sleep 1000ms
        >>> await sleep_ms(1000)

        >>> # Sleep 1000ms + up to 500ms jitter
        >>> await sleep_ms(1000, jitter_ms=500)
    """
    total_delay = delay_ms
    if jitter_ms > 0:
        total_delay += int(jitter_ms * jitter_intensity * random.random())

    if total_delay > 0:
        await asyncio.sleep(total_delay / 1000.0)


async def sleep_with_backoff(
    attempt: int,
    base_delay_ms: float = 1000.0,
    max_delay_ms: float = 30000.0,
    factor: float = 2.0,
    jitter_factor: float = 0.1,
) -> None:
    """
    Sleep with exponential backoff.

    Args:
        attempt: Current attempt number (0-indexed)
        base_delay_ms: Initial delay in milliseconds
        max_delay_ms: Maximum delay cap
        factor: Exponential growth factor
        jitter_factor: Jitter as fraction of delay (0.0 to 1.0)

    Example:
        >>> for attempt in range(max_retries):
        ...     try:
        ...         result = await do_request()
        ...         break
        ...     except NetworkError:
        ...         await sleep_with_backoff(attempt)
    """
    # Calculate exponential delay
    delay = min(base_delay_ms * (factor**attempt), max_delay_ms)

    # Add jitter
    if jitter_factor > 0:
        jitter = delay * jitter_factor * (2 * random.random() - 1)
        delay = max(0, delay + jitter)

    await asyncio.sleep(delay / 1000.0)


class RandomizedScheduler:
    """
    A scheduler that adds randomness to timing operations.

    Useful for simulating human-like behavior or preventing thundering herd.

    Example:
        >>> scheduler = RandomizedScheduler(base_delay_ms=1000, variance_ms=500)
        >>>
        >>> # Get next delay (1000ms ± 500ms)
        >>> delay = scheduler.next_delay()
        >>>
        >>> # Sleep for the randomized duration
        >>> await scheduler.sleep()
    """

    def __init__(self, base_delay_ms: int = 1000, variance_ms: int = 0, intensity: float = 1.0):
        """
        Initialize scheduler.

        Args:
            base_delay_ms: Base delay in milliseconds
            variance_ms: Maximum random variance
            intensity: Intensity multiplier for variance
        """
        self.base_delay_ms = base_delay_ms
        self.variance_ms = variance_ms
        self.intensity = intensity

    def next_delay(self) -> int:
        """Calculate next randomized delay in milliseconds."""
        return random_delay_ms(self.base_delay_ms, self.variance_ms, self.intensity)

    async def sleep(self) -> None:
        """Sleep for the next randomized duration."""
        await sleep_ms(self.next_delay())


class ProbabilisticExecutor:
    """
    Execute actions based on probability.

    Example:
        >>> executor = ProbabilisticExecutor()
        >>>
        >>> # Register actions with probabilities
        >>> executor.register("rare", lambda: print("Rare!"), probability=0.1)
        >>> executor.register("common", lambda: print("Common"), probability=0.9)
        >>>
        >>> # Execute one action based on probabilities
        >>> executor.execute_one()
    """

    def __init__(self):
        self._actions: list[tuple[str, Callable, float]] = []

    def register(self, name: str, action: Callable, probability: float) -> None:
        """
        Register an action with a probability.

        Args:
            name: Action identifier
            action: Callable to execute
            probability: Probability weight (relative to others)
        """
        self._actions.append((name, action, probability))

    def execute_one(self) -> bool:
        """
        Execute one action based on registered probabilities.

        Returns:
            True if an action was executed
        """
        if not self._actions:
            return False

        total_weight = sum(weight for _, _, weight in self._actions)
        if total_weight <= 0:
            return False

        # Random selection based on weights
        r = random.uniform(0, total_weight)
        cumulative = 0.0

        for name, action, weight in self._actions:
            cumulative += weight
            if r <= cumulative:
                action()
                return True

        # Fallback to last action
        self._actions[-1][1]()
        return True

    def should_execute(self, name: str, intensity: float = 1.0) -> bool:
        """
        Check if a specific action should execute based on its probability.

        Args:
            name: Action name
            intensity: Intensity multiplier

        Returns:
            True if action should execute
        """
        for action_name, _, probability in self._actions:
            if action_name == name:
                return should_trigger(probability, intensity)
        return False
