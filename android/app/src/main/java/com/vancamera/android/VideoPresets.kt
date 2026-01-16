package com.vancamera.android

/**
 * Presets predefinidos de configuración de video
 */
enum class VideoPreset {
    PRESET_720P_30FPS,
    PRESET_720P_60FPS,
    PRESET_1080P_30FPS,
    PRESET_1080P_60FPS,
    CUSTOM
}

/**
 * Utilidades para trabajar con presets de video
 */
object VideoPresetHelper {
    /**
     * Obtiene el nombre legible del preset
     */
    fun getDisplayName(preset: VideoPreset): String {
        return when (preset) {
            VideoPreset.PRESET_720P_30FPS -> "720p @ 30fps"
            VideoPreset.PRESET_720P_60FPS -> "720p @ 60fps"
            VideoPreset.PRESET_1080P_30FPS -> "1080p @ 30fps"
            VideoPreset.PRESET_1080P_60FPS -> "1080p @ 60fps"
            VideoPreset.CUSTOM -> "Personalizado"
        }
    }

    /**
     * Obtiene la descripción del preset
     */
    fun getDescription(preset: VideoPreset): String {
        return when (preset) {
            VideoPreset.PRESET_720P_30FPS -> "Balance calidad/rendimiento (recomendado para WiFi)"
            VideoPreset.PRESET_720P_60FPS -> "Más fluido, requiere buena conexión"
            VideoPreset.PRESET_1080P_30FPS -> "Máxima calidad, requiere conexión estable"
            VideoPreset.PRESET_1080P_60FPS -> "Máxima calidad y fluidez, requiere conexión excelente"
            VideoPreset.CUSTOM -> "Configuración personalizada"
        }
    }

    /**
     * Lista de presets disponibles (excluyendo CUSTOM)
     */
    fun getAvailablePresets(): List<VideoPreset> {
        return listOf(
            VideoPreset.PRESET_720P_30FPS,
            VideoPreset.PRESET_720P_60FPS,
            VideoPreset.PRESET_1080P_30FPS,
            VideoPreset.PRESET_1080P_60FPS
        )
    }
}
