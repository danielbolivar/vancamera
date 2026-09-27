package com.vancamera.android

import org.junit.Assert.assertEquals
import org.junit.Test

class StreamQualityTest {

    @Test
    fun unknownOrMissingPreferenceFallsBackToDefault() {
        assertEquals(StreamQuality.HD_30, StreamQuality.fromName(null))
        assertEquals(StreamQuality.HD_30, StreamQuality.fromName("ULTRA_4K"))
        assertEquals(StreamQuality.FHD_30, StreamQuality.fromName("FHD_30"))
    }

    @Test
    fun sixtyFpsOnlyOfferedWhenTheCameraCanDoIt() {
        assertEquals(listOf(StreamQuality.HD_30, StreamQuality.FHD_30), StreamQuality.available(30))
        assertEquals(StreamQuality.entries, StreamQuality.available(60))
    }
}
