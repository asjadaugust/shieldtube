package com.shieldtube.phone.ui.search

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.shieldtube.phone.data.api.VideoItem
import com.shieldtube.phone.ui.components.EmptyState
import com.shieldtube.phone.ui.components.VideoGrid

@Composable
fun SearchScreen(
    viewModel: SearchViewModel,
    onVideoClick: (VideoItem) -> Unit,
) {
    val uiState by viewModel.uiState.collectAsState()
    val baseUrl by viewModel.baseUrl.collectAsState()

    Column(modifier = Modifier.fillMaxSize()) {
        OutlinedTextField(
            value = uiState.query,
            onValueChange = { viewModel.updateQuery(it) },
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 8.dp),
            placeholder = { Text("Search YouTube") },
            leadingIcon = {
                Icon(Icons.Default.Search, contentDescription = "Search")
            },
            trailingIcon = {
                if (uiState.query.isNotEmpty()) {
                    IconButton(onClick = { viewModel.updateQuery("") }) {
                        Icon(Icons.Default.Clear, contentDescription = "Clear")
                    }
                }
            },
            singleLine = true,
        )

        when {
            uiState.query.length < 2 && !uiState.hasSearched ->
                EmptyState(message = "Search YouTube", modifier = Modifier.fillMaxSize())

            else -> VideoGrid(
                videos = uiState.results,
                baseUrl = baseUrl,
                onVideoClick = onVideoClick,
                isLoading = uiState.isLoading,
                error = uiState.error,
                onRetry = { viewModel.updateQuery(uiState.query) },
            )
        }
    }
}
