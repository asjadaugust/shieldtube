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
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.TextView
import android.widget.Toast
import com.shieldtube.R
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackParameters
import androidx.media3.common.MimeTypes
import androidx.media3.common.Player
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.DefaultRenderersFactory
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.MergingMediaSource
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import androidx.media3.exoplayer.source.SingleSampleMediaSource
import androidx.media3.extractor.DefaultExtractorsFactory
import androidx.media3.ui.PlayerView
import com.shieldtube.api.ApiClient
import com.shieldtube.api.Chapter
import com.shieldtube.api.PlaybackStatusBody
import com.shieldtube.api.ProgressBody
import com.shieldtube.api.SponsorSegment
import com.shieldtube.api.SubtitleTrack
import com.shieldtube.api.VideoFormat
import kotlinx.coroutines.*

class PlaybackFragment : Fragment() {

    companion object {
        const val BACKEND_HOST = "https://192.168.0.26:9443"
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
    private var subtitleScrollView: android.widget.ScrollView? = null // legacy, unused
    private var subtitlePopupView: FrameLayout? = null
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

    // Remote control state
    private var commandPollJob: Job? = null
    private var statusReportJob: Job? = null

    private var controlsHideJob: Job? = null
    private val CONTROLS_HIDE_DELAY = 5000L
    private val QUICK_SEEK_HIDE_DELAY = 1000L
    private val SEEK_STEP_MS = 15_000L

    // Custom controls views
    private var quickSeekBar: View? = null
    private var quickSeekSeekbar: SeekBar? = null
    private var quickSeekPosition: TextView? = null
    private var quickSeekDuration: TextView? = null
    private var fullControls: View? = null
    private var controlsSeekbar: SeekBar? = null
    private var controlsPosition: TextView? = null
    private var controlsDuration: TextView? = null
    private var controlsTitle: TextView? = null
    private var controlsChannel: TextView? = null
    private var btnPlayPause: ImageButton? = null
    private var seekBarUpdateJob: Job? = null
    private var quickSeekHideJob: Job? = null
    private var currentTitle: String = ""
    private var currentChannel: String = ""

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
            useController = false // We use our own custom controls
            // Style subtitles: centered, semi-transparent background
            subtitleView?.apply {
                val style = androidx.media3.ui.CaptionStyleCompat(
                    Color.WHITE,                           // foreground
                    Color.parseColor("#80000000"),          // background (50% opacity black)
                    Color.TRANSPARENT,                      // window
                    androidx.media3.ui.CaptionStyleCompat.EDGE_TYPE_NONE,
                    Color.TRANSPARENT,                      // edge color
                    null                                    // typeface
                )
                setApplyEmbeddedStyles(false)
                setApplyEmbeddedFontSizes(false)
                setStyle(style)
                setFixedTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, 18f)
                setBottomPaddingFraction(0.08f)
            }
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

