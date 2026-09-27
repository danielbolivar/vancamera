package com.vancamera.android

import android.content.Context
import android.util.Size
import androidx.core.content.edit

/**
 * Stream presets the user picks on each phone (saved on the phone, so every device keeps its
 * own). The PC adapts to whatever it receives, including the virtual camera size and rate.
 */
enum class StreamQuality(val width: Int, val height: Int, val fps: Int, val bitrate: Int) {
    /** Default: enough for video calls (they send 30 fps at most), coolest for the phone. */
    HD_30(1280, 720, 30, 6_000_000),

    /** Sharper image, more heat. */
    FHD_30(1920, 1080, 30, 10_000_000),

    /** Smooth motion for OBS / recordings; only offered if the camera can run at 60 fps. */
    HD_60(1280, 720, 60, 10_000_000);

    val size: Size get() = Size(width, height)

    val label: String get() = "${height}p · $fps fps"

    companion object {
        val DEFAULT = HD_30

        private const val PREFS = "vancamera"
        private const val KEY = "stream_quality"

        fun fromName(name: String?): StreamQuality = entries.firstOrNull { it.name == name } ?: DEFAULT

        /** Presets this camera can deliver, given its maximum auto-exposure frame rate. */
        fun available(maxCameraFps: Int): List<StreamQuality> = entries.filter { it.fps <= maxCameraFps }

        fun load(context: Context): StreamQuality =
            fromName(context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY, null))

        fun save(context: Context, quality: StreamQuality) {
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putString(KEY, quality.name) }
        }
    }
}
