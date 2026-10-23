package com.cameradirector.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.cameradirector.model.Easing
import com.cameradirector.model.ShotScript
import com.cameradirector.model.Step
import com.cameradirector.model.formatDuration
import kotlin.math.roundToInt

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ScriptEditorScreen(
    initial: ShotScript,
    onSave: (ShotScript) -> Unit,
    onCancel: () -> Unit,
) {
    var name by remember { mutableStateOf(initial.name) }
    var steps by remember { mutableStateOf(initial.steps) }
    var addMenuOpen by remember { mutableStateOf(false) }

    fun replace(index: Int, step: Step) {
        steps = steps.toMutableList().also { it[index] = step }
    }

    fun move(from: Int, to: Int) {
        if (to !in steps.indices) return
        steps = steps.toMutableList().also { it.add(to, it.removeAt(from)) }
    }

    val warnings = validate(steps)

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Edit script") },
                navigationIcon = {
                    IconButton(onClick = onCancel) { Icon(Icons.Default.ArrowBack, contentDescription = "Back") }
                },
                actions = {
                    TextButton(onClick = { onSave(initial.copy(name = name.ifBlank { "Untitled" }, steps = steps)) }) {
                        Text("Save")
                    }
                },
            )
        },
        floatingActionButton = {
            Box {
                ExtendedFloatingActionButton(
                    onClick = { addMenuOpen = true },
                    icon = { Icon(Icons.Default.Add, contentDescription = null) },
                    text = { Text("Add step") },
                )
                DropdownMenu(expanded = addMenuOpen, onDismissRequest = { addMenuOpen = false }) {
                    listOf(
                        Step.StartRecording,
                        Step.Zoom(),
                        Step.Hold(),
                        Step.FocusCenter,
                        Step.StopRecording,
                    ).forEach { template ->
                        DropdownMenuItem(
                            text = { Text(stepTypeName(template)) },
                            onClick = { steps = steps + template; addMenuOpen = false },
                        )
                    }
                }
            }
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp, 8.dp, 16.dp, 96.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Script name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Text(
                    "Total length: ${formatDuration(steps.sumOf { it.durationMs })}",
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.padding(top = 6.dp),
                )
                warnings.forEach {
                    Text("⚠ $it", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                }
            }
            itemsIndexed(steps) { index, step ->
                StepCard(
                    index = index,
                    step = step,
                    onChange = { replace(index, it) },
                    onUp = { move(index, index - 1) },
                    onDown = { move(index, index + 1) },
                    onDelete = { steps = steps.filterIndexed { i, _ -> i != index } },
                )
            }
        }
    }
}

private fun stepTypeName(step: Step) = when (step) {
    Step.StartRecording -> "Start recording"
    Step.StopRecording -> "Stop recording"
    Step.FocusCenter -> "Refocus (center)"
    is Step.Hold -> "Hold / wait"
    is Step.Zoom -> "Zoom"
}

private fun validate(steps: List<Step>): List<String> {
    val out = mutableListOf<String>()
    if (steps.none { it == Step.StartRecording }) out += "Script never starts recording."
    var recording = false
    steps.forEach { step ->
        when (step) {
            Step.StartRecording -> if (recording) out += "Recording started twice." else recording = true
            Step.StopRecording -> recording = false
            else -> {}
        }
    }
    if (recording) out += "No Stop step at the end — recording stops automatically when the script ends."
    return out.distinct()
}

@Composable
private fun StepCard(
    index: Int,
    step: Step,
    onChange: (Step) -> Unit,
    onUp: () -> Unit,
    onDown: () -> Unit,
    onDelete: () -> Unit,
) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(start = 16.dp, end = 4.dp, top = 4.dp, bottom = 8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("${index + 1}. ${stepTypeName(step)}", style = MaterialTheme.typography.titleSmall)
                Spacer(Modifier.weight(1f))
                IconButton(onClick = onUp) { Icon(Icons.Default.KeyboardArrowUp, contentDescription = "Move up") }
                IconButton(onClick = onDown) { Icon(Icons.Default.KeyboardArrowDown, contentDescription = "Move down") }
                IconButton(onClick = onDelete) { Icon(Icons.Default.Delete, contentDescription = "Delete") }
            }
            Column(Modifier.padding(end = 12.dp)) {
                when (step) {
                    is Step.Zoom -> {
                        LabeledSlider(
                            label = "Zoom level: %.1fx".format(step.targetZoom),
                            value = step.targetZoom,
                            range = 0.5f..10f,
                            onChange = { onChange(step.copy(targetZoom = roundTo(it, 0.1f))) },
                        )
                        LabeledSlider(
                            label = "Zoom duration: %.1f s".format(step.durationSec),
                            value = step.durationSec,
                            range = 0f..30f,
                            onChange = { onChange(step.copy(durationSec = roundTo(it, 0.1f))) },
                        )
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Easing.entries.forEach { e ->
                                FilterChip(
                                    selected = step.easing == e,
                                    onClick = { onChange(step.copy(easing = e)) },
                                    label = { Text(e.label) },
                                )
                            }
                        }
                        Text(
                            "Levels outside your camera's range are clamped when the script runs.",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                    is Step.Hold -> LabeledSlider(
                        label = "Wait: %.1f s".format(step.durationSec),
                        value = step.durationSec,
                        range = 0.5f..300f,
                        onChange = { onChange(step.copy(durationSec = roundTo(it, if (it < 10f) 0.5f else 1f))) },
                    )
                    Step.FocusCenter -> Text("Re-runs autofocus and exposure on the centre of the frame.", style = MaterialTheme.typography.bodySmall)
                    Step.StartRecording, Step.StopRecording -> {}
                }
            }
        }
    }
}

@Composable
private fun LabeledSlider(label: String, value: Float, range: ClosedFloatingPointRange<Float>, onChange: (Float) -> Unit) {
    Text(label, style = MaterialTheme.typography.bodyMedium)
    Slider(value = value.coerceIn(range), onValueChange = onChange, valueRange = range)
}

private fun roundTo(value: Float, step: Float): Float = (value / step).roundToInt() * step
