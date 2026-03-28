package com.shieldtube.phone.ui.components

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Fill
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import com.shieldtube.phone.data.api.VideoItem

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun VideoCard(
    video: VideoItem,
    baseUrl: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    onDownloadToPhone: ((VideoItem) -> Unit)? = null,
    onDownloadToServer: ((VideoItem) -> Unit)? = null,
) {
    var menuExpanded by remember { mutableStateOf(false) }
    val hasActions = onDownloadToPhone != null || onDownloadToServer != null

    Box(modifier = modifier) {
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .combinedClickable(
                    onClick = onClick,
                    onLongClick = {
                        if (hasActions) menuExpanded = true
                    },
                ),
            shape = RoundedCornerShape(8.dp),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surface,
            ),
            elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        ) {
            Column {
                Box {
                    AsyncImage(
                        model = "$baseUrl/api/video/${video.id}/thumbnail?res=maxres",
                        contentDescription = video.title,
                        contentScale = ContentScale.Crop,
                        modifier = Modifier
                            .fillMaxWidth()
                            .aspectRatio(16f / 9f),
                    )
                    // Download button (top-right of thumbnail)
                    if (hasActions) {
                        IconButton(
                            onClick = { menuExpanded = true },
                            modifier = Modifier
                                .align(Alignment.TopEnd)
                                .padding(4.dp)
                                .size(28.dp)
                                .clip(CircleShape)
                                .background(Color.Black.copy(alpha = 0.6f)),
                        ) {
                            androidx.compose.foundation.Canvas(
                                modifier = Modifier.size(14.dp)
                            ) {
                                val w = size.width
                                val h = size.height
                                // Down arrow
                                drawPath(
                                    path = Path().apply {
                                        moveTo(w * 0.5f, h * 0.05f)
                                        lineTo(w * 0.5f, h * 0.6f)
                                        moveTo(w * 0.2f, h * 0.4f)
                                        lineTo(w * 0.5f, h * 0.7f)
                                        lineTo(w * 0.8f, h * 0.4f)
                                    },
                                    color = Color.White,
                                    style = androidx.compose.ui.graphics.drawscope.Stroke(width = 2f),
                                )
                                // Bottom bar
                                drawRect(
                                    color = Color.White,
                                    topLeft = androidx.compose.ui.geometry.Offset(w * 0.2f, h * 0.85f),
                                    size = androidx.compose.ui.geometry.Size(w * 0.6f, h * 0.08f),
                                )
                            }
                        }
                    }

                    video.duration?.let { duration ->
                        val formatted = formatDuration(duration)
                        if (formatted.isNotBlank()) {
                            Text(
                                text = formatted,
                                color = Color.White,
                                fontSize = 11.sp,
                                modifier = Modifier
                                    .align(Alignment.BottomEnd)
                                    .padding(4.dp)
                                    .background(
                                        color = Color.Black.copy(alpha = 0.75f),
                                        shape = RoundedCornerShape(3.dp),
                                    )
                                    .padding(horizontal = 4.dp, vertical = 2.dp),
                            )
                        }
                    }
                }
                Column(modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp)) {
                    Text(
                        text = video.title,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurface,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        text = video.channelName,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.padding(top = 2.dp),
                    )
                }
            }
        }

        if (hasActions) {
            DropdownMenu(
                expanded = menuExpanded,
                onDismissRequest = { menuExpanded = false },
            ) {
                DropdownMenuItem(
                    text = { Text("Play") },
                    onClick = {
                        menuExpanded = false
                        onClick()
                    },
                )
                if (onDownloadToPhone != null) {
                    DropdownMenuItem(
                        text = { Text("Download to Phone") },
                        onClick = {
                            menuExpanded = false
                            onDownloadToPhone(video)
                        },
                    )
                }
                if (onDownloadToServer != null) {
                    DropdownMenuItem(
                        text = { Text("Download to Server") },
                        onClick = {
                            menuExpanded = false
                            onDownloadToServer(video)
                        },
                    )
                }
            }
        }
    }
}

/**
 * Formats an ISO 8601 duration (PT1H2M3S) or plain seconds string
 * into H:MM:SS or M:SS display format.
 */
private fun formatDuration(raw: String): String {
    return try {
        // Try to parse total seconds as integer first (e.g. "3723")
        val totalSeconds = raw.trim().toLongOrNull()
            ?: parseIso8601Duration(raw)
        if (totalSeconds < 0) return ""
        val hours = totalSeconds / 3600
        val minutes = (totalSeconds % 3600) / 60
        val seconds = totalSeconds % 60
        if (hours > 0) {
            "%d:%02d:%02d".format(hours, minutes, seconds)
        } else {
            "%d:%02d".format(minutes, seconds)
        }
    } catch (e: Exception) {
        ""
    }
}

private fun parseIso8601Duration(iso: String): Long {
    val upper = iso.uppercase()
    if (!upper.startsWith("PT")) return -1
    val part = upper.removePrefix("PT")
    var totalSeconds = 0L
    var current = ""
    for (ch in part) {
        when {
            ch.isDigit() -> current += ch
            ch == 'H' -> { totalSeconds += (current.toLongOrNull() ?: 0L) * 3600; current = "" }
            ch == 'M' -> { totalSeconds += (current.toLongOrNull() ?: 0L) * 60; current = "" }
            ch == 'S' -> { totalSeconds += current.toLongOrNull() ?: 0L; current = "" }
        }
    }
    return totalSeconds
}
