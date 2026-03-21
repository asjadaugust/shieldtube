package com.shieldtube.phone.ui.downloads

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.shieldtube.phone.data.api.ActiveDownload
import com.shieldtube.phone.data.api.LibraryVideo
import com.shieldtube.phone.data.db.LocalDownloadEntity
import com.shieldtube.phone.ui.components.EmptyState
import com.shieldtube.phone.ui.components.LoadingIndicator

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DownloadsScreen(
    viewModel: DownloadsViewModel,
    onPlayLocal: (String) -> Unit,
    onPlayServer: (String) -> Unit,
) {
    val uiState by viewModel.uiState.collectAsState()
    val baseUrl by viewModel.baseUrl.collectAsState()

    Column(modifier = Modifier.fillMaxSize()) {
        TabRow(selectedTabIndex = uiState.selectedTab) {
            Tab(
                selected = uiState.selectedTab == 0,
                onClick = { viewModel.selectTab(0) },
                text = { Text("On Phone") },
            )
            Tab(
                selected = uiState.selectedTab == 1,
                onClick = { viewModel.selectTab(1) },
                text = { Text("On Server") },
            )
        }

        when (uiState.selectedTab) {
            0 -> PhoneDownloadsTab(
                downloads = uiState.localDownloads,
                baseUrl = baseUrl,
                onPlay = { onPlayLocal(it) },
                onDelete = { viewModel.deleteLocal(it) },
            )
            1 -> ServerDownloadsTab(
                active = uiState.serverActive,
                library = uiState.serverLibrary,
                isLoading = uiState.isLoading,
                error = uiState.error,
                baseUrl = baseUrl,
                onPlay = { onPlayServer(it) },
                onRefresh = { viewModel.loadServerData() },
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PhoneDownloadsTab(
    downloads: List<LocalDownloadEntity>,
    baseUrl: String,
    onPlay: (String) -> Unit,
    onDelete: (String) -> Unit,
) {
    if (downloads.isEmpty()) {
        EmptyState(
            message = "No videos downloaded to phone",
            modifier = Modifier.fillMaxSize(),
        )
        return
    }

    LazyColumn(modifier = Modifier.fillMaxSize()) {
        items(
            items = downloads,
            key = { it.videoId },
        ) { download ->
            val swipeState = rememberSwipeToDismissBoxState(
                confirmValueChange = { value ->
                    if (value == SwipeToDismissBoxValue.EndToStart) {
                        onDelete(download.videoId)
                        true
                    } else {
                        false
                    }
                },
            )

            SwipeToDismissBox(
                state = swipeState,
                enableDismissFromStartToEnd = false,
                enableDismissFromEndToStart = true,
                backgroundContent = {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .background(MaterialTheme.colorScheme.errorContainer)
                            .padding(end = 16.dp),
                        contentAlignment = Alignment.CenterEnd,
                    ) {
                        Icon(
                            imageVector = Icons.Default.Delete,
                            contentDescription = "Delete",
                            tint = MaterialTheme.colorScheme.onErrorContainer,
                        )
                    }
                },
            ) {
                LocalDownloadRow(
                    download = download,
                    baseUrl = baseUrl,
                    onClick = {
                        if (download.status == "complete") onPlay(download.videoId)
                    },
                    onDelete = { onDelete(download.videoId) },
                )
            }
        }
    }
}

@Composable
private fun LocalDownloadRow(
    download: LocalDownloadEntity,
    baseUrl: String,
    onClick: () -> Unit,
    onDelete: () -> Unit,
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp, vertical = 4.dp)
            .clickable(enabled = download.status == "complete", onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
    ) {
        Column(modifier = Modifier.animateContentSize()) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                AsyncImage(
                    model = "$baseUrl/api/video/${download.videoId}/thumbnail?res=mqdefault",
                    contentDescription = download.title,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier
                        .width(120.dp)
                        .aspectRatio(16f / 9f),
                )
                Spacer(modifier = Modifier.width(8.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = download.title,
                        style = MaterialTheme.typography.bodyMedium,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        text = download.channelName,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.padding(top = 2.dp),
                    )
                    Text(
                        text = when (download.status) {
                            "complete" -> formatFileSize(download.fileSize)
                            "downloading" -> "Downloading... ${download.progress}%"
                            "error" -> "Error"
                            else -> "Pending"
                        },
                        style = MaterialTheme.typography.labelSmall,
                        color = when (download.status) {
                            "complete" -> MaterialTheme.colorScheme.primary
                            "error" -> MaterialTheme.colorScheme.error
                            else -> MaterialTheme.colorScheme.onSurfaceVariant
                        },
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
                if (download.status == "downloading") {
                    CircularProgressIndicator(
                        modifier = Modifier.size(24.dp),
                        strokeWidth = 2.dp,
                    )
                } else {
                    IconButton(onClick = onDelete) {
                        Icon(
                            imageVector = Icons.Default.Delete,
                            contentDescription = "Delete",
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
            if (download.status == "downloading") {
                LinearProgressIndicator(
                    progress = { download.progress / 100f },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(3.dp),
                )
            }
        }
    }
}

@Composable
private fun ServerDownloadsTab(
    active: List<ActiveDownload>,
    library: List<LibraryVideo>,
    isLoading: Boolean,
    error: String?,
    baseUrl: String,
    onPlay: (String) -> Unit,
    onRefresh: () -> Unit,
) {
    if (isLoading && active.isEmpty() && library.isEmpty()) {
        LoadingIndicator(modifier = Modifier.fillMaxSize())
        return
    }
    if (error != null && active.isEmpty() && library.isEmpty()) {
        Column(
            modifier = Modifier.fillMaxSize(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Text(
                text = error,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyMedium,
            )
            Spacer(modifier = Modifier.height(12.dp))
            Button(onClick = onRefresh) {
                Text("Retry")
            }
        }
        return
    }
    if (active.isEmpty() && library.isEmpty()) {
        EmptyState(
            message = "No videos on server",
            modifier = Modifier.fillMaxSize(),
        )
        return
    }

    LazyColumn(modifier = Modifier.fillMaxSize()) {
        if (active.isNotEmpty()) {
            item {
                Text(
                    text = "Active Downloads",
                    style = MaterialTheme.typography.titleSmall,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                    color = MaterialTheme.colorScheme.primary,
                )
            }
            items(active, key = { "active_${it.videoId}" }) { download ->
                ActiveDownloadRow(download = download, baseUrl = baseUrl)
            }
        }
        if (library.isNotEmpty()) {
            item {
                Text(
                    text = "Library",
                    style = MaterialTheme.typography.titleSmall,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                    color = MaterialTheme.colorScheme.primary,
                )
            }
            items(library, key = { "lib_${it.id}" }) { video ->
                LibraryVideoRow(
                    video = video,
                    baseUrl = baseUrl,
                    onClick = { onPlay(video.id) },
                )
            }
        }
    }
}

@Composable
private fun ActiveDownloadRow(
    download: ActiveDownload,
    baseUrl: String,
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp, vertical = 4.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
    ) {
        Column {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                AsyncImage(
                    model = "$baseUrl/api/video/${download.videoId}/thumbnail?res=mqdefault",
                    contentDescription = download.title,
                    contentScale = ContentScale.Crop,
                    modifier = Modifier
                        .width(120.dp)
                        .aspectRatio(16f / 9f),
                )
                Spacer(modifier = Modifier.width(8.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = download.title,
                        style = MaterialTheme.typography.bodyMedium,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        text = download.channelName,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.padding(top = 2.dp),
                    )
                    Text(
                        text = "${download.percent}%",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
                CircularProgressIndicator(
                    progress = { download.percent / 100f },
                    modifier = Modifier.size(28.dp),
                    strokeWidth = 3.dp,
                )
            }
            LinearProgressIndicator(
                progress = { download.percent / 100f },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(3.dp),
            )
        }
    }
}

@Composable
private fun LibraryVideoRow(
    video: LibraryVideo,
    baseUrl: String,
    onClick: () -> Unit,
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp, vertical = 4.dp)
            .clickable(onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            AsyncImage(
                model = "$baseUrl/api/video/${video.id}/thumbnail?res=mqdefault",
                contentDescription = video.title,
                contentScale = ContentScale.Crop,
                modifier = Modifier
                    .width(120.dp)
                    .aspectRatio(16f / 9f),
            )
            Spacer(modifier = Modifier.width(8.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = video.title,
                    style = MaterialTheme.typography.bodyMedium,
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
                video.fileSize?.let { size ->
                    Text(
                        text = formatFileSize(size),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
            }
        }
    }
}

private fun formatFileSize(bytes: Long): String {
    return when {
        bytes <= 0L -> ""
        bytes < 1024 * 1024 -> "${bytes / 1024} KB"
        bytes < 1024 * 1024 * 1024 -> "%.1f MB".format(bytes / (1024.0 * 1024))
        else -> "%.2f GB".format(bytes / (1024.0 * 1024 * 1024))
    }
}
