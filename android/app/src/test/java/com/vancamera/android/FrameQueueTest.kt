package com.vancamera.android

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import kotlin.concurrent.thread

class FrameQueueTest {

    private fun packet(id: Int) = byteArrayOf(id.toByte())

    @Test
    fun deliversInOrder() {
        val q = FrameQueue(maxFrames = 4)
        repeat(3) { assertEquals(FrameQueue.OfferResult.QUEUED, q.offer(packet(it), it == 0)) }
        repeat(3) { assertArrayEquals(packet(it), q.poll(10)) }
        assertNull(q.poll(10))
    }

    @Test
    fun overflowFlushesAndWaitsForKeyFrame() {
        val q = FrameQueue(maxFrames = 3)
        q.offer(packet(0), true)
        q.offer(packet(1), false)
        q.offer(packet(2), false)
        // Queue full: the next delta frame flushes everything and asks for a keyframe.
        assertEquals(FrameQueue.OfferResult.DROPPED_NEED_KEYFRAME, q.offer(packet(3), false))
        assertEquals(0, q.size)
        // Delta frames are useless until the next keyframe.
        assertEquals(FrameQueue.OfferResult.DROPPED, q.offer(packet(4), false))
        assertEquals(FrameQueue.OfferResult.QUEUED, q.offer(packet(5), true))
        assertEquals(FrameQueue.OfferResult.QUEUED, q.offer(packet(6), false))
        assertArrayEquals(packet(5), q.poll(10))
        assertArrayEquals(packet(6), q.poll(10))
        assertEquals(5L, q.droppedFrames)
    }

    @Test
    fun keyFrameOnFullQueueReplacesBacklog() {
        val q = FrameQueue(maxFrames = 2)
        q.offer(packet(0), true)
        q.offer(packet(1), false)
        assertEquals(FrameQueue.OfferResult.QUEUED, q.offer(packet(2), true))
        assertEquals(1, q.size)
        assertArrayEquals(packet(2), q.poll(10))
    }

    @Test
    fun closeWakesUpWaitingConsumer() {
        val q = FrameQueue()
        var result: ByteArray? = byteArrayOf()
        val consumer = thread { result = q.poll(5_000) }
        Thread.sleep(50)
        q.close()
        consumer.join(1_000)
        assertNull(result)
        assertEquals(FrameQueue.OfferResult.DROPPED, q.offer(packet(1), true))
    }
}
