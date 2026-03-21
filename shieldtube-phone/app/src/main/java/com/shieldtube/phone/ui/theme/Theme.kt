package com.shieldtube.phone.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val NvidiaGreen = Color(0xFF76B900)
private val DarkBackground = Color(0xFF121212)
private val DarkSurface = Color(0xFF1E1E1E)
private val DarkSurfaceVariant = Color(0xFF2A2A2A)
private val OnSurfaceVariantGray = Color(0xFFB0B0B0)

private val ShieldTubeDarkColorScheme = darkColorScheme(
    primary = NvidiaGreen,
    background = DarkBackground,
    surface = DarkSurface,
    surfaceVariant = DarkSurfaceVariant,
    onPrimary = DarkBackground,
    onBackground = Color.White,
    onSurface = Color.White,
    onSurfaceVariant = OnSurfaceVariantGray,
)

@Composable
fun ShieldTubeTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = ShieldTubeDarkColorScheme,
        typography = ShieldTubeTypography,
        content = content,
    )
}
