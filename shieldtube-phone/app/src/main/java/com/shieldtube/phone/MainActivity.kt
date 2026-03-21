package com.shieldtube.phone

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.hilt.navigation.compose.hiltViewModel
import com.shieldtube.phone.ui.navigation.AppNavigation
import com.shieldtube.phone.ui.setup.SetupScreen
import com.shieldtube.phone.ui.setup.SetupViewModel
import com.shieldtube.phone.ui.theme.ShieldTubeTheme
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
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
}
