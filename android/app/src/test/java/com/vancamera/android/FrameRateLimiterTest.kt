package com.vancamera.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class FrameRateLimiterTest {

    @Test
    fun halvesA60FpsStreamTo30() {
        val limiter = FrameRateLimiter(30)
        val frameNs = 1_000_000_000L / 60
        val accepted = (0 until 60).count { limiter.shouldProcess(it * frameNs) }
        assertEquals(30, accepted)
    }

    @Test
    fun keepsA30FpsStreamWithJitter() {
        val limiter = FrameRateLimiter(30)
        val frameNs = 1_000_000_000L / 30
        val accepted = (0 until 30).count { i ->
            val jitter = if (i % 2 == 0) 2_000_000L else -2_000_000L
            limiter.shouldProcess(i * frameNs + jitter)
        }
        assertEquals(30, accepted)
    }

    @Test
    fun resetAcceptsNextFrame() {
        val limiter = FrameRateLimiter(30)
        assertTrue(limiter.shouldProcess(1_000))
        assertFalse(limiter.shouldProcess(2_000))
        limiter.reset()
        assertTrue(limiter.shouldProcess(3_000))
    }

    @Test
    fun fpsRangeLetsExposureStretchInLowLight() {
        val ranges = listOf(15 to 15, 7 to 30, 30 to 30, 15 to 30, 60 to 60, 30 to 60)
        assertEquals(15 to 30, FpsRangeSelector.select(ranges, 30))
    }

    @Test
    fun fpsRangeNeverDropsBelowMinimum() {
        assertEquals(30 to 30, FpsRangeSelector.select(listOf(7 to 30, 30 to 30), 30))
        assertEquals(10 to 30, FpsRangeSelector.select(listOf(7 to 30, 10 to 30), 30))
    }

    @Test
    fun fpsRangeAvoidsSixtyWhenPossible() {
        val ranges = listOf(15 to 24, 24 to 60, 30 to 120)
        assertEquals(24 to 60, FpsRangeSelector.select(ranges, 30))
    }

    @Test
    fun fpsRangeFallsBackToFastest() {
        assertEquals(15 to 24, FpsRangeSelector.select(listOf(10 to 15, 15 to 24), 30))
        assertNull(FpsRangeSelector.select(emptyList(), 30))
    }
}
