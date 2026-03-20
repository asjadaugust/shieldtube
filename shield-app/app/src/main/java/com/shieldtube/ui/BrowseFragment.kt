package com.shieldtube.ui

import android.os.Bundle
import android.widget.Toast
import androidx.leanback.app.BrowseSupportFragment
import androidx.leanback.widget.ArrayObjectAdapter
import androidx.leanback.widget.HeaderItem
import androidx.leanback.widget.ListRow
import androidx.leanback.widget.ListRowPresenter
import androidx.lifecycle.lifecycleScope
import com.shieldtube.api.ApiClient
import com.shieldtube.api.Video
import com.shieldtube.player.PlaybackFragment
import kotlinx.coroutines.launch

class BrowseFragment : BrowseSupportFragment() {

    companion object {
        private const val HEADER_HOME = 0L
        private const val HEADER_SUBSCRIPTIONS = 1L
    }

    // Top-level adapter holds the two rows
    private lateinit var rowsAdapter: ArrayObjectAdapter
    // Per-row content adapters
    private val homeAdapter = ArrayObjectAdapter(CardPresenter())
    private val subsAdapter = ArrayObjectAdapter(CardPresenter())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        title = "ShieldTube"
        headersState = HEADERS_ENABLED
        isHeadersTransitionOnBackEnabled = true
        brandColor = 0xFF1a1a2e.toInt()
        searchAffordanceColor = 0xFFe94560.toInt()

        setupHeaders()
        setupListeners()

        // Load Home feed immediately on launch
        loadFeedForHeader(HEADER_HOME)
    }

    private fun setupHeaders() {
        rowsAdapter = ArrayObjectAdapter(ListRowPresenter())

        val homeHeader = HeaderItem(HEADER_HOME, "Home")
        val subsHeader = HeaderItem(HEADER_SUBSCRIPTIONS, "Subscriptions")

        rowsAdapter.add(ListRow(homeHeader, homeAdapter))
        rowsAdapter.add(ListRow(subsHeader, subsAdapter))

        adapter = rowsAdapter
    }

    private fun setupListeners() {
        // Navigate to playback when a card is clicked
        setOnItemViewClickedListener { _, item, _, _ ->
            val video = item as? Video ?: return@setOnItemViewClickedListener
            val fragment = PlaybackFragment.newInstance(video.id)
            parentFragmentManager.beginTransaction()
                .replace(android.R.id.content, fragment)
                .addToBackStack("playback")
                .commit()
        }

        // Load the appropriate feed when the user switches headers
        setOnItemViewSelectedListener { _, _, rowViewHolder, row ->
            val listRow = row as? ListRow ?: return@setOnItemViewSelectedListener
            val headerId = listRow.headerItem?.id ?: return@setOnItemViewSelectedListener
            loadFeedForHeader(headerId)
        }

        // Search icon click → SearchFragment
        setOnSearchClickedListener {
            parentFragmentManager.beginTransaction()
                .replace(android.R.id.content, SearchFragment())
                .addToBackStack("search")
                .commit()
        }
    }

    private fun loadFeedForHeader(headerId: Long) {
        lifecycleScope.launch {
            try {
                val feedResponse = when (headerId) {
                    HEADER_HOME -> ApiClient.api.getFeedHome()
                    HEADER_SUBSCRIPTIONS -> ApiClient.api.getFeedSubscriptions()
                    else -> return@launch
                }
                updateRowContent(headerId, feedResponse.videos)
            } catch (e: Exception) {
                val message = when (headerId) {
                    HEADER_HOME -> "Couldn't load feed. Check your connection."
                    HEADER_SUBSCRIPTIONS -> "Couldn't load subscriptions. Check your connection."
                    else -> "Couldn't load feed. Check your connection."
                }
                Toast.makeText(requireContext(), message, Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun updateRowContent(headerId: Long, videos: List<Video>) {
        val targetAdapter = when (headerId) {
            HEADER_HOME -> homeAdapter
            HEADER_SUBSCRIPTIONS -> subsAdapter
            else -> return
        }
        targetAdapter.clear()
        targetAdapter.addAll(0, videos)
    }
}
