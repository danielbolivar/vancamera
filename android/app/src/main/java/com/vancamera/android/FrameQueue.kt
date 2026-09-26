package com.vancamera.android

import java.util.ArrayDeque
import java.util.concurrent.TimeUnit
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock

/**
 * Bounded, latency-aware queue between the encoder and the network sender.
 *
 * When the network cannot keep up (weak Wi-Fi, congested network) the old implementation launched
 * one coroutine per frame; they piled up, wrote concurrently to the same socket (corrupting the
 * stream) and the video froze. Here, instead:
 *
 * - at most [maxFrames] frames wait to be sent (≈ maxFrames / fps seconds of extra latency);
 * - on overflow every queued frame is dropped and the queue waits for the next keyframe, because
 *   predicted frames are useless without the frames they reference;
 * - the caller is told a keyframe is needed so the encoder can produce one right away.
 */
class FrameQueue(private val maxFrames: Int = DEFAULT_MAX_FRAMES) {

    enum class OfferResult {
        QUEUED,
        /** Dropped because we are waiting for a keyframe after an earlier overflow. */
        DROPPED,
        /** Overflow: queue flushed; the encoder should emit a keyframe as soon as possible. */
        DROPPED_NEED_KEYFRAME
    }

    private val lock = ReentrantLock()
    private val notEmpty = lock.newCondition()
    private val frames = ArrayDeque<ByteArray>()
    private var waitingForKeyFrame = false
    private var closed = false

    var droppedFrames: Long = 0
        private set

    fun offer(packet: ByteArray, isKeyFrame: Boolean): OfferResult = lock.withLock {
        if (closed) return OfferResult.DROPPED

        if (waitingForKeyFrame && !isKeyFrame) {
            droppedFrames++
            return OfferResult.DROPPED
        }

        if (frames.size >= maxFrames) {
            droppedFrames += frames.size
            frames.clear()
            if (!isKeyFrame) {
                droppedFrames++
                waitingForKeyFrame = true
                return OfferResult.DROPPED_NEED_KEYFRAME
            }
        }

        if (isKeyFrame) waitingForKeyFrame = false
        frames.addLast(packet)
        notEmpty.signal()
        OfferResult.QUEUED
    }

    /** Waits up to [timeoutMs] for a frame. Returns null on timeout or when closed. */
    fun poll(timeoutMs: Long): ByteArray? = lock.withLock {
        var remaining = TimeUnit.MILLISECONDS.toNanos(timeoutMs)
        while (frames.isEmpty() && !closed) {
            if (remaining <= 0) return null
            remaining = notEmpty.awaitNanos(remaining)
        }
        frames.pollFirst()
    }

    val size: Int get() = lock.withLock { frames.size }

    fun close() = lock.withLock {
        closed = true
        frames.clear()
        notEmpty.signalAll()
    }

    companion object {
        /** ~200 ms at 30 fps. */
        const val DEFAULT_MAX_FRAMES = 6
    }
}
