package com.vancamera.android

import android.os.Parcelable
import android.util.Size
import kotlinx.parcelize.Parcelize

/**
 * Configuración de parámetros de video para captura y codificación
 */
@Parcelize
data class VideoConfig(
    val width: Int,
    val height: Int,
    val fps: Int,
    val bitrate: Int, // en bps
    val iFrameInterval: Int = 1 // intervalo de frames I (1 = cada segundo)
) : Parcelable {
    val resolution: Size
        get() = Size(width, height)

    val resolutionString: String
        get() = "${width}x${height}"

    companion object {
        fun fromPreset(preset: VideoPreset): VideoConfig {
            return when (preset) {
                VideoPreset.PRESET_720P_30FPS -> VideoConfig(
                    width = 1280,
                    height = 720,
                    fps = 30,
                    bitrate = 2_000_000 // 2 Mbps
                )
                VideoPreset.PRESET_720P_60FPS -> VideoConfig(
                    width = 1280,
                    height = 720,
                    fps = 60,
                    bitrate = 4_000_000 // 4 Mbps
                )
                VideoPreset.PRESET_1080P_30FPS -> VideoConfig(
                    width = 1920,
                    height = 1080,
                    fps = 30,
                    bitrate = 4_000_000 // 4 Mbps
                )
                VideoPreset.PRESET_1080P_60FPS -> VideoConfig(
                    width = 1920,
                    height = 1080,
                    fps = 60,
                    bitrate = 8_000_000 // 8 Mbps
                )
                VideoPreset.CUSTOM -> throw IllegalArgumentException("CUSTOM preset requires explicit configuration")
            }
        }
    }
}
