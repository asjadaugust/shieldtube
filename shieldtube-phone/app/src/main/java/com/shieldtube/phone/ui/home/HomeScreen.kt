package com.shieldtube.phone.ui.home

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.pulltorefresh.PullToRefreshContainer
import androidx.compose.material3.pulltorefresh.rememberPullToRefreshState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.unit.dp
import androidx.compose.material3.Text
import com.shieldtube.phone.data.api.VideoItem
import com.shieldtube.phone.ui.components.VideoGrid

private data class FeedTab(val label: String, val type: String)

private val TABS = listOf(
    FeedTab("For You", "recommended"),
    FeedTab("Home", "home"),
    FeedTab("History", "history"),
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    viewModel: HomeViewModel,
    onVideoClick: (VideoItem) -> Unit,
    onDownloadToPhone: ((VideoItem) -> Unit)? = null,
    onDownloadToServer: ((VideoItem) -> Unit)? = null,
) {
    val uiState by viewModel.uiState.collectAsState()
    val baseUrl by viewModel.baseUrl.collectAsState()

    val pullToRefreshState = rememberPullToRefreshState()

    if (pullToRefreshState.isRefreshing) {
        LaunchedEffect(Unit) {
            viewModel.loadFeed(uiState.selectedTab)
        }
    }

    // Stop the refresh indicator when loading finishes
    LaunchedEffect(uiState.isLoading) {
        if (!uiState.isLoading) {
            pullToRefreshState.endRefresh()
        }
    }

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

        Box(
            modifier = Modifier
                .fillMaxSize()
                .nestedScroll(pullToRefreshState.nestedScrollConnection),
        ) {
            VideoGrid(
                videos = uiState.videos,
                baseUrl = baseUrl,
                onVideoClick = onVideoClick,
                isLoading = uiState.isLoading,
                error = uiState.error,
                onRetry = { viewModel.loadFeed(uiState.selectedTab) },
                onDownloadToPhone = onDownloadToPhone,
                onDownloadToServer = onDownloadToServer,
            )

            PullToRefreshContainer(
                state = pullToRefreshState,
                modifier = Modifier.align(Alignment.TopCenter),
            )
        }
    }
}
