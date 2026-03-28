package com.shieldtube.player

import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.KeyEvent
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import androidx.media3.extractor.DefaultExtractorsFactory
import androidx.media3.ui.PlayerView
import com.shieldtube.api.ApiClient
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class ShortsPlayerFragment : Fragment() {

    companion object {
        private const val ARG_VIDEO_IDS = "video_ids"
        private const val ARG_START_INDEX = "start_index"

        fun newInstance(videoIds: ArrayList<String>, startIndex: Int): ShortsPlayerFragment {
            return ShortsPlayerFragment().apply {
                arguments = Bundle().apply {
                    putStringArrayList(ARG_VIDEO_IDS, videoIds)
                    putInt(ARG_START_INDEX, startIndex)
                }
            }
        }
    }

    private var player: ExoPlayer? = null
    private var playerView: PlayerView? = null
    private var videoIds: List<String> = emptyList()
    private var currentIndex: Int = 0
    private var titleView: TextView? = null
    private var channelView: TextView? = null
    private var overlayView: View? = null
    private var overlayHideJob: Job? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        videoIds = arguments?.getStringArrayList(ARG_VIDEO_IDS) ?: emptyList()
        currentIndex = arguments?.getInt(ARG_START_INDEX, 0) ?: 0
    }

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        val context = requireContext()
        val dm = context.resources.displayMetrics
        val screenHeight = dm.heightPixels
        val screenWidth = dm.widthPixels
        // Portrait: width = height × (9/16) to maintain 9:16 ratio on a 16:9 display
        val playerWidth = (screenHeight * 9.0 / 16.0).toInt()
        val sideMargin = (screenWidth - playerWidth) / 2

        playerView = PlayerView(context).apply {
            useController = false
        }

        val titleText = TextView(context).apply {
            textSize = 16f
            setTextColor(Color.WHITE)
        }
        val channelText = TextView(context).apply {
            textSize = 13f
            setTextColor(Color.LTGRAY)
            setPadding(0, 4, 0, 0)
        }
        titleView = titleText
        channelView = channelText

        val overlay = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#99000000"))
            setPadding(24, 16, 24, 16)
            addView(titleText)
            addView(channelText)
            layoutParams = FrameLayout.LayoutParams(
                playerWidth, FrameLayout.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM or Gravity.START
            ).apply { leftMargin = sideMargin }
            visibility = View.GONE
        }
        overlayView = overlay

        val playerFrame = FrameLayout(context).apply {
            layoutParams = FrameLayout.LayoutParams(
                playerWidth, FrameLayout.LayoutParams.MATCH_PARENT
            ).apply { leftMargin = sideMargin }
            addView(playerView!!, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ))
        }

        val root = object : FrameLayout(context) {
            override fun dispatchKeyEvent(event: KeyEvent): Boolean {
                if (event.action == KeyEvent.ACTION_DOWN) {
                    when (event.keyCode) {
                        KeyEvent.KEYCODE_DPAD_DOWN -> { navigateToNext(); return true }
                        KeyEvent.KEYCODE_DPAD_UP -> { navigateToPrev(); return true }
                    }
                }
                return super.dispatchKeyEvent(event)
            }
        }.apply {
            setBackgroundColor(Color.BLACK)
            isFocusable = true
            isFocusableInTouchMode = true
            addView(playerFrame)
            addView(overlay)
        }

        return root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        initPlayer()
        if (videoIds.isNotEmpty()) loadShort(currentIndex)
    }

    private fun initPlayer() {
        val exoPlayer = ExoPlayer.Builder(requireContext()).build().apply {
            repeatMode = Player.REPEAT_MODE_ONE
            playWhenReady = true
            addListener(object : Player.Listener {
                override fun onPlayerError(error: PlaybackException) {
                    if (isAdded) {
                        Toast.makeText(requireContext(), "Couldn't load Short. Press ↓ to skip.", Toast.LENGTH_SHORT).show()
                    }
                }
            })
        }
        player = exoPlayer
        playerView?.player = exoPlayer
    }

    private fun loadShort(index: Int) {
        val videoId = videoIds.getOrNull(index) ?: return
        val streamUrl = "${ApiClient.BASE_URL}/api/video/$videoId/stream"
        val mediaItem = MediaItem.fromUri(Uri.parse(streamUrl))
        val dataSourceFactory = DefaultHttpDataSource.Factory()
            .setDefaultRequestProperties(mapOf(
                "X-ShieldTube-Secret" to com.shieldtube.BuildConfig.API_SECRET
            ))
        val extractorsFactory = DefaultExtractorsFactory()
            .setConstantBitrateSeekingEnabled(true)
        val mediaSource = ProgressiveMediaSource.Factory(dataSourceFactory, extractorsFactory)
            .createMediaSource(mediaItem)

        player?.let { p ->
            p.stop()
            p.setMediaSource(mediaSource)
            p.prepare()
        }

        // Fetch title/channel asynchronously — show overlay once available
        lifecycleScope.launch {
            try {
                val meta = ApiClient.api.getVideoMeta(videoId)
                titleView?.text = meta.title
                channelView?.text = meta.channelName
                showOverlay()
            } catch (_: Exception) {
                // Overlay stays hidden if metadata unavailable
            }
        }
    }

    private fun navigateToNext() {
        if (videoIds.isEmpty()) return
        currentIndex = (currentIndex + 1) % videoIds.size
        loadShort(currentIndex)
    }

    private fun navigateToPrev() {
        if (videoIds.isEmpty()) return
        currentIndex = if (currentIndex == 0) videoIds.size - 1 else currentIndex - 1
        loadShort(currentIndex)
    }

    private fun showOverlay() {
        overlayHideJob?.cancel()
        overlayView?.visibility = View.VISIBLE
        overlayHideJob = lifecycleScope.launch {
            delay(3000)
            overlayView?.visibility = View.GONE
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        overlayHideJob?.cancel()
        player?.release()
        player = null
        playerView?.player = null
        playerView = null
        overlayView = null
        titleView = null
        channelView = null
    }
}
