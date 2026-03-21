package com.shieldtube.phone.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.shieldtube.phone.data.api.VideoItem

@Composable
fun VideoGrid(
    videos: List<VideoItem>,
    baseUrl: String,
    onVideoClick: (VideoItem) -> Unit,
    isLoading: Boolean = false,
    error: String? = null,
    onRetry: () -> Unit = {},
    onDownloadToPhone: ((VideoItem) -> Unit)? = null,
    onDownloadToServer: ((VideoItem) -> Unit)? = null,
    modifier: Modifier = Modifier,
) {
    when {
        isLoading && videos.isEmpty() -> LoadingIndicator(modifier = modifier)
        error != null && videos.isEmpty() -> ErrorMessage(
            message = error,
            onRetry = onRetry,
            modifier = modifier,
        )
        videos.isEmpty() -> EmptyState(
            message = "Nothing here yet",
            modifier = modifier,
        )
        else -> LazyVerticalGrid(
            columns = GridCells.Fixed(2),
            modifier = modifier.fillMaxSize(),
            contentPadding = PaddingValues(8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(videos, key = { it.id }) { video ->
                VideoCard(
                    video = video,
                    baseUrl = baseUrl,
                    onClick = { onVideoClick(video) },
                    onDownloadToPhone = onDownloadToPhone,
                    onDownloadToServer = onDownloadToServer,
                )
            }
        }
    }
}
