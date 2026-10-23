package com.cameradirector.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
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
import com.cameradirector.model.ShotScript
import com.cameradirector.model.formatDuration

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ScriptListScreen(
    scripts: List<ShotScript>,
    onNew: () -> Unit,
    onEdit: (ShotScript) -> Unit,
    onRun: (ShotScript) -> Unit,
    onDuplicate: (ShotScript) -> Unit,
    onDelete: (ShotScript) -> Unit,
    onRestorePresets: () -> Unit,
) {
    var pendingDelete by remember { mutableStateOf<ShotScript?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Camera Director") },
                actions = { TextButton(onClick = onRestorePresets) { Text("Add presets") } },
            )
        },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = onNew,
                icon = { Icon(Icons.Default.Add, contentDescription = null) },
                text = { Text("New script") },
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(16.dp, 8.dp, 16.dp, 96.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (scripts.isEmpty()) {
                item { Text("No scripts yet. Tap \"New script\" or \"Add presets\".") }
            }
            items(scripts, key = { it.id }) { script ->
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp)) {
                        Text(script.name, style = MaterialTheme.typography.titleMedium)
                        Text(
                            "${script.steps.size} steps · ${formatDuration(script.totalDurationMs)}",
                            style = MaterialTheme.typography.bodySmall,
                        )
                        Row(
                            Modifier.fillMaxWidth().padding(top = 8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Button(onClick = { onRun(script) }) {
                                Icon(Icons.Default.PlayArrow, contentDescription = null)
                                Spacer(Modifier.width(4.dp))
                                Text("Run")
                            }
                            Spacer(Modifier.weight(1f))
                            TextButton(onClick = { onEdit(script) }) { Text("Edit") }
                            TextButton(onClick = { onDuplicate(script) }) { Text("Copy") }
                            TextButton(onClick = { pendingDelete = script }) { Text("Delete") }
                        }
                    }
                }
            }
        }
    }

    pendingDelete?.let { script ->
        AlertDialog(
            onDismissRequest = { pendingDelete = null },
            title = { Text("Delete \"${script.name}\"?") },
            confirmButton = {
                TextButton(onClick = { onDelete(script); pendingDelete = null }) { Text("Delete") }
            },
            dismissButton = { TextButton(onClick = { pendingDelete = null }) { Text("Cancel") } },
        )
    }
}
