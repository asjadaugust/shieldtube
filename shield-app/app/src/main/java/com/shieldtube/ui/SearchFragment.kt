package com.shieldtube.ui

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Toast
import androidx.leanback.app.SearchSupportFragment
import androidx.leanback.widget.ArrayObjectAdapter
import androidx.leanback.widget.HeaderItem
import androidx.leanback.widget.ListRow
import androidx.leanback.widget.ListRowPresenter
import androidx.leanback.widget.ObjectAdapter
import androidx.lifecycle.lifecycleScope
import com.shieldtube.api.ApiClient
import com.shieldtube.api.Video
import com.shieldtube.player.PlaybackFragment
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

class SearchFragment : SearchSupportFragment(), SearchSupportFragment.SearchResultProvider {

    private val resultsAdapter = ArrayObjectAdapter(ListRowPresenter())
    private val handler = Handler(Looper.getMainLooper())
    private var searchJob: Job? = null

    private val debounceRunnable = Runnable {
        val query = currentQuery
        if (query.isNotBlank()) {
            performSearch(query)
        }
    }

    private var currentQuery: String = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setSearchResultProvider(this)

        setOnItemViewClickedListener { _, item, _, _ ->
            val video = item as? Video ?: return@setOnItemViewClickedListener
            val fragment = PlaybackFragment.newInstance(video.id)
            parentFragmentManager.beginTransaction()
                .replace(android.R.id.content, fragment)
                .addToBackStack("playback")
                .commit()
        }
    }

    override fun getResultsAdapter(): ObjectAdapter = resultsAdapter

    override fun onQueryTextChange(newQuery: String): Boolean {
        currentQuery = newQuery
        handler.removeCallbacks(debounceRunnable)
        if (newQuery.isBlank()) {
            resultsAdapter.clear()
            return true
        }
        handler.postDelayed(debounceRunnable, 300L)
        return true
    }

    override fun onQueryTextSubmit(query: String): Boolean {
        handler.removeCallbacks(debounceRunnable)
        currentQuery = query
        if (query.isNotBlank()) {
            performSearch(query)
        }
        return true
    }

    private fun performSearch(query: String) {
        searchJob?.cancel()
        searchJob = lifecycleScope.launch {
            try {
                val response = ApiClient.api.search(query)
                displayResults(response.videos)
            } catch (e: Exception) {
                Toast.makeText(
                    requireContext(),
                    "Search unavailable. Try again.",
                    Toast.LENGTH_SHORT
                ).show()
            }
        }
    }

    private fun displayResults(videos: List<Video>) {
        resultsAdapter.clear()
        if (videos.isEmpty()) return

        val cardAdapter = ArrayObjectAdapter(CardPresenter())
        cardAdapter.addAll(0, videos)

        val header = HeaderItem(0L, "Results")
        resultsAdapter.add(ListRow(header, cardAdapter))
    }

    override fun onDestroy() {
        super.onDestroy()
        handler.removeCallbacks(debounceRunnable)
        searchJob?.cancel()
    }
}
