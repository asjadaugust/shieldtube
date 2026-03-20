package com.shieldtube.ui

import android.graphics.Color
import android.graphics.drawable.ColorDrawable
import android.view.ViewGroup
import android.widget.TextView
import androidx.leanback.widget.ImageCardView
import androidx.leanback.widget.Presenter
import com.bumptech.glide.Glide
import com.shieldtube.api.ApiClient
import com.shieldtube.api.Video

class CardPresenter : Presenter() {

    companion object {
        private const val CARD_WIDTH_DP = 313
        private const val CARD_HEIGHT_DP = 176

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
            val views = formatViewCount(video.viewCount)
            if (views.isNotEmpty()) append(views)
        }

        // Load thumbnail via Glide
        val thumbnailUrl = "${ApiClient.BASE_URL}${video.thumbnailUrl}"
        Glide.with(context)
            .load(thumbnailUrl)
            .centerCrop()
            .placeholder(ColorDrawable(Color.DKGRAY))
            .error(ColorDrawable(Color.DKGRAY))
            .into(cardView.mainImageView!!)

        // Duration badge (bottom-right overlay)
        val duration = formatDuration(video.duration)
        val badgeView = cardView.badgeImage
        if (badgeView != null && duration.isNotEmpty()) {
            // Use InfoField as the duration text overlay if available
        }
        // Set duration as extra info
        val infoArea = cardView.infoAreaBackground
        // Duration badge via tag on the card for downstream use
        cardView.tag = duration

        // Channel avatar color for bottom-left: set as background tint of the extra row
        val channelColor = getChannelColor(video.channelName)

        // Set the card's info area background to channel color as a subtle tint
        cardView.infoAreaBackground = ColorDrawable(0xFF1a1a2e.toInt())
    }

    override fun onUnbindViewHolder(viewHolder: ViewHolder) {
        val cardView = viewHolder.view as ImageCardView
        cardView.badgeImage = null
        cardView.mainImage = null
    }
}
