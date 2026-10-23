package com.cameradirector.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import java.util.UUID

@Serializable
enum class Easing(val label: String) {
    LINEAR("Linear"),
    SMOOTH("Smooth");

    fun apply(t: Float): Float = when (this) {
        LINEAR -> t
        SMOOTH -> t * t * (3f - 2f * t)
    }
}

/** One action in a shot script. Steps run one after another. */
@Serializable
sealed class Step {
    abstract val title: String

    /** How long the step takes to run, ignoring camera latency. */
    open val durationMs: Long get() = 0L

    @Serializable
    @SerialName("start_recording")
    data object StartRecording : Step() {
        override val title get() = "Start recording"
    }

    @Serializable
    @SerialName("stop_recording")
    data object StopRecording : Step() {
        override val title get() = "Stop recording"
    }

    @Serializable
    @SerialName("zoom")
    data class Zoom(
        val targetZoom: Float = 2f,
        val durationSec: Float = 2f,
        val easing: Easing = Easing.SMOOTH,
    ) : Step() {
        override val title get() = "Zoom to %.1fx".format(targetZoom)
        override val durationMs get() = (durationSec * 1000).toLong()
    }

    @Serializable
    @SerialName("hold")
    data class Hold(val durationSec: Float = 3f) : Step() {
        override val title get() = "Hold"
        override val durationMs get() = (durationSec * 1000).toLong()
    }

    @Serializable
    @SerialName("focus_center")
    data object FocusCenter : Step() {
        override val title get() = "Refocus (center)"
    }
}

@Serializable
data class ShotScript(
    val id: String = UUID.randomUUID().toString(),
    val name: String = "New script",
    val steps: List<Step> = listOf(Step.StartRecording, Step.Hold(5f), Step.StopRecording),
) {
    val totalDurationMs: Long get() = steps.sumOf { it.durationMs }
}

fun formatDuration(ms: Long): String {
    val totalSec = (ms + 500) / 1000
    return "%d:%02d".format(totalSec / 60, totalSec % 60)
}
