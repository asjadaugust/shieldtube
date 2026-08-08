package com.shieldtube.phone.ui.home

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.FilterChip
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.material3.Text
import com.shieldtube.phone.data.api.VideoItem
import com.shieldtube.phone.ui.components.VideoGrid

private data class FeedTab(val label: String, val type: String)

private val TABS = listOf(
    FeedTab("For You", "recommended"),
    FeedTab("Channels", "channels"),
    FeedTab("Home", "home"),
    FeedTab("History", "history"),
)

@Composable
fun HomeScreen(
    viewModel: HomeViewModel,
    onVideoClick: (VideoItem) -> Unit,
    onDownloadToPhone: ((VideoItem) -> Unit)? = null,
    onDownloadToServer: ((VideoItem) -> Unit)? = null,
) {
    val uiState by viewModel.uiState.collectAsState()
    val baseUrl by viewModel.baseUrl.collectAsState()

    Column(modifier = Modifier.fillMaxSize()) {
        LazyRow(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 4.dp),
        ) {
            items(TABS) { tab ->
                FilterChip(
                    selected = uiState.selectedTab == tab.type,
                    onClick = { viewModel.selectTab(tab.type) },
                    label = { Text(tab.label) },
                    modifier = Modifier.padding(end = 8.dp),
                )
            }
        }

        VideoGrid(
            videos = uiState.videos,
            baseUrl = baseUrl,
            onVideoClick = onVideoClick,
            isLoading = uiState.isLoading,
            error = uiState.error,
            onRetry = { viewModel.loadFeed(uiState.selectedTab) },
            onDownloadToPhone = onDownloadToPhone,
            onDownloadToServer = onDownloadToServer,
            modifier = Modifier.fillMaxSize(),
        )
    }
}
