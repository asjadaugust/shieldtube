package com.shieldtube.player

import android.net.Uri
import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.DefaultRenderersFactory
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import com.shieldtube.api.ApiClient
import com.shieldtube.api.ProgressBody
import com.shieldtube.api.SponsorSegment
import kotlinx.coroutines.*

class PlaybackFragment : Fragment() {

    companion object {
        const val BACKEND_HOST = "http://192.168.1.100:8080"
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

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        playerView = PlayerView(requireContext()).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
        }
        return playerView!!
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

        this.videoId = videoId

        val renderersFactory = DefaultRenderersFactory(requireContext())
            .setExtensionRendererMode(DefaultRenderersFactory.EXTENSION_RENDERER_MODE_ON)

        player = ExoPlayer.Builder(requireContext(), renderersFactory)
            .build()
            .also { exoPlayer ->
                playerView?.player = exoPlayer

                val streamUrl = "$BACKEND_HOST/api/video/$videoId/stream"
                val mediaItem = MediaItem.fromUri(Uri.parse(streamUrl))
                exoPlayer.setMediaItem(mediaItem)

                // Fetch resume position (don't block playback if it fails)
                lifecycleScope.launch {
                    try {
                        val meta = ApiClient.api.getVideoMeta(videoId)
                        if (meta.lastPositionSeconds > 0) {
                            exoPlayer.seekTo(meta.lastPositionSeconds * 1000L)
                        }
                    } catch (e: Exception) {
                        Log.w(TAG, "Failed to fetch resume position: ${e.message}")
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
        sponsorSegments = emptyList()
        skippedSegmentIndices.clear()
        userSeekedRecently = false
        player?.release()
        player = null
    }
}
