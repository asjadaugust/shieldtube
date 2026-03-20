package com.shieldtube.player

import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.util.Log
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
import androidx.media3.common.PlaybackParameters
import androidx.media3.common.MimeTypes
import androidx.media3.common.Player
import androidx.media3.exoplayer.DefaultRenderersFactory
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import com.shieldtube.api.ApiClient
import com.shieldtube.api.Chapter
import com.shieldtube.api.ProgressBody
import com.shieldtube.api.SponsorSegment
import com.shieldtube.api.SubtitleTrack
import com.shieldtube.api.VideoFormat
import kotlinx.coroutines.*

class PlaybackFragment : Fragment() {

    companion object {
        const val BACKEND_HOST = "https://192.168.1.100:8443"
        private const val ARG_VIDEO_ID = "video_id"
        private const val TAG = "PlaybackFragment"

        fun newInstance(videoId: String): PlaybackFragment {
            return PlaybackFragment().apply {
                arguments = Bundle().apply {
                    putString(ARG_VIDEO_ID, videoId)
                }
            }
        }
    }

    private var player: ExoPlayer? = null
    private var playerView: PlayerView? = null
    private var progressJob: Job? = null
    private var videoId: String? = null
    private var sponsorSegments: List<SponsorSegment> = emptyList()
    private var skippedSegmentIndices: MutableSet<Int> = mutableSetOf()
    private var skipCheckJob: Job? = null
    private var userSeekedRecently = false

    // Chapter marker state
    private var chapters: List<Chapter> = emptyList()
    private var currentChapterIndex: Int = -1
    private var chapterCheckJob: Job? = null
    private var chapterOverlay: TextView? = null

    // Subtitle state
    private var subtitleTracks: List<SubtitleTrack> = emptyList()
    private var currentSubtitleLang: String? = null
    private var subtitleOverlay: LinearLayout? = null
    private var subtitleOverlayVisible: Boolean = false

    // Playback speed state
    private var currentSpeed: Float = 1.0f
    private var speedOverlay: LinearLayout? = null
    private val SPEED_OPTIONS = floatArrayOf(0.5f, 0.75f, 1.0f, 1.25f, 1.5f, 2.0f)

    // Quality selection state
    private var selectedQuality: String = "auto"
    private var availableFormats: List<VideoFormat> = emptyList()
    private var qualityOverlay: LinearLayout? = null
    private var qualityOverlayVisible: Boolean = false

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        playerView = PlayerView(requireContext()).apply {
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        }