        // Subtitle selection overlay: small centered popup
        val subtitleMenu = LinearLayout(requireContext()).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
        }
        subtitleOverlay = subtitleMenu
        val subtitlePopup = FrameLayout(requireContext()).apply {
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.CENTER
            )
            setBackgroundColor(Color.parseColor("#CC000000"))
            setPadding(48, 32, 48, 32)
            visibility = View.GONE
            addView(subtitleMenu)
        }
        subtitleScrollView = null
        subtitlePopupView = subtitlePopup

        val container = object : FrameLayout(requireContext()) {
            override fun dispatchKeyEvent(event: KeyEvent): Boolean {
                if (event.action == KeyEvent.ACTION_DOWN) {
                    if (handleKeyDown(event.keyCode, event)) return true
                }
                return super.dispatchKeyEvent(event)
            }
        }.apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
            isFocusable = true
            isFocusableInTouchMode = true
            addView(playerView)
            addView(overlay)
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

            // Custom controls overlay (YouTube TV style)
            val controlsOverlay = inflater.inflate(R.layout.player_controls, this, false)
            addView(controlsOverlay)
            quickSeekBar = controlsOverlay.findViewById(R.id.quick_seek_bar)
            quickSeekSeekbar = controlsOverlay.findViewById(R.id.quick_seek_seekbar)
            quickSeekPosition = controlsOverlay.findViewById(R.id.quick_seek_position)
            quickSeekDuration = controlsOverlay.findViewById(R.id.quick_seek_duration)
            fullControls = controlsOverlay.findViewById(R.id.full_controls)
            controlsSeekbar = controlsOverlay.findViewById(R.id.controls_seekbar)
            controlsPosition = controlsOverlay.findViewById(R.id.controls_position)
            controlsDuration = controlsOverlay.findViewById(R.id.controls_duration)
            controlsTitle = controlsOverlay.findViewById(R.id.controls_title)
            controlsChannel = controlsOverlay.findViewById(R.id.controls_channel)
            btnPlayPause = controlsOverlay.findViewById(R.id.btn_play_pause)

            // Wire up control buttons
            btnPlayPause?.setOnClickListener { player?.let { p -> if (p.isPlaying) p.pause() else p.play() }; updatePlayPauseIcon() }
            controlsOverlay.findViewById<ImageButton>(R.id.btn_rewind)?.setOnClickListener {
                player?.let { p -> p.seekTo(maxOf(p.currentPosition - SEEK_STEP_MS, 0)) }
            }
            controlsOverlay.findViewById<ImageButton>(R.id.btn_forward)?.setOnClickListener {
                player?.let { p -> p.seekTo(minOf(p.currentPosition + SEEK_STEP_MS, p.duration)) }
            }
            controlsOverlay.findViewById<ImageButton>(R.id.btn_prev_chapter)?.setOnClickListener { jumpToPreviousChapter() }
            controlsOverlay.findViewById<TextView>(R.id.btn_cc)?.setOnClickListener { toggleSubtitleOverlay() }
            controlsOverlay.findViewById<ImageButton>(R.id.btn_next_chapter)?.setOnClickListener { jumpToNextChapter() }

            // Add subtitle popup ON TOP of controls
            addView(subtitlePopup)
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

                    // Use ProgressiveMediaSource with constant-bitrate seeking
                    // so ExoPlayer can seek in fragmented MP4 streams (empty_moov)
                    val dataSourceFactory = DefaultHttpDataSource.Factory()
                        .setDefaultRequestProperties(mapOf(
                            "X-ShieldTube-Secret" to com.shieldtube.BuildConfig.API_SECRET
                        ))
                    val extractorsFactory = DefaultExtractorsFactory()
                        .setConstantBitrateSeekingEnabled(true)
                    val mediaSource = ProgressiveMediaSource.Factory(
                        dataSourceFactory, extractorsFactory
                    ).createMediaSource(mediaItem)
                    exoPlayer.setMediaSource(mediaSource)

                    // Fetch resume position and chapters (don't block playback if it fails)
                    lifecycleScope.launch {
                        try {
                            val meta = ApiClient.api.getVideoMeta(videoId)
                            currentTitle = meta.title
                            currentChannel = meta.channelName
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

                    // Fetch video title for remote status reporting
                    lifecycleScope.launch {
                        try {
                            val meta = ApiClient.api.getVideoMeta(videoId)
                            currentTitle = meta.title
                        } catch (_: Exception) {}
                    }

                    // Remote control: poll for commands from phone (every 500ms)
                    startCommandPolling(exoPlayer)

                    // Remote control: report playback status to phone (every 1s)
                    startStatusReporting(videoId, exoPlayer)

                    // Report play/pause/completed events
                    exoPlayer.addListener(object : Player.Listener {
                        override fun onIsPlayingChanged(isPlaying: Boolean) {
                            val vid = videoId ?: return
                            lifecycleScope.launch {
                                try {
                                    ApiClient.api.reportProgress(vid, ProgressBody(
                                        positionSeconds = (exoPlayer.currentPosition / 1000).toInt(),
                                        duration = (exoPlayer.duration / 1000).toInt(),
                                        event = if (isPlaying) "playing" else "paused",
                                        speed = currentSpeed
                                    ))
                                } catch (_: Exception) {}
                            }
                        }

                        override fun onPlaybackStateChanged(playbackState: Int) {
                            if (playbackState == Player.STATE_ENDED) {
                                val vid = videoId ?: return
                                lifecycleScope.launch {
                                    try {
                                        ApiClient.api.reportProgress(vid, ProgressBody(
                                            positionSeconds = (exoPlayer.duration / 1000).toInt(),
                                            duration = (exoPlayer.duration / 1000).toInt(),
                                            event = "completed",
                                            speed = currentSpeed
                                        ))
                                    } catch (_: Exception) {}
                                }
                            }
                        }
                    })

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
                                duration = (exoPlayer.duration / 1000).toInt(),
                                event = "playing",
                                speed = currentSpeed
                            )
                        )
                    } catch (e: Exception) {
                        Log.w(TAG, "Failed to report progress: ${e.message}")
                    }
                }
            }
        }
    }

    private fun startCommandPolling(exoPlayer: ExoPlayer) {
        commandPollJob = lifecycleScope.launch {
            while (isActive) {
                delay(500)
                try {
                    val response = ApiClient.api.getPlaybackCommands()
                    for (cmd in response.commands) {
                        when (cmd.action) {
                            "pause" -> exoPlayer.pause()
                            "resume" -> exoPlayer.play()
                            "toggle" -> if (exoPlayer.isPlaying) exoPlayer.pause() else exoPlayer.play()
                            "seek" -> exoPlayer.seekTo((cmd.value?.toDoubleOrNull()?.times(1000))?.toLong() ?: 0)
                            "speed" -> {
                                val newSpeed = cmd.value?.toFloatOrNull() ?: 1f
                                currentSpeed = newSpeed
                                exoPlayer.setPlaybackParameters(PlaybackParameters(newSpeed))
                            }
                            "play" -> {
                                val newVideoId = cmd.value
                                if (newVideoId != null && newVideoId != videoId) {
                                    switchToVideo(newVideoId)
                                    return@launch // Stop this loop; initPlayer starts a new one
                                }
                            }
                        }
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "Failed to poll commands: ${e.message}")
                }
            }
        }
    }

    private fun startStatusReporting(videoId: String, exoPlayer: ExoPlayer) {
        statusReportJob = lifecycleScope.launch {
            while (isActive) {
                delay(1000)
                try {
                    ApiClient.api.updatePlaybackStatus(PlaybackStatusBody(
                        videoId = videoId,
                        title = currentTitle,
                        positionMs = exoPlayer.currentPosition,
                        durationMs = exoPlayer.duration,
                        isPlaying = exoPlayer.isPlaying,
                        speed = exoPlayer.playbackParameters.speed
                    ))
                } catch (e: Exception) {
                    Log.w(TAG, "Failed to report status: ${e.message}")
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

        // Build option list: "Off" + original language, English, Spanish only
        val preferredLangs = setOf("en-orig", "en", "es")
        val filteredTracks = subtitleTracks.filter { it.lang in preferredLangs }
        // Sort: original first, then English, then Spanish
        val sortedTracks = filteredTracks.sortedBy { track ->
            when {
                track.lang.contains("orig") -> 0
                track.lang == "en" -> 1
                track.lang == "es" -> 2
                else -> 3
            }
        }
        val options: List<Pair<String?, String>> = listOf(null to "Off") +
            sortedTracks.map { track -> track.lang to track.name }

        if (options.size == 1) {
            // Only "Off" — no tracks available
            Toast.makeText(requireContext(), "No subtitles available", Toast.LENGTH_SHORT).show()
            return
        }

        options.forEachIndexed { index, (lang, label) ->
            val isSelected = lang == currentSubtitleLang
            val item = TextView(requireContext()).apply {
                text = if (isSelected) "● $label" else label
                setTextColor(if (isSelected) Color.parseColor("#76B900") else Color.WHITE)
                textSize = 16f
                setPadding(48, 16, 48, 16)
                gravity = Gravity.CENTER
                isFocusable = true
                isFocusableInTouchMode = true
                setBackgroundResource(android.R.drawable.list_selector_background)
                setOnClickListener { selectSubtitle(lang) }
                setOnKeyListener { _, keyCode, event ->
                    if (event.action == KeyEvent.ACTION_DOWN && keyCode == KeyEvent.KEYCODE_DPAD_CENTER) {
                        selectSubtitle(lang)
                        true
                    } else if (event.action == KeyEvent.ACTION_DOWN && keyCode == KeyEvent.KEYCODE_BACK) {
                        hideSubtitleOverlay()
                        true
                    } else {
                        false
                    }
                }
            }
            menu.addView(item)
        }

        subtitlePopupView?.visibility = View.VISIBLE
        subtitleOverlayVisible = true
        // Hide full controls so they don't compete for focus
        fullControls?.visibility = View.GONE
        // Focus the first item so D-pad navigation works
        menu.getChildAt(0)?.requestFocus()
    }

    private fun hideSubtitleOverlay() {
        subtitlePopupView?.visibility = View.GONE
        subtitleOverlayVisible = false
        view?.requestFocus()
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

        val resumePosition = exoPlayer.currentPosition

        // Use the same data source factory with API secret for all requests
        val dataSourceFactory = DefaultHttpDataSource.Factory()
            .setDefaultRequestProperties(mapOf(
                "X-ShieldTube-Secret" to com.shieldtube.BuildConfig.API_SECRET
            ))

        val streamUrl = buildStreamUrl(vid)
        val mediaItem = MediaItem.fromUri(Uri.parse(streamUrl))
        val extractorsFactory = DefaultExtractorsFactory()
            .setConstantBitrateSeekingEnabled(true)
        val videoSource = ProgressiveMediaSource.Factory(dataSourceFactory, extractorsFactory)
            .createMediaSource(mediaItem)

        if (lang != null) {
            val subtitleUri = Uri.parse("$BACKEND_HOST/api/video/$vid/subtitles/$lang")
            val subtitleConfig = MediaItem.SubtitleConfiguration.Builder(subtitleUri)
                .setMimeType(MimeTypes.TEXT_VTT)
                .setLanguage(lang)
                .setSelectionFlags(C.SELECTION_FLAG_DEFAULT)
                .build()
            val subtitleSource = SingleSampleMediaSource.Factory(dataSourceFactory)
                .createMediaSource(subtitleConfig, C.TIME_UNSET)
            val mergedSource = MergingMediaSource(videoSource, subtitleSource)
            exoPlayer.setMediaSource(mergedSource, resumePosition)
        } else {
            exoPlayer.setMediaSource(videoSource, resumePosition)
        }

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

        val resumePosition = exoPlayer.currentPosition
        val dataSourceFactory = DefaultHttpDataSource.Factory()
            .setDefaultRequestProperties(mapOf(
                "X-ShieldTube-Secret" to com.shieldtube.BuildConfig.API_SECRET
            ))
        val streamUrl = buildStreamUrl(vid)
        val mediaItem = MediaItem.fromUri(Uri.parse(streamUrl))
        val extractorsFactory = DefaultExtractorsFactory()
            .setConstantBitrateSeekingEnabled(true)
        val videoSource = ProgressiveMediaSource.Factory(dataSourceFactory, extractorsFactory)
            .createMediaSource(mediaItem)

        if (currentSubtitleLang != null) {
            val subtitleUri = Uri.parse("$BACKEND_HOST/api/video/$vid/subtitles/$currentSubtitleLang")
            val subtitleConfig = MediaItem.SubtitleConfiguration.Builder(subtitleUri)
                .setMimeType(MimeTypes.TEXT_VTT)
                .setLanguage(currentSubtitleLang!!)
                .setSelectionFlags(C.SELECTION_FLAG_DEFAULT)
                .build()
            val subtitleSource = SingleSampleMediaSource.Factory(dataSourceFactory)
                .createMediaSource(subtitleConfig, C.TIME_UNSET)
            exoPlayer.setMediaSource(MergingMediaSource(videoSource, subtitleSource), resumePosition)
        } else {
            exoPlayer.setMediaSource(videoSource, resumePosition)
        }
        exoPlayer.prepare()
        exoPlayer.playWhenReady = true

        val label = availableFormats.firstOrNull { it.quality == quality }?.label ?: quality
        Toast.makeText(requireContext(), "Quality: $label", Toast.LENGTH_SHORT).show()
    }

    private fun handleKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        // Priority 1: close any open overlay
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            if (qualityOverlayVisible) { hideQualityOverlay(); return true }
            if (subtitleOverlayVisible) { hideSubtitleOverlay(); return true }
            if (speedOverlay?.visibility == View.VISIBLE) { speedOverlay?.visibility = View.GONE; return true }
            if (fullControls?.visibility == View.VISIBLE) { hideFullControls(); return true }
            if (quickSeekBar?.visibility == View.VISIBLE) { hideQuickSeek(); return true }
            return false
        }

        // Play/Pause buttons (remote media keys)
        if (keyCode == KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE ||
            keyCode == KeyEvent.KEYCODE_MEDIA_PLAY ||
            keyCode == KeyEvent.KEYCODE_MEDIA_PAUSE
        ) {
            player?.let { p -> if (p.isPlaying) p.pause() else p.play() }
            updatePlayPauseIcon()
            showFullControlsWithAutoHide()
            return true
        }

        // Center/Enter: confirm seek position, show full controls, or toggle play/pause
        if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER) {
            if (quickSeekBar?.visibility == View.VISIBLE) {
                // Confirm seek position and resume
                hideQuickSeek()
                player?.play()
                return true
            }
            if (fullControls?.visibility != View.VISIBLE) {
                showFullControlsWithAutoHide()
                btnPlayPause?.requestFocus()
            } else {
                player?.let { p -> if (p.isPlaying) p.pause() else p.play() }
                updatePlayPauseIcon()
                scheduleControlsHide()
            }
            return true
        }

        // Long-press actions
        if (event.isLongPress) {
            return when (keyCode) {
                KeyEvent.KEYCODE_DPAD_RIGHT -> { jumpToNextChapter(); true }
                KeyEvent.KEYCODE_DPAD_LEFT -> { jumpToPreviousChapter(); true }
                KeyEvent.KEYCODE_DPAD_DOWN -> { toggleSubtitleOverlay(); true }
                KeyEvent.KEYCODE_DPAD_UP -> { toggleSpeedOverlay(); true }
                else -> false
            }
        }

        // Menu key: quality overlay
        if (keyCode == KeyEvent.KEYCODE_MENU) {
            toggleQualityOverlay()
            return true
        }

        // D-pad left/right when full controls visible: let focus navigation work
        if (fullControls?.visibility == View.VISIBLE) {
            if (keyCode == KeyEvent.KEYCODE_DPAD_UP || keyCode == KeyEvent.KEYCODE_DPAD_DOWN ||
                keyCode == KeyEvent.KEYCODE_DPAD_LEFT || keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) {
                scheduleControlsHide()
                return false // Let Android handle focus navigation
            }
        }

        // D-pad left/right (no controls): quick seek ±15s
        if (keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) {
            player?.let { p -> p.seekTo(minOf(p.currentPosition + SEEK_STEP_MS, p.duration)) }
            showQuickSeek()
            return true
        }
        if (keyCode == KeyEvent.KEYCODE_DPAD_LEFT) {
            player?.let { p -> p.seekTo(maxOf(p.currentPosition - SEEK_STEP_MS, 0)) }
            showQuickSeek()
            return true
        }

        // D-pad up (no controls): show full controls
        if (keyCode == KeyEvent.KEYCODE_DPAD_UP) {
            showFullControlsWithAutoHide()
            controlsSeekbar?.requestFocus()
            return true
        }

        return false
    }

    // --- Quick Seek Bar (D-pad left/right, auto-hide) ---

    private fun showQuickSeek() {
        fullControls?.visibility = View.GONE
        quickSeekBar?.visibility = View.VISIBLE
        player?.pause()
        updateSeekBarPositions()
    }

    private fun hideQuickSeek() {
        quickSeekBar?.visibility = View.GONE
        quickSeekHideJob?.cancel()
        view?.requestFocus()
    }

    // --- Full Controls (Center button, auto-hide) ---

    private fun showFullControlsWithAutoHide() {
        quickSeekBar?.visibility = View.GONE
        fullControls?.visibility = View.VISIBLE
        controlsTitle?.text = currentTitle
        controlsChannel?.text = currentChannel
        updatePlayPauseIcon()
        updateSeekBarPositions()
        startSeekBarUpdates()
        scheduleControlsHide()
    }

    private fun hideFullControls() {
        fullControls?.visibility = View.GONE
        controlsHideJob?.cancel()
        seekBarUpdateJob?.cancel()
        view?.requestFocus()
    }

    private fun scheduleControlsHide() {
        controlsHideJob?.cancel()
        controlsHideJob = lifecycleScope.launch {
            val timeout = if (player?.isPlaying == true) CONTROLS_HIDE_DELAY else CONTROLS_HIDE_DELAY * 2
            delay(timeout)
            hideControls()
        }
    }

    private fun hideControls() {
        hideFullControls()
        hideQuickSeek()
    }

    private fun updatePlayPauseIcon() {
        val isPlaying = player?.isPlaying == true
        btnPlayPause?.setImageResource(
            if (isPlaying) android.R.drawable.ic_media_pause
            else android.R.drawable.ic_media_play
        )
    }

    private fun updateSeekBarPositions() {
        val p = player ?: return
        val pos = p.currentPosition
        val dur = if (p.duration > 0) p.duration else 1L
        val progress = ((pos * 1000) / dur).toInt()
        val posText = formatTimeMs(pos)
        val durText = formatTimeMs(dur)

        quickSeekSeekbar?.progress = progress
        quickSeekPosition?.text = posText
        quickSeekDuration?.text = durText

        controlsSeekbar?.progress = progress
        controlsPosition?.text = posText
        controlsDuration?.text = durText
    }

    private fun startSeekBarUpdates() {
        seekBarUpdateJob?.cancel()
        seekBarUpdateJob = lifecycleScope.launch {
            while (isActive) {
                updateSeekBarPositions()
                updatePlayPauseIcon()
                delay(500)
            }
        }
    }

    private fun formatTimeMs(ms: Long): String {
        val totalSec = (ms / 1000).toInt()
        val h = totalSec / 3600
        val m = (totalSec % 3600) / 60
        val s = totalSec % 60
        return if (h > 0) "%d:%02d:%02d".format(h, m, s) else "%d:%02d".format(m, s)
    }

    private fun releasePlayer() {
        // Send final progress report and clear remote playback status
        videoId?.let { vid ->
            player?.let { p ->
                if (p.currentPosition > 0) {
                    lifecycleScope.launch {
                        try {
                            ApiClient.api.reportProgress(
                                vid,
                                ProgressBody(
                                    positionSeconds = (p.currentPosition / 1000).toInt(),
                                    duration = (p.duration / 1000).toInt(),
                                    event = "abandoned",
                                    speed = currentSpeed
                                )
                            )
                        } catch (e: Exception) {
                            Log.w(TAG, "Failed to send final progress: ${e.message}")
                        }
                    }
                }
            }
        }
        // Clear remote playback status so phone exits remote control mode
        lifecycleScope.launch {
            try {
                ApiClient.api.clearPlaybackStatus()
            } catch (e: Exception) {
                Log.w(TAG, "Failed to clear playback status: ${e.message}")
            }
        }
        commandPollJob?.cancel()
        commandPollJob = null
        statusReportJob?.cancel()
        statusReportJob = null
        progressJob?.cancel()
        progressJob = null
        skipCheckJob?.cancel()
        skipCheckJob = null
        chapterCheckJob?.cancel()
        chapterCheckJob = null
        controlsHideJob?.cancel()
        controlsHideJob = null
        quickSeekHideJob?.cancel()
        quickSeekHideJob = null
        seekBarUpdateJob?.cancel()
        seekBarUpdateJob = null
        sponsorSegments = emptyList()
        skippedSegmentIndices.clear()
        userSeekedRecently = false
        chapters = emptyList()
        currentChapterIndex = -1
        chapterOverlay = null
        subtitleTracks = emptyList()
        currentSubtitleLang = null
        subtitleOverlay = null
        subtitleScrollView = null
        subtitlePopupView = null
        subtitleOverlayVisible = false
        currentTitle = ""
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

    /**
     * Switch to a new video in-place without fragment navigation.
     * Skips clearPlaybackStatus to avoid a status gap for the phone remote.
     */
    private fun switchToVideo(newVideoId: String) {
        // Cancel all background jobs
        commandPollJob?.cancel()
        statusReportJob?.cancel()
        progressJob?.cancel()
        skipCheckJob?.cancel()
        chapterCheckJob?.cancel()
        controlsHideJob?.cancel()
        quickSeekHideJob?.cancel()
        seekBarUpdateJob?.cancel()

        // Reset state
        sponsorSegments = emptyList()
        skippedSegmentIndices.clear()
        userSeekedRecently = false
        chapters = emptyList()
        currentChapterIndex = -1
        subtitleTracks = emptyList()
        currentSubtitleLang = null
        currentTitle = ""
        currentSpeed = 1.0f
        selectedQuality = "auto"
        availableFormats = emptyList()

        // Hide overlays
        hideControls()
        subtitlePopupView?.visibility = View.GONE
        subtitleOverlayVisible = false
        speedOverlay?.visibility = View.GONE
        qualityOverlay?.visibility = View.GONE
        qualityOverlayVisible = false

        // Release old player
        player?.release()
        player = null

        // Set new video ID and reinitialize
        arguments = Bundle().apply { putString(ARG_VIDEO_ID, newVideoId) }
        initPlayer()
    }
}
