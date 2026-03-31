"""
Tests for app.utils.random_utils module.
"""

import asyncio
import pytest

from app.utils.random import (
    random_delay_ms,
    random_int_range,
    random_float_range,
    random_drift,
    random_drift_2d,
    should_trigger,
    sleep_ms,
    sleep_with_backoff,
    RandomizedScheduler,
    ProbabilisticExecutor,
)


class TestRandomDelayMs:
    """Test cases for random_delay_ms function."""

    def test_base_only(self):
        """Test delay with only base value."""
        delay = random_delay_ms(base_ms=100, max_additional_ms=0)
        assert delay == 100
    
    def test_with_additional(self):
        """Test delay with additional range."""
        for _ in range(100):  # Run multiple times to cover randomness
            delay = random_delay_ms(base_ms=100, max_additional_ms=50)
            assert 100 <= delay <= 150
    
    def test_intensity_scaling(self):
        """Test that intensity scales the additional delay."""
        # With intensity=0, should always return base
        delay = random_delay_ms(base_ms=100, max_additional_ms=100, intensity=0)
        assert delay == 100
        
        # With intensity=0.5, should be between base and base + 50% of additional
        for _ in range(50):
            delay = random_delay_ms(base_ms=100, max_additional_ms=100, intensity=0.5)
            assert 100 <= delay <= 150
    
    def test_zero_base(self):
        """Test with zero base delay."""
        delay = random_delay_ms(base_ms=0, max_additional_ms=100)
        assert 0 <= delay <= 100


class TestRandomIntRange:
    """Test cases for random_int_range function."""

    def test_base_only(self):
        """Test with only base value."""
        value = random_int_range(base=5, max_additional=0)
        assert value == 5
    
    def test_within_range(self):
        """Test value is within expected range."""
        for _ in range(100):
            value = random_int_range(base=1, max_additional=4)
            assert 1 <= value <= 5
    
    def test_intensity_effect(self):
        """Test intensity affects range."""
        # With intensity=0.5 and max_additional=10, max should be 5
        for _ in range(50):
            value = random_int_range(base=0, max_additional=10, intensity=0.5)
            assert 0 <= value <= 5


class TestRandomFloatRange:
    """Test cases for random_float_range function."""

    def test_within_bounds(self):
        """Test float is within bounds."""
        for _ in range(100):
            value = random_float_range(-10, 10)
            assert -10 <= value <= 10
    
    def test_same_bounds(self):
        """Test with identical bounds."""
        value = random_float_range(5, 5)
        assert value == 5


class TestRandomDrift:
    """Test cases for random_drift function."""

    def test_symmetric_range(self):
        """Test drift is symmetric around 0."""
        for _ in range(100):
            drift = random_drift(max_drift=50)
            assert -50 <= drift <= 50
    
    def test_intensity_zero(self):
        """Test zero intensity returns 0."""
        drift = random_drift(max_drift=50, intensity=0)
        assert drift == 0
    
    def test_scaled_by_intensity(self):
        """Test drift scales with intensity."""
        for _ in range(50):
            drift = random_drift(max_drift=100, intensity=0.3)
            assert -30 <= drift <= 30


class TestRandomDrift2D:
    """Test cases for random_drift_2d function."""

    def test_returns_tuple(self):
        """Test returns 2-element tuple."""
        dx, dy = random_drift_2d(50)
        assert isinstance(dx, int)
        assert isinstance(dy, int)
    
    def test_bounds(self):
        """Test both drifts are within bounds."""
        for _ in range(50):
            dx, dy = random_drift_2d(50, intensity=1.0)
            assert -50 <= dx <= 50
            assert -50 <= dy <= 50
    
    def test_independent_values(self):
        """Test x and y are independent."""
        # Run many times to ensure independence
        values = [random_drift_2d(100) for _ in range(100)]
        # Check that we get variety in both dimensions
        x_values = [v[0] for v in values]
        y_values = [v[1] for v in values]
        assert len(set(x_values)) > 10  # Should have variety
        assert len(set(y_values)) > 10


class TestShouldTrigger:
    """Test cases for should_trigger function."""

    def test_probability_one(self):
        """Test probability of 1 always triggers."""
        for _ in range(100):
            assert should_trigger(1.0) is True
    
    def test_probability_zero(self):
        """Test probability of 0 never triggers."""
        for _ in range(100):
            assert should_trigger(0.0) is False
    
    def test_probability_distribution(self):
        """Test approximate probability distribution."""
        triggers = sum(should_trigger(0.5) for _ in range(1000))
        # Should be roughly 500, but allow for randomness (400-600)
        assert 400 <= triggers <= 600
    
    def test_intensity_affects_probability(self):
        """Test intensity scales probability."""
        # With probability=0.5 and intensity=0, should never trigger
        for _ in range(50):
            assert should_trigger(0.5, intensity=0) is False
        
        # With probability=0.5 and intensity=2, should cap at 1.0
        triggers = sum(should_trigger(0.6, intensity=2.0) for _ in range(100))
        assert triggers == 100  # Always triggers with effective prob 1.0


