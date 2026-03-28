package com.shieldtube.phone

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.lifecycleScope
import com.shieldtube.phone.data.api.EnqueueBody
import com.shieldtube.phone.data.api.ShieldTubeApi
import com.shieldtube.phone.ui.navigation.AppNavigation
import com.shieldtube.phone.ui.setup.SetupScreen
import com.shieldtube.phone.ui.setup.SetupViewModel
import com.shieldtube.phone.ui.theme.ShieldTubeTheme
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject lateinit var api: ShieldTubeApi

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Handle share intent from YouTube
        if (intent?.action == Intent.ACTION_SEND && intent.type == "text/plain") {
            handleShareIntent(intent)
        }

        setContent {
            ShieldTubeTheme {
                val viewModel: SetupViewModel = hiltViewModel()
                val isConfigured by viewModel.isConfigured.collectAsState()

                if (isConfigured) {
                    AppNavigation()
                } else {
                    SetupScreen(onConfigured = { /* isConfigured will update via Flow */ })
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        if (intent.action == Intent.ACTION_SEND && intent.type == "text/plain") {
            handleShareIntent(intent)
        }
    }

    private fun handleShareIntent(intent: Intent) {
        val text = intent.getStringExtra(Intent.EXTRA_TEXT) ?: return
        val videoId = extractVideoId(text) ?: run {
            Toast.makeText(this, "Could not extract video ID", Toast.LENGTH_SHORT).show()
            return
        }

        Toast.makeText(this, "Queuing download: $videoId", Toast.LENGTH_SHORT).show()

        lifecycleScope.launch {
            try {
                val result = api.enqueueServerDownload(EnqueueBody(videoId))
                val msg = when (result.status) {
                    "already_cached" -> "Already downloaded"
                    "ok" -> "Download queued!"
                    else -> "Queued: ${result.status}"
                }
                Toast.makeText(this@MainActivity, msg, Toast.LENGTH_SHORT).show()
            } catch (e: Exception) {
                Toast.makeText(this@MainActivity, "Failed: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun extractVideoId(text: String): String? {
        // Match youtube.com/watch?v=ID, youtu.be/ID, youtube.com/shorts/ID
        val patterns = listOf(
            Regex("""youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})"""),
            Regex("""youtu\.be/([a-zA-Z0-9_-]{11})"""),
            Regex("""youtube\.com/shorts/([a-zA-Z0-9_-]{11})"""),
            Regex("""youtube\.com/embed/([a-zA-Z0-9_-]{11})"""),
        )
        for (pattern in patterns) {
            pattern.find(text)?.groupValues?.get(1)?.let { return it }
        }
        return null
    }
}
