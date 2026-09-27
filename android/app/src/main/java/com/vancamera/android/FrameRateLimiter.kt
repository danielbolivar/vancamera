package com.vancamera.android

/**
 * Drops camera frames that arrive faster than [targetFps].
 *
 * Some devices deliver 60 fps to ImageAnalysis even when we asked for 30; converting and encoding
 * frames that the PC does not need is wasted battery and heat.
 */
class FrameRateLimiter(targetFps: Int) {

    private val intervalNs = 1_000_000_000L / targetFps

    // Frames may arrive up to a quarter interval early (camera timestamp jitter) and still count
    // as the next frame; anything earlier is an "extra" frame from a faster sensor.
    private val toleranceNs = intervalNs / 4
    private var nextDueNs = Long.MIN_VALUE

    fun shouldProcess(timestampNs: Long): Boolean {
        if (nextDueNs == Long.MIN_VALUE || timestampNs - nextDueNs > intervalNs || timestampNs < nextDueNs - 4 * intervalNs) {
            // First frame, a long gap, or timestamps going backwards: resynchronize.
            nextDueNs = timestampNs + intervalNs
            return true
        }
        if (timestampNs < nextDueNs - toleranceNs) return false
        nextDueNs += intervalNs
        return true
    }

    fun reset() {
        nextDueNs = Long.MIN_VALUE
    }
}

/**
 * Picks the camera auto-exposure FPS range to request.
 *
 * Prefers a range whose upper bound equals the target (so the sensor never runs at 60 fps and
 * heats the phone). Among those it takes the lowest lower bound that is still at least
 * [MIN_FPS]: a fixed 30-30 range caps exposure at 1/30 s, which makes indoor and evening video
 * dark and noisy, while 15-30 lets the camera expose longer in low light like a real webcam.
 */
object FpsRangeSelector {
    const val MIN_FPS = 15

    fun select(ranges: List<Pair<Int, Int>>, targetFps: Int): Pair<Int, Int>? {
        if (ranges.isEmpty()) return null
        val exact = ranges.filter { it.second == targetFps }
        if (exact.isNotEmpty()) {
            return exact.filter { it.first >= MIN_FPS }.minByOrNull { it.first }
                ?: exact.maxByOrNull { it.first }
        }
        // Otherwise the smallest upper bound that still reaches the target...
        val above = ranges.filter { it.second > targetFps }
        if (above.isNotEmpty()) {
            val minUpper = above.minOf { it.second }
            return above.filter { it.second == minUpper }.maxByOrNull { it.first }
        }
        // ...or the fastest range available.
        val maxUpper = ranges.maxOf { it.second }
        return ranges.filter { it.second == maxUpper }.maxByOrNull { it.first }
    }
}
