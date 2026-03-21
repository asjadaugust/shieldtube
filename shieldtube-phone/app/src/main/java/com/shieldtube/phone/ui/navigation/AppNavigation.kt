package com.shieldtube.phone.ui.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.shieldtube.phone.ui.downloads.DownloadsScreen
import com.shieldtube.phone.ui.downloads.DownloadsViewModel
import com.shieldtube.phone.ui.home.HomeScreen
import com.shieldtube.phone.ui.home.HomeViewModel
import com.shieldtube.phone.ui.player.PlayerScreen
import com.shieldtube.phone.ui.player.PlayerViewModel
import com.shieldtube.phone.ui.search.SearchScreen
import com.shieldtube.phone.ui.search.SearchViewModel
import com.shieldtube.phone.ui.settings.SettingsScreen
import com.shieldtube.phone.ui.settings.SettingsViewModel

enum class Screen(
    val route: String,
    val label: String,
    val icon: ImageVector,
) {
    Home(route = "home", label = "Home", icon = Icons.Default.Home),
    Search(route = "search", label = "Search", icon = Icons.Default.Search),
    Downloads(route = "downloads", label = "Downloads", icon = Icons.Default.KeyboardArrowDown),
    Settings(route = "settings", label = "Settings", icon = Icons.Default.Settings),
}

private val bottomNavRoutes = Screen.entries.map { it.route }.toSet()

@Composable
fun AppNavigation() {
    val navController = rememberNavController()
    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentDestination = navBackStackEntry?.destination
    val currentRoute = currentDestination?.route

    // Hide bottom nav when in player
    val showBottomNav = currentRoute == null ||
        !currentRoute.startsWith("player/")

    Scaffold(
        bottomBar = {
            if (showBottomNav) {
                NavigationBar {
                    Screen.entries.forEach { screen ->
                        NavigationBarItem(
                            selected = currentDestination?.hierarchy?.any { it.route == screen.route } == true,
                            onClick = {
                                navController.navigate(screen.route) {
                                    popUpTo(navController.graph.findStartDestination().id) {
                                        saveState = true
                                    }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon = { Icon(screen.icon, contentDescription = screen.label) },
                            label = { Text(screen.label) },
                        )
                    }
                }
            }
        },
    ) { _ ->
        NavHost(
            navController = navController,
            startDestination = Screen.Home.route,
        ) {
            composable(Screen.Home.route) {
                val vm: HomeViewModel = hiltViewModel()
                val downloadsVm: DownloadsViewModel = hiltViewModel()
                HomeScreen(
                    viewModel = vm,
                    onVideoClick = { video -> navController.navigate("player/${video.id}") },
                    onDownloadToPhone = { video -> downloadsVm.startPhoneDownload(video) },
                    onDownloadToServer = { video -> downloadsVm.enqueueServer(video.id) },
                )
            }
            composable(Screen.Search.route) {
                val vm: SearchViewModel = hiltViewModel()
                val downloadsVm: DownloadsViewModel = hiltViewModel()
                SearchScreen(
                    viewModel = vm,
                    onVideoClick = { video -> navController.navigate("player/${video.id}") },
                    onDownloadToPhone = { video -> downloadsVm.startPhoneDownload(video) },
                    onDownloadToServer = { video -> downloadsVm.enqueueServer(video.id) },
                )
            }
            composable(Screen.Downloads.route) {
                val vm: DownloadsViewModel = hiltViewModel()
                DownloadsScreen(
                    viewModel = vm,
                    onPlayLocal = { videoId -> navController.navigate("player/$videoId") },
                    onPlayServer = { videoId -> navController.navigate("player/$videoId") },
                )
            }
            composable(Screen.Settings.route) {
                val vm: SettingsViewModel = hiltViewModel()
                SettingsScreen(
                    viewModel = vm,
                    onDisconnected = {
                        // Navigate to root; MainActivity will redirect to SetupScreen
                        navController.navigate(Screen.Home.route) {
                            popUpTo(navController.graph.findStartDestination().id) {
                                inclusive = true
                            }
                        }
                    },
                )
            }
            composable("player/{videoId}") { _ ->
                val vm: PlayerViewModel = hiltViewModel()
                PlayerScreen(vm) { navController.popBackStack() }
            }
        }
    }
}