class TestSleepMs:
    """Test cases for sleep_ms function."""

    @pytest.mark.asyncio
    async def test_basic_sleep(self):
        """Test basic async sleep."""
        import time
        start = time.time()
        await sleep_ms(100)  # 100ms
        elapsed = (time.time() - start) * 1000
        assert elapsed >= 90  # Allow some tolerance
    
    @pytest.mark.asyncio
    async def test_sleep_with_jitter(self):
        """Test sleep with jitter adds randomness."""
        times = []
        for _ in range(10):
            import time
            start = time.time()
            await sleep_ms(50, jitter_ms=50)
            elapsed = (time.time() - start) * 1000
            times.append(elapsed)
        
        # Should have some variation due to jitter
        assert max(times) > min(times)
        # All should be at least the base time
        assert all(t >= 40 for t in times)
    
    @pytest.mark.asyncio
    async def test_zero_delay(self):
        """Test zero delay returns immediately."""
        import time
        start = time.time()
        await sleep_ms(0)
        elapsed = (time.time() - start) * 1000
        assert elapsed < 50  # Should be nearly instant


class TestSleepWithBackoff:
    """Test cases for sleep_with_backoff function."""

    @pytest.mark.asyncio
    async def test_backoff_increases(self):
        """Test that backoff increases with attempt number."""
        import time
        
        # First attempt
        start = time.time()
        await sleep_with_backoff(0, base_delay_ms=100)
        first_duration = (time.time() - start) * 1000
        
        # Second attempt
        start = time.time()
        await sleep_with_backoff(1, base_delay_ms=100)
        second_duration = (time.time() - start) * 1000
        
        # Second should take longer
        assert second_duration > first_duration
    
    @pytest.mark.asyncio
    async def test_max_delay_cap(self):
        """Test max delay is respected."""
        import time
        start = time.time()
        await sleep_with_backoff(10, base_delay_ms=1000, max_delay_ms=200)
        elapsed = (time.time() - start) * 1000
        
        # Should not exceed max_delay by much (allowing jitter)
        assert elapsed < 400


class TestRandomizedScheduler:
    """Test cases for RandomizedScheduler class."""

    def test_delay_within_range(self):
        """Test scheduler produces delays within range."""
        scheduler = RandomizedScheduler(base_delay_ms=100, variance_ms=50)
        
        for _ in range(100):
            delay = scheduler.next_delay()
            assert 100 <= delay <= 150
    
    def test_zero_variance(self):
        """Test scheduler with zero variance."""
        scheduler = RandomizedScheduler(base_delay_ms=100, variance_ms=0)
        
        for _ in range(10):
            assert scheduler.next_delay() == 100
    
    @pytest.mark.asyncio
    async def test_sleep_method(self):
        """Test sleep method works."""
        scheduler = RandomizedScheduler(base_delay_ms=50, variance_ms=0)
        
        import time
        start = time.time()
        await scheduler.sleep()
        elapsed = (time.time() - start) * 1000
        
        assert elapsed >= 40  # Allow tolerance


class TestProbabilisticExecutor:
    """Test cases for ProbabilisticExecutor class."""

    def test_register_and_execute(self):
        """Test registering and executing actions."""
        executor = ProbabilisticExecutor()
        results = []
        
        def action1():
            results.append("action1")
        
        def action2():
            results.append("action2")
        
        executor.register("a1", action1, probability=1)
        executor.register("a2", action2, probability=0)  # Never triggers
        
        # Execute multiple times
        for _ in range(10):
            executor.execute_one()
        
        # Only action1 should have executed
        assert all(r == "action1" for r in results)
    
    def test_should_execute(self):
        """Test should_execute method."""
        executor = ProbabilisticExecutor()
        executor.register("always", lambda: None, probability=1.0)
        executor.register("never", lambda: None, probability=0.0)
        
        for _ in range(10):
            assert executor.should_execute("always") is True
            assert executor.should_execute("never") is False
    
    def test_should_execute_unknown(self):
        """Test should_execute with unknown action."""
        executor = ProbabilisticExecutor()
        assert executor.should_execute("unknown") is False
    
    def test_empty_executor(self):
        """Test execute_one with no actions."""
        executor = ProbabilisticExecutor()
        result = executor.execute_one()
        assert result is False
