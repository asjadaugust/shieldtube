package com.shieldtube.ui

import android.os.Bundle
import android.widget.Toast
import androidx.leanback.app.BrowseSupportFragment
import androidx.leanback.widget.ArrayObjectAdapter
import androidx.leanback.widget.HeaderItem
import androidx.leanback.widget.ListRow
import androidx.leanback.widget.ListRowPresenter
import androidx.lifecycle.lifecycleScope
import com.shieldtube.R
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
        private const val HEADER_HISTORY = 2L
        private const val HEADER_FOR_YOU = 3L
        private const val HEADER_DOWNLOADS = 4L
        private const val HEADER_NEW_CHANNELS = 5L
        private const val HEADER_SHORTS_RECOMMENDED = 6L
        private const val HEADER_SHORTS_TRENDING = 7L
    }

    // Top-level adapter holds the rows
    private lateinit var rowsAdapter: ArrayObjectAdapter
    // Per-row content adapters
    private val downloadsAdapter = ArrayObjectAdapter(CardPresenter())
    private val channelsAdapter = ArrayObjectAdapter(CardPresenter())
    private val forYouAdapter = ArrayObjectAdapter(CardPresenter())
    private val homeAdapter = ArrayObjectAdapter(CardPresenter())
    private val historyAdapter = ArrayObjectAdapter(CardPresenter())
    private val shortsRecommendedAdapter = ArrayObjectAdapter(ShortsCardPresenter())
    private val shortsTrendingAdapter = ArrayObjectAdapter(ShortsCardPresenter())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        title = "ShieldTube"
        headersState = HEADERS_ENABLED
        isHeadersTransitionOnBackEnabled = true
        brandColor = resources.getColor(R.color.background_dark, null)
        searchAffordanceColor = resources.getColor(R.color.nvidia_green, null)

        setupHeaders()
        setupListeners()

        // Load all feeds on launch
        val cached = loadCachedRecommendations()
        if (cached.isNotEmpty()) {
            forYouAdapter.addAll(0, cached)
        }
        loadFeedForHeader(HEADER_SHORTS_RECOMMENDED)
        loadFeedForHeader(HEADER_SHORTS_TRENDING)
        loadFeedForHeader(HEADER_DOWNLOADS)
        loadFeedForHeader(HEADER_NEW_CHANNELS)
        loadFeedForHeader(HEADER_FOR_YOU)
        loadFeedForHeader(HEADER_HOME)
        loadFeedForHeader(HEADER_HISTORY)
    }

    override fun onResume() {
        super.onResume()
        startCastPolling()
        refreshFeed(HEADER_SHORTS_RECOMMENDED)
        refreshFeed(HEADER_SHORTS_TRENDING)
        refreshFeed(HEADER_DOWNLOADS)
        refreshFeed(HEADER_NEW_CHANNELS)
        refreshFeed(HEADER_HISTORY)
        refreshFeed(HEADER_HOME)
        refreshFeed(HEADER_FOR_YOU)
    }

    override fun onPause() {
        super.onPause()
        castPollJob?.cancel()
        castPollJob = null
    }

    override fun onDestroy() {
        super.onDestroy()
        castPollJob?.cancel()
    }

    private fun startCastPolling() {
        castPollJob?.cancel()
        castPollJob = lifecycleScope.launch {
            while (isActive) {
                delay(2000)
                try {
                    val nowPlaying = ApiClient.api.getNowPlaying()
                    if (nowPlaying.videoId != null) {
                        castPollJob?.cancel()
                        requireActivity().supportFragmentManager.beginTransaction()
                            .replace(android.R.id.content, PlaybackFragment.newInstance(nowPlaying.videoId))
                            .addToBackStack("playback")
                            .commit()
                        return@launch
                    }
                } catch (e: Exception) {
                    // Silently ignore polling errors
                }
            }
        }
    }

    private fun setupHeaders() {
        rowsAdapter = ArrayObjectAdapter(ListRowPresenter())

        val shortsRecHeader = HeaderItem(HEADER_SHORTS_RECOMMENDED, "Shorts — For You")
        rowsAdapter.add(ListRow(shortsRecHeader, shortsRecommendedAdapter))

        val shortsTrendHeader = HeaderItem(HEADER_SHORTS_TRENDING, "Shorts — Trending")
        rowsAdapter.add(ListRow(shortsTrendHeader, shortsTrendingAdapter))

        val downloadsHeader = HeaderItem(HEADER_DOWNLOADS, "Downloads")
        rowsAdapter.add(ListRow(downloadsHeader, downloadsAdapter))

        val channelsHeader = HeaderItem(HEADER_NEW_CHANNELS, "New from your channels")
        rowsAdapter.add(ListRow(channelsHeader, channelsAdapter))

        val forYouHeader = HeaderItem(HEADER_FOR_YOU, "For You")
        rowsAdapter.add(ListRow(forYouHeader, forYouAdapter))

        val homeHeader = HeaderItem(HEADER_HOME, "Home")
        rowsAdapter.add(ListRow(homeHeader, homeAdapter))

        val historyHeader = HeaderItem(HEADER_HISTORY, "History")
        rowsAdapter.add(ListRow(historyHeader, historyAdapter))

        adapter = rowsAdapter
    }

    private fun setupListeners() {
        // Navigate to playback when a card is clicked
        setOnItemViewClickedListener { _, item, _, row ->
            val video = item as? Video ?: return@setOnItemViewClickedListener
            val listRow = row as? androidx.leanback.widget.ListRow
            val headerId = listRow?.headerItem?.id

            if (headerId == HEADER_SHORTS_RECOMMENDED || headerId == HEADER_SHORTS_TRENDING) {
                val adapter = if (headerId == HEADER_SHORTS_RECOMMENDED) shortsRecommendedAdapter else shortsTrendingAdapter
                val videoIds = ArrayList((0 until adapter.size()).map { (adapter.get(it) as Video).id })
                val startIndex = videoIds.indexOf(video.id).coerceAtLeast(0)
                val fragment = com.shieldtube.player.ShortsPlayerFragment.newInstance(videoIds, startIndex)
                parentFragmentManager.beginTransaction()
                    .replace(android.R.id.content, fragment)
                    .addToBackStack("shorts")
                    .commit()
            } else {
                val fragment = PlaybackFragment.newInstance(video.id)
                parentFragmentManager.beginTransaction()
                    .replace(android.R.id.content, fragment)
                    .addToBackStack("playback")
                    .commit()
            }
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

    private fun refreshFeed(headerId: Long) {
        lifecycleScope.launch {
            try {
                val feedResponse = when (headerId) {
                    HEADER_SHORTS_RECOMMENDED -> ApiClient.api.getShortsRecommended()
                    HEADER_SHORTS_TRENDING -> ApiClient.api.getShortsTrending()
                    HEADER_DOWNLOADS -> ApiClient.api.getDownloadLibrary()
                    HEADER_NEW_CHANNELS -> ApiClient.api.getFeedChannels()
                    HEADER_HISTORY -> ApiClient.api.getFeedHistory()
                    HEADER_HOME -> ApiClient.api.getFeedHome()
                    HEADER_FOR_YOU -> ApiClient.api.getFeedRecommended()
                    else -> return@launch
                }
                updateRowContent(headerId, feedResponse.videos)
            } catch (_: Exception) {
                // Silent — don't toast on background refresh
            }
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
                    HEADER_SHORTS_RECOMMENDED -> ApiClient.api.getShortsRecommended()
                    HEADER_SHORTS_TRENDING -> ApiClient.api.getShortsTrending()
                    HEADER_DOWNLOADS -> ApiClient.api.getDownloadLibrary()
                    HEADER_NEW_CHANNELS -> ApiClient.api.getFeedChannels()
                    HEADER_FOR_YOU -> ApiClient.api.getFeedRecommended()
                    HEADER_HOME -> ApiClient.api.getFeedHome()
                    HEADER_HISTORY -> ApiClient.api.getFeedHistory()
                    else -> return@launch
                }
                android.util.Log.d("ShieldTube", "loadFeed: got ${feedResponse.videos.size} videos for header=$headerId")
                updateRowContent(headerId, feedResponse.videos)
            } catch (e: retrofit2.HttpException) {
                android.util.Log.e("ShieldTube", "loadFeed: HTTP error for header=$headerId: ${e.code()} ${e.message()}", e)
                if (e.code() == 401 && isAdded) {
                    android.util.Log.e("ShieldTube", "loadFeed: 401 on header=$headerId — check API_SECRET config")
                    Toast.makeText(requireContext(), "API secret mismatch (401). Check server config.", Toast.LENGTH_LONG).show()
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
            HEADER_SHORTS_RECOMMENDED -> shortsRecommendedAdapter
            HEADER_SHORTS_TRENDING -> shortsTrendingAdapter
            HEADER_DOWNLOADS -> downloadsAdapter
            HEADER_NEW_CHANNELS -> channelsAdapter
            HEADER_FOR_YOU -> forYouAdapter
            HEADER_HOME -> homeAdapter
            HEADER_HISTORY -> historyAdapter
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
