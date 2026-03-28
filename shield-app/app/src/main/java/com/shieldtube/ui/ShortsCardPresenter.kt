package com.shieldtube.ui

import android.graphics.Color
import android.graphics.drawable.ColorDrawable
import android.view.ViewGroup
import androidx.leanback.widget.ImageCardView
import androidx.leanback.widget.Presenter
import com.bumptech.glide.Glide
import com.shieldtube.api.ApiClient
import com.shieldtube.api.Video

class ShortsCardPresenter : Presenter() {

    companion object {
        private const val CARD_WIDTH_DP = 120
        private const val CARD_HEIGHT_DP = 213  // 9:16 portrait ratio
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

        cardView.titleText = video.title
        cardView.contentText = video.channelName
        cardView.infoAreaBackground = ColorDrawable(0xFF1a1a2e.toInt())

        val thumbnailUrl = "${ApiClient.BASE_URL}${video.thumbnailUrl}"
        Glide.with(context)
            .load(thumbnailUrl)
            .centerCrop()
            .placeholder(ColorDrawable(Color.DKGRAY))
            .error(ColorDrawable(Color.DKGRAY))
            .into(cardView.mainImageView!!)
    }

    override fun onUnbindViewHolder(viewHolder: ViewHolder) {
        val cardView = viewHolder.view as ImageCardView
        cardView.badgeImage = null
        cardView.mainImage = null
    }
}
