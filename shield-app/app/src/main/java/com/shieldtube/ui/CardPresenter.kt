package com.shieldtube.ui

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ColorFilter
import android.graphics.Paint
import android.graphics.PixelFormat
import android.graphics.drawable.ColorDrawable
import android.graphics.drawable.Drawable
import android.graphics.drawable.LayerDrawable
import android.view.ViewGroup
import androidx.leanback.widget.ImageCardView
import androidx.leanback.widget.Presenter
import com.bumptech.glide.Glide
import com.shieldtube.api.ApiClient
import com.shieldtube.api.Video
import java.time.Instant
import java.time.temporal.ChronoUnit

class CardPresenter : Presenter() {

    companion object {
        private const val CARD_WIDTH_DP = 313
        private const val CARD_HEIGHT_DP = 176
        private const val PROGRESS_BAR_HEIGHT_DP = 4

        private const val NVIDIA_GREEN = 0xFF76B900.toInt()
        private const val PROGRESS_TRACK = 0x40FFFFFF.toInt()

        @JvmStatic
        fun formatDuration(seconds: Int?): String {
            if (seconds == null || seconds == 0) return ""
            val h = seconds / 3600
            val m = (seconds % 3600) / 60
            val s = seconds % 60
            return if (h > 0) {
                "%d:%02d:%02d".format(h, m, s)
            } else {
                "%d:%02d".format(m, s)
            }
        }

        @JvmStatic
        fun getChannelColor(channelName: String): Int {
            val index = Math.abs(channelName.hashCode()) % CHANNEL_COLORS.size
            return CHANNEL_COLORS[index]
        }

        @JvmStatic
        fun formatViewCount(count: Long?): String {
            if (count == null) return ""
            return when {
                count >= 1_000_000_000L -> "%.1fB views".format(count / 1_000_000_000.0)
                count >= 1_000_000L -> "%.1fM views".format(count / 1_000_000.0)
                count >= 1_000L -> "%.0fK views".format(count / 1_000.0)
                else -> "$count views"
            }
        }

        @JvmStatic
        fun formatRelativeTime(isoDate: String?): String {
            if (isoDate.isNullOrEmpty()) return ""
            return try {
                val then = Instant.parse(isoDate)
                val now = Instant.now()
                val minutes = ChronoUnit.MINUTES.between(then, now)
                when {
                    minutes < 60 -> "just now"
                    minutes < 1440 -> "${minutes / 60} hours ago"
                    minutes < 10080 -> "${minutes / 1440} days ago"
                    minutes < 43200 -> "${minutes / 10080} weeks ago"
                    minutes < 525600 -> "${minutes / 43200} months ago"
                    else -> "${minutes / 525600} years ago"
                }
            } catch (e: Exception) {
                ""
            }
        }

        // 8 predefined channel avatar colors
        private val CHANNEL_COLORS = intArrayOf(
            0xFFe53935.toInt(), // Red
            0xFF8E24AA.toInt(), // Purple
            0xFF1E88E5.toInt(), // Blue
            0xFF00897B.toInt(), // Teal
            0xFF43A047.toInt(), // Green
            0xFFFF8F00.toInt(), // Amber
            0xFFE91E63.toInt(), // Pink
            0xFF546E7A.toInt()  // Blue Grey
        )
    }

    override fun onCreateViewHolder(parent: ViewGroup): ViewHolder {
        val context = parent.context
        val density = context.resources.displayMetrics.density
        val cardWidthPx = (CARD_WIDTH_DP * density).toInt()
        val cardHeightPx = (CARD_HEIGHT_DP * density).toInt()

        val cardView = ImageCardView(context).apply {
            isFocusable = true
            isFocusableInTouchMode = true
            setMainImageDimensions(cardWidthPx, cardHeightPx)
        }
        return ViewHolder(cardView)
    }

    override fun onBindViewHolder(viewHolder: ViewHolder, item: Any?) {
        val video = item as? Video ?: return
        val cardView = viewHolder.view as ImageCardView
        val context = cardView.context

        // Title and content text
        cardView.titleText = video.title
        cardView.contentText = buildString {
            append(video.channelName)
            val relTime = formatRelativeTime(video.publishedAt)
            if (relTime.isNotEmpty()) {
                append(" · ")
                append(relTime)
            }
        }

        // Load thumbnail via Glide
        val thumbnailUrl = "${ApiClient.BASE_URL}${video.thumbnailUrl}"
        Glide.with(context)
            .load(thumbnailUrl)
            .centerCrop()
            .placeholder(ColorDrawable(Color.DKGRAY))
            .error(ColorDrawable(Color.DKGRAY))
            .into(cardView.mainImageView!!)

        // Duration badge
        val duration = formatDuration(video.duration)
        cardView.tag = duration

        // Info area background
        cardView.infoAreaBackground = ColorDrawable(0xFF1a1a2e.toInt())

        // Watch progress bar at bottom of thumbnail
        val pct = video.watchPercentage
        if (pct != null && pct > 0f) {
            val density = context.resources.displayMetrics.density
            val barHeightPx = (PROGRESS_BAR_HEIGHT_DP * density).toInt()
            val cardWidthPx = (CARD_WIDTH_DP * density).toInt()
            val fillPct = if (video.completed == true) 1f else pct

            val progressDrawable = ProgressBarDrawable(
                cardWidthPx, barHeightPx, fillPct, NVIDIA_GREEN, PROGRESS_TRACK
            )
            // Overlay the progress bar on the main image using a foreground
            cardView.mainImageView?.foreground = progressDrawable
        } else {
            cardView.mainImageView?.foreground = null
        }
    }

    override fun onUnbindViewHolder(viewHolder: ViewHolder) {
        val cardView = viewHolder.view as ImageCardView
        cardView.badgeImage = null
        cardView.mainImage = null
        cardView.mainImageView?.foreground = null
    }

    /**
     * A simple drawable that renders a progress bar at the bottom of the view.
     */
    private class ProgressBarDrawable(
        private val viewWidth: Int,
        private val barHeight: Int,
        private val percentage: Float,
        private val fillColor: Int,
        private val trackColor: Int
    ) : Drawable() {
        private val trackPaint = Paint().apply { color = trackColor; style = Paint.Style.FILL }
        private val fillPaint = Paint().apply { color = fillColor; style = Paint.Style.FILL }

        override fun draw(canvas: Canvas) {
            val b = bounds
            val top = (b.bottom - barHeight).toFloat()
            // Track
            canvas.drawRect(b.left.toFloat(), top, b.right.toFloat(), b.bottom.toFloat(), trackPaint)
            // Fill
            val fillWidth = b.left + (b.width() * percentage)
            canvas.drawRect(b.left.toFloat(), top, fillWidth, b.bottom.toFloat(), fillPaint)
        }

        override fun setAlpha(alpha: Int) {}
        override fun setColorFilter(colorFilter: ColorFilter?) {}
        override fun getOpacity(): Int = PixelFormat.TRANSLUCENT
    }
}
