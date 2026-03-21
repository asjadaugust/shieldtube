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
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class BrowseFragment : BrowseSupportFragment() {

    private var castPollJob: Job? = null
    private val loadedFeeds = mutableSetOf<Long>()

    companion object {
        private const val HEADER_HOME = 0L
        private const val HEADER_SUBSCRIPTIONS = 1L
        private const val HEADER_WATCH_LATER = 2L
        private const val HEADER_FOR_YOU = 3L
    }

    // Top-level adapter holds the three rows
    private lateinit var rowsAdapter: ArrayObjectAdapter
    // Per-row content adapters
    private val forYouAdapter = ArrayObjectAdapter(CardPresenter())
    private val homeAdapter = ArrayObjectAdapter(CardPresenter())
    private val subsAdapter = ArrayObjectAdapter(CardPresenter())
    private val watchLaterAdapter = ArrayObjectAdapter(CardPresenter())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        title = "ShieldTube"
        headersState = HEADERS_ENABLED
        isHeadersTransitionOnBackEnabled = true
        brandColor = 0xFF1a1a2e.toInt()
        searchAffordanceColor = 0xFFe94560.toInt()

        setupHeaders()
        setupListeners()

        // Load all feeds on launch
        val cached = loadCachedRecommendations()
        if (cached.isNotEmpty()) {
            forYouAdapter.addAll(0, cached)
        }
        loadFeedForHeader(HEADER_FOR_YOU)
        loadFeedForHeader(HEADER_HOME)
        loadFeedForHeader(HEADER_SUBSCRIPTIONS)
        loadFeedForHeader(HEADER_WATCH_LATER)

        castPollJob = lifecycleScope.launch {
            while (isActive) {
                delay(5000) // Poll every 5 seconds
                try {
                    val nowPlaying = ApiClient.api.getNowPlaying()
                    if (nowPlaying.videoId != null) {
                        // Navigate to playback
                        requireActivity().supportFragmentManager.beginTransaction()
                            .replace(android.R.id.content, PlaybackFragment.newInstance(nowPlaying.videoId))
                            .addToBackStack("playback")
                            .commit()
                    }
                } catch (e: Exception) {
                    // Silently ignore polling errors
                }
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        castPollJob?.cancel()
    }

    private fun setupHeaders() {
        rowsAdapter = ArrayObjectAdapter(ListRowPresenter())

        val forYouHeader = HeaderItem(HEADER_FOR_YOU, "For You")
        rowsAdapter.add(ListRow(forYouHeader, forYouAdapter))

        val homeHeader = HeaderItem(HEADER_HOME, "Home")
        val subsHeader = HeaderItem(HEADER_SUBSCRIPTIONS, "Subscriptions")
        val watchLaterHeader = HeaderItem(HEADER_WATCH_LATER, "Watch Later")

        rowsAdapter.add(ListRow(homeHeader, homeAdapter))
        rowsAdapter.add(ListRow(subsHeader, subsAdapter))
        rowsAdapter.add(ListRow(watchLaterHeader, watchLaterAdapter))

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
        if (headerId in loadedFeeds) {
            android.util.Log.d("ShieldTube", "loadFeed: header=$headerId already loaded, skipping")
            return
        }
        loadedFeeds.add(headerId)
        android.util.Log.d("ShieldTube", "loadFeed: launching coroutine for header=$headerId")
        lifecycleScope.launch {
            try {
                android.util.Log.d("ShieldTube", "loadFeed: requesting feed for header=$headerId")
                val feedResponse = when (headerId) {
                    HEADER_FOR_YOU -> ApiClient.api.getFeedRecommended()
                    HEADER_HOME -> ApiClient.api.getFeedHome()
                    HEADER_SUBSCRIPTIONS -> ApiClient.api.getFeedSubscriptions()
                    HEADER_WATCH_LATER -> ApiClient.api.getFeedWatchLater()
                    else -> return@launch
                }
                android.util.Log.d("ShieldTube", "loadFeed: got ${feedResponse.videos.size} videos for header=$headerId")
                updateRowContent(headerId, feedResponse.videos)
            } catch (e: retrofit2.HttpException) {
                android.util.Log.e("ShieldTube", "loadFeed: HTTP error for header=$headerId: ${e.code()} ${e.message()}", e)
                if (e.code() == 401 && isAdded) {
                    parentFragmentManager.beginTransaction()
                        .replace(android.R.id.content, LoginFragment())
                        .commit()
                    return@launch
                }
                if (isAdded) {
                    Toast.makeText(requireContext(), "Couldn't load feed. Check your connection.", Toast.LENGTH_SHORT).show()
                }
            } catch (e: Exception) {
                android.util.Log.e("ShieldTube", "loadFeed: exception for header=$headerId: ${e.javaClass.simpleName}: ${e.message}", e)
                if (isAdded) {
                    Toast.makeText(requireContext(), "Couldn't load feed. Check your connection.", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun updateRowContent(headerId: Long, videos: List<Video>) {
        val targetAdapter = when (headerId) {
            HEADER_FOR_YOU -> forYouAdapter
            HEADER_HOME -> homeAdapter
            HEADER_SUBSCRIPTIONS -> subsAdapter
            HEADER_WATCH_LATER -> watchLaterAdapter
            else -> return
        }
        targetAdapter.clear()
        targetAdapter.addAll(0, videos)
        if (headerId == HEADER_FOR_YOU) cacheRecommendations(videos)
    }

    private fun cacheRecommendations(videos: List<Video>) {
        try {
            val json = com.google.gson.Gson().toJson(videos)
            java.io.File(requireContext().filesDir, "recommended_cache.json").writeText(json)
        } catch (e: Exception) {
            android.util.Log.w("ShieldTube", "Failed to cache recommendations: ${e.message}")
        }
    }

    private fun loadCachedRecommendations(): List<Video> {
        return try {
            val file = java.io.File(requireContext().filesDir, "recommended_cache.json")
            if (file.exists()) {
                val type = object : com.google.gson.reflect.TypeToken<List<Video>>() {}.type
                com.google.gson.Gson().fromJson(file.readText(), type)
            } else emptyList()
        } catch (e: Exception) {
            emptyList()
        }
    }
}