        // Chapter title overlay: semi-transparent black background, white text, top-left
        val overlay = TextView(requireContext()).apply {
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.TOP or Gravity.START
            ).also { params ->
                params.setMargins(48, 48, 48, 0)
            }
            setBackgroundColor(Color.parseColor("#99000000"))
            setTextColor(Color.WHITE)
            textSize = 16f
            setPadding(24, 12, 24, 12)
            visibility = View.GONE
        }
        chapterOverlay = overlay

        // Subtitle selection overlay: vertical list on the left side, hidden by default
        val subtitleMenu = LinearLayout(requireContext()).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.CENTER_VERTICAL or Gravity.START
            ).also { params ->
                params.setMargins(48, 0, 0, 0)
            }
            setBackgroundColor(Color.parseColor("#CC000000"))
            setPadding(16, 16, 16, 16)
            visibility = View.GONE
        }
        subtitleOverlay = subtitleMenu

        val container = FrameLayout(requireContext()).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
            isFocusable = true
            isFocusableInTouchMode = true
            addView(playerView)
            addView(overlay)
            addView(subtitleMenu)
            speedOverlay = LinearLayout(requireContext()).apply {
                orientation = LinearLayout.VERTICAL
                setBackgroundColor(Color.parseColor("#CC000000"))
                setPadding(32, 16, 32, 16)
                visibility = View.GONE
                layoutParams = FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.WRAP_CONTENT,
                    FrameLayout.LayoutParams.WRAP_CONTENT,
                    Gravity.CENTER_VERTICAL or Gravity.END
                ).apply { setMargins(0, 0, 32, 0) }
                SPEED_OPTIONS.forEach { speed ->
                    addView(TextView(context).apply {
                        text = "${speed}x"
                        textSize = 18f
                        setPadding(24, 12, 24, 12)
                        setTextColor(if (speed == currentSpeed) Color.parseColor("#e94560") else Color.WHITE)
                        isFocusable = true
                        isFocusableInTouchMode = true
                        setOnClickListener { selectSpeed(speed) }
                    })
                }
            }
            addView(speedOverlay)
            qualityOverlay = LinearLayout(requireContext()).apply {
                orientation = LinearLayout.VERTICAL
                setBackgroundColor(Color.parseColor("#CC000000"))
                setPadding(32, 16, 32, 16)
                visibility = View.GONE
                layoutParams = FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.WRAP_CONTENT,
                    FrameLayout.LayoutParams.WRAP_CONTENT,
                    Gravity.CENTER_VERTICAL or Gravity.CENTER_HORIZONTAL
                )
            }
            addView(qualityOverlay)
            setOnKeyListener { _, keyCode, event ->
                if (event.action == KeyEvent.ACTION_DOWN) {
                    when {
                        keyCode == KeyEvent.KEYCODE_DPAD_RIGHT && event.isLongPress -> {
                            jumpToNextChapter()
                            true
                        }
                        keyCode == KeyEvent.KEYCODE_DPAD_LEFT && event.isLongPress -> {
                            jumpToPreviousChapter()
                            true
                        }
                        keyCode == KeyEvent.KEYCODE_DPAD_DOWN && event.isLongPress -> {
                            toggleSubtitleOverlay()
                            true
                        }
                        keyCode == KeyEvent.KEYCODE_DPAD_UP && event.isLongPress -> {
                            toggleSpeedOverlay()
                            true
                        }
                        keyCode == KeyEvent.KEYCODE_MENU -> {
                            toggleQualityOverlay()
                            true
                        }
                        keyCode == KeyEvent.KEYCODE_BACK && qualityOverlayVisible -> {
                            hideQualityOverlay()
                            true
                        }
                        keyCode == KeyEvent.KEYCODE_BACK && subtitleOverlayVisible -> {
                            hideSubtitleOverlay()
                            true
                        }
                        else -> false
                    }
                } else {
                    false
                }
            }
        }

        return container
    }

    override fun onStart() {
        super.onStart()
        initPlayer()
    }

    override fun onStop() {
        super.onStop()
        releasePlayer()
    }

    private fun initPlayer() {
        val videoId = arguments?.getString(ARG_VIDEO_ID)
        if (videoId == null) {
            Log.e(TAG, "No video ID provided")
            parentFragmentManager.popBackStack()
            return
        }

        try {
            this.videoId = videoId

            val renderersFactory = DefaultRenderersFactory(requireContext())
                .setExtensionRendererMode(DefaultRenderersFactory.EXTENSION_RENDERER_MODE_ON)

            player = ExoPlayer.Builder(requireContext(), renderersFactory)
                .build()
                .also { exoPlayer ->
                    playerView?.player = exoPlayer

                    val streamUrl = buildStreamUrl(videoId)
                    val mediaItem = MediaItem.fromUri(Uri.parse(streamUrl))
                    exoPlayer.setMediaItem(mediaItem)

                    // Fetch resume position and chapters (don't block playback if it fails)
                    lifecycleScope.launch {
                        try {
                            val meta = ApiClient.api.getVideoMeta(videoId)
                            if (meta.lastPositionSeconds > 0) {
                                exoPlayer.seekTo(meta.lastPositionSeconds * 1000L)
                            }
                            // Populate chapters and start chapter checking if non-empty
                            chapters = meta.chapters.orEmpty()
                            if (chapters.isNotEmpty()) {
                                startChapterChecking(exoPlayer)
                            }
                        } catch (e: Exception) {
                            Log.w(TAG, "Failed to fetch resume position/chapters: ${e.message}")
                        }
                    }

                    // Fetch available subtitle tracks (non-blocking)
                    lifecycleScope.launch {
                        try {
                            val subtitleResponse = ApiClient.api.getSubtitles(videoId)
                            subtitleTracks = subtitleResponse.tracks
                        } catch (e: Exception) {
                            Log.w(TAG, "Failed to fetch subtitles: ${e.message}")
                        }
                    }

                    // Fetch available quality formats (non-blocking)
                    lifecycleScope.launch {
                        try {
                            val formatsResponse = ApiClient.api.getFormats(videoId)
                            availableFormats = formatsResponse.formats
                        } catch (e: Exception) {
                            Log.w(TAG, "Failed to fetch quality formats: ${e.message}")
                        }
                    }

                    exoPlayer.playWhenReady = true
                    exoPlayer.prepare()

                    // Start periodic progress reporting
                    startProgressReporting(videoId, exoPlayer)

                    // Fetch SponsorBlock segments
                    lifecycleScope.launch {
                        try {
                            val response = ApiClient.api.getSponsorSegments(videoId)
                            sponsorSegments = response.segments
                            if (sponsorSegments.isNotEmpty()) {
                                startSkipChecking(exoPlayer)
                            }
                        } catch (e: Exception) {
                            Log.w(TAG, "Failed to fetch sponsor segments: ${e.message}")
                        }
                    }

                    // Detect manual seeks to suppress auto-skip
                    exoPlayer.addListener(object : Player.Listener {
                        override fun onPositionDiscontinuity(
                            oldPosition: Player.PositionInfo,
                            newPosition: Player.PositionInfo,
                            reason: Int
                        ) {
                            if (reason == Player.DISCONTINUITY_REASON_SEEK) {
                                userSeekedRecently = true
                                // Reset after 2 seconds
                                lifecycleScope.launch {
                                    delay(2000)
                                    userSeekedRecently = false
                                }
                            }
                        }
                    })
                }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start playback: ${e.message}")
            Toast.makeText(requireContext(), "Video unavailable", Toast.LENGTH_SHORT).show()
            parentFragmentManager.popBackStack()
        }
    }

    private fun startProgressReporting(videoId: String, exoPlayer: ExoPlayer) {
        progressJob = lifecycleScope.launch {
            while (isActive) {
                delay(10_000)
                if (exoPlayer.isPlaying) {
                    try {
                        ApiClient.api.reportProgress(
                            videoId,
                            ProgressBody(
                                positionSeconds = (exoPlayer.currentPosition / 1000).toInt(),
                                duration = (exoPlayer.duration / 1000).toInt()
                            )
                        )
                    } catch (e: Exception) {
                        Log.w(TAG, "Failed to report progress: ${e.message}")
                    }
                }
            }
        }
    }

    private fun startSkipChecking(exoPlayer: ExoPlayer) {
        skipCheckJob = lifecycleScope.launch {
            while (isActive) {
                delay(500) // Check every 500ms
                if (!exoPlayer.isPlaying || userSeekedRecently) continue

                val positionSec = exoPlayer.currentPosition / 1000.0
                for ((index, segment) in sponsorSegments.withIndex()) {
                    if (index in skippedSegmentIndices) continue
                    if (positionSec >= segment.start && positionSec < segment.end) {
                        // Skip to end of segment
                        val skipDuration = (segment.end - segment.start).toInt()
                        exoPlayer.seekTo((segment.end * 1000).toLong())
                        skippedSegmentIndices.add(index)

                        // Show toast
                        val label = when (segment.category) {
                            "sponsor" -> "sponsor"
                            "intro" -> "intro"
                            "outro" -> "outro"
                            else -> segment.category
                        }
                        Toast.makeText(
                            requireContext(),
                            "Skipped $label (${skipDuration}s)",
                            Toast.LENGTH_SHORT
                        ).show()
                        break
                    }
                }
            }
        }
    }

    /**
     * Poll player position every second, show chapter title overlay when chapter changes,
     * and fade the overlay out after 3 seconds of showing.
     */
    private fun startChapterChecking(exoPlayer: ExoPlayer) {
        chapterCheckJob = lifecycleScope.launch {
            var overlayHideJob: Job? = null
            while (isActive) {
                delay(1_000)
                val positionSec = exoPlayer.currentPosition / 1000.0
                val newIndex = chapters.indexOfLast { it.startTime <= positionSec }
                if (newIndex != currentChapterIndex && newIndex >= 0) {
                    currentChapterIndex = newIndex
                    val chapterTitle = chapters[newIndex].title

                    // Show overlay
                    chapterOverlay?.text = chapterTitle
                    chapterOverlay?.visibility = View.VISIBLE

                    // Cancel any pending hide and schedule a new one
                    overlayHideJob?.cancel()
                    overlayHideJob = launch {
                        delay(3_000)
                        chapterOverlay?.visibility = View.GONE
                    }
                }
            }
        }
    }

    /**
     * Seek to the start of the next chapter, if any.
     */
    fun jumpToNextChapter() {
        val exoPlayer = player ?: return
        if (chapters.isEmpty()) return
        val positionSec = exoPlayer.currentPosition / 1000.0
        val nextChapter = chapters.firstOrNull { it.startTime > positionSec + 1.0 }
        if (nextChapter != null) {
            exoPlayer.seekTo((nextChapter.startTime * 1000).toLong())
        }
    }

    /**
     * Seek to the start of the previous chapter (or beginning of current if near start).
     */
    fun jumpToPreviousChapter() {
        val exoPlayer = player ?: return
        if (chapters.isEmpty()) return
        val positionSec = exoPlayer.currentPosition / 1000.0
        // If more than 3 seconds into current chapter, go to its start; otherwise go to previous
        val currentIdx = chapters.indexOfLast { it.startTime <= positionSec }
        if (currentIdx > 0) {
            val currentChapterStart = chapters[currentIdx].startTime
            val targetChapter = if (positionSec - currentChapterStart > 3.0) {
                chapters[currentIdx]
            } else {
                chapters[currentIdx - 1]
            }
            exoPlayer.seekTo((targetChapter.startTime * 1000).toLong())
        } else if (currentIdx == 0) {
            exoPlayer.seekTo((chapters[0].startTime * 1000).toLong())
        }
    }

    /**
     * Show or hide the subtitle selection overlay.
     * If no subtitle tracks are available, shows a toast instead.
     */
    private fun toggleSubtitleOverlay() {
        if (subtitleOverlayVisible) {
            hideSubtitleOverlay()
        } else {
            showSubtitleOverlay()
        }
    }

    private fun showSubtitleOverlay() {
        val menu = subtitleOverlay ?: return
        menu.removeAllViews()

        // Build option list: "Off" + one entry per language
        val options: List<Pair<String?, String>> = listOf(null to "Off") +
            subtitleTracks.map { track -> track.lang to track.name }

        if (options.size == 1) {
            // Only "Off" — no tracks available
            Toast.makeText(requireContext(), "No subtitles available", Toast.LENGTH_SHORT).show()
            return
        }

        options.forEach { (lang, label) ->
            val isSelected = lang == currentSubtitleLang
            val item = TextView(requireContext()).apply {
                text = if (isSelected) "• $label" else "  $label"
                setTextColor(if (isSelected) Color.YELLOW else Color.WHITE)
                textSize = 18f
                setPadding(16, 12, 48, 12)
                setOnClickListener { selectSubtitle(lang) }
            }
            menu.addView(item)
        }

        menu.visibility = View.VISIBLE
        subtitleOverlayVisible = true
    }

    private fun hideSubtitleOverlay() {
        subtitleOverlay?.visibility = View.GONE
        subtitleOverlayVisible = false
    }

    /**
     * Apply a subtitle selection. Pass null to disable subtitles ("Off").
     * Rebuilds the MediaItem with or without a SubtitleConfiguration and re-prepares the player.
     */
    private fun selectSubtitle(lang: String?) {
        val exoPlayer = player ?: return
        val vid = videoId ?: return

        currentSubtitleLang = lang
        hideSubtitleOverlay()

        val streamUrl = buildStreamUrl(vid)
        val mediaItem = if (lang != null) {
            val subtitleUri = Uri.parse("$BACKEND_HOST/api/video/$vid/subtitles/$lang")
            val subtitleConfig = MediaItem.SubtitleConfiguration.Builder(subtitleUri)
                .setMimeType(MimeTypes.TEXT_VTT)
                .setLanguage(lang)
                .build()
            MediaItem.Builder()
                .setUri(Uri.parse(streamUrl))
                .setSubtitleConfigurations(listOf(subtitleConfig))
                .build()
        } else {
            MediaItem.fromUri(Uri.parse(streamUrl))
        }

        val resumePosition = exoPlayer.currentPosition
        exoPlayer.setMediaItem(mediaItem, resumePosition)
        exoPlayer.prepare()
        exoPlayer.playWhenReady = true

        val trackLabel = if (lang != null) {
            subtitleTracks.firstOrNull { it.lang == lang }?.name ?: lang
        } else {
            "Off"
        }
        Toast.makeText(requireContext(), "Subtitles: $trackLabel", Toast.LENGTH_SHORT).show()
    }

    private fun toggleSpeedOverlay() {
        speedOverlay?.let { overlay ->
            if (overlay.visibility == View.VISIBLE) {
                overlay.visibility = View.GONE
            } else {
                overlay.visibility = View.VISIBLE
                val currentIndex = SPEED_OPTIONS.indexOfFirst { it == currentSpeed }
                if (currentIndex >= 0) overlay.getChildAt(currentIndex)?.requestFocus()
            }
        }
    }

    private fun selectSpeed(speed: Float) {
        currentSpeed = speed
        player?.setPlaybackParameters(PlaybackParameters(speed))
        speedOverlay?.let { overlay ->
            for (i in 0 until overlay.childCount) {
                (overlay.getChildAt(i) as? TextView)?.setTextColor(
                    if (SPEED_OPTIONS[i] == speed) Color.parseColor("#e94560") else Color.WHITE
                )
            }
        }
        Toast.makeText(requireContext(), "Speed: ${speed}x", Toast.LENGTH_SHORT).show()
        speedOverlay?.visibility = View.GONE
    }

    /**
     * Build the stream URL for the current video, appending ?quality=<preset> when not "auto".
     */
    private fun buildStreamUrl(vid: String): String {
        val base = "$BACKEND_HOST/api/video/$vid/stream"
        return if (selectedQuality != "auto") "$base?quality=$selectedQuality" else base
    }

    private fun toggleQualityOverlay() {
        if (qualityOverlayVisible) {
            hideQualityOverlay()
        } else {
            showQualityOverlay()
        }
    }

    private fun showQualityOverlay() {
        val menu = qualityOverlay ?: return
        menu.removeAllViews()

        val formats = if (availableFormats.isNotEmpty()) availableFormats else listOf(
            com.shieldtube.api.VideoFormat("auto", "Auto (Best HDR)"),
            com.shieldtube.api.VideoFormat("4K_HDR", "4K HDR"),
            com.shieldtube.api.VideoFormat("4K", "4K"),
            com.shieldtube.api.VideoFormat("1080p", "1080p"),
            com.shieldtube.api.VideoFormat("720p", "720p"),
        )

        formats.forEach { format ->
            val isSelected = format.quality == selectedQuality
            val item = TextView(requireContext()).apply {
                text = if (isSelected) "• ${format.label}" else "  ${format.label}"
                setTextColor(if (isSelected) Color.parseColor("#e94560") else Color.WHITE)
                textSize = 18f
                setPadding(24, 12, 48, 12)
                setOnClickListener { selectQuality(format.quality) }
            }
            menu.addView(item)
        }

        menu.visibility = View.VISIBLE
        qualityOverlayVisible = true
    }

    private fun hideQualityOverlay() {
        qualityOverlay?.visibility = View.GONE
        qualityOverlayVisible = false
    }

    /**
     * Apply a quality selection and restart playback with the new stream URL.
     */
    private fun selectQuality(quality: String) {
        val exoPlayer = player ?: return
        val vid = videoId ?: return

        selectedQuality = quality
        hideQualityOverlay()

        val streamUrl = buildStreamUrl(vid)
        val mediaItem = if (currentSubtitleLang != null) {
            val subtitleUri = Uri.parse("$BACKEND_HOST/api/video/$vid/subtitles/$currentSubtitleLang")
            val subtitleConfig = MediaItem.SubtitleConfiguration.Builder(subtitleUri)
                .setMimeType(MimeTypes.TEXT_VTT)
                .setLanguage(currentSubtitleLang!!)
                .build()
            MediaItem.Builder()
                .setUri(Uri.parse(streamUrl))
                .setSubtitleConfigurations(listOf(subtitleConfig))
                .build()
        } else {
            MediaItem.fromUri(Uri.parse(streamUrl))
        }

        val resumePosition = exoPlayer.currentPosition
        exoPlayer.setMediaItem(mediaItem, resumePosition)
        exoPlayer.prepare()
        exoPlayer.playWhenReady = true

        val label = availableFormats.firstOrNull { it.quality == quality }?.label ?: quality
        Toast.makeText(requireContext(), "Quality: $label", Toast.LENGTH_SHORT).show()
    }

    private fun releasePlayer() {
        // Send final progress report
        videoId?.let { vid ->
            player?.let { p ->
                if (p.currentPosition > 0) {
                    lifecycleScope.launch {
                        try {
                            ApiClient.api.reportProgress(
                                vid,
                                ProgressBody(
                                    positionSeconds = (p.currentPosition / 1000).toInt(),
                                    duration = (p.duration / 1000).toInt()
                                )
                            )
                        } catch (e: Exception) {
                            Log.w(TAG, "Failed to send final progress: ${e.message}")
                        }
                    }
                }
            }
        }
        progressJob?.cancel()
        progressJob = null
        skipCheckJob?.cancel()
        skipCheckJob = null
        chapterCheckJob?.cancel()
        chapterCheckJob = null
        sponsorSegments = emptyList()
        skippedSegmentIndices.clear()
        userSeekedRecently = false
        chapters = emptyList()
        currentChapterIndex = -1
        chapterOverlay = null
        subtitleTracks = emptyList()
        currentSubtitleLang = null
        subtitleOverlay = null
        subtitleOverlayVisible = false
        currentSpeed = 1.0f
        speedOverlay?.visibility = View.GONE
        speedOverlay = null
        selectedQuality = "auto"
        availableFormats = emptyList()
        qualityOverlay?.visibility = View.GONE
        qualityOverlay = null
        qualityOverlayVisible = false
        player?.release()
        player = null
    }
}
