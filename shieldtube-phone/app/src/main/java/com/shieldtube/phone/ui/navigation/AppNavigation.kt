package com.shieldtube.phone.ui.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.PlayArrow
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
import com.shieldtube.phone.ui.home.HomeScreen
import com.shieldtube.phone.ui.home.HomeViewModel
import com.shieldtube.phone.ui.player.PlayerScreen
import com.shieldtube.phone.ui.player.PlayerViewModel
import com.shieldtube.phone.ui.search.SearchScreen
import com.shieldtube.phone.ui.search.SearchViewModel

enum class Screen(
    val route: String,
    val label: String,
    val icon: ImageVector,
) {
    Home(route = "home", label = "Home", icon = Icons.Default.Home),
    Search(route = "search", label = "Search", icon = Icons.Default.Search),
    Downloads(route = "downloads", label = "Downloads", icon = Icons.Default.PlayArrow),
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
                HomeScreen(vm) { video -> navController.navigate("player/${video.id}") }
            }
            composable(Screen.Search.route) {
                val vm: SearchViewModel = hiltViewModel()
                SearchScreen(vm) { video -> navController.navigate("player/${video.id}") }
            }
            composable(Screen.Downloads.route) {
                Text("Downloads — coming soon")
            }
            composable(Screen.Settings.route) {
                Text("Settings — coming soon")
            }
            composable("player/{videoId}") { _ ->
                val vm: PlayerViewModel = hiltViewModel()
                PlayerScreen(vm) { navController.popBackStack() }
            }
        }
    }
}
