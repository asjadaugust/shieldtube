# ShieldTube Android Phone App — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a native Android phone app (Kotlin + Jetpack Compose) to replace the mobile PWA with reliable video playback, background downloads, and cast support.

**Architecture:** Single-activity Compose app with MVVM pattern. Retrofit talks to the existing ShieldTube backend API. Media3 ExoPlayer for video. WorkManager for phone downloads. Room for local state. LAN auto-detect for fast streaming.

**Tech Stack:** Kotlin 1.9, Jetpack Compose, Material 3, Media3 ExoPlayer, Retrofit + OkHttp + Moshi, WorkManager, Room, Hilt, Coil, Compose Navigation.

**Spec:** `docs/superpowers/specs/2026-03-21-shieldtube-android-app-design.md`

**Existing code to reference:** `shield-app/` has Kotlin API models (`api/models.kt`), Retrofit interface (`api/ShieldTubeApi.kt`), and ApiClient (`api/ApiClient.kt`) that can be adapted.

---

## File Structure

```
shieldtube-phone/
├── app/
│   ├── build.gradle.kts
│   ├── src/main/
│   │   ├── AndroidManifest.xml
│   │   ├── java/com/shieldtube/phone/
│   │   │   ├── ShieldTubeApp.kt                  # Hilt Application
│   │   │   ├── MainActivity.kt                   # Single Compose activity
│   │   │   ├── di/
│   │   │   │   └── AppModule.kt                  # Hilt providers (Retrofit, Room, etc.)
│   │   │   ├── data/
│   │   │   │   ├── api/
│   │   │   │   │   ├── ShieldTubeApi.kt          # Retrofit interface
│   │   │   │   │   ├── AuthInterceptor.kt        # OkHttp interceptor for X-ShieldTube-Secret
│   │   │   │   │   └── ApiModels.kt              # Response data classes
│   │   │   │   ├── db/
│   │   │   │   │   ├── AppDatabase.kt            # Room database
│   │   │   │   │   ├── LocalDownloadDao.kt       # Download DAO
│   │   │   │   │   └── LocalDownloadEntity.kt    # Entity
│   │   │   │   ├── preferences/
│   │   │   │   │   └── AppPreferences.kt         # DataStore for settings
│   │   │   │   └── repository/
│   │   │   │       ├── FeedRepository.kt         # Feed data source
│   │   │   │       ├── DownloadRepository.kt     # Server + phone downloads
│   │   │   │       └── SettingsRepository.kt     # Backend URL, LAN URL, secret
│   │   │   ├── service/
│   │   │   │   ├── LanDetector.kt                # LAN availability probe
│   │   │   │   └── VideoDownloadWorker.kt        # WorkManager phone download
│   │   │   └── ui/
│   │   │       ├── navigation/
│   │   │       │   └── AppNavigation.kt          # NavHost + bottom nav
│   │   │       ├── theme/
│   │   │       │   ├── Theme.kt                  # NVIDIA dark theme
│   │   │       │   └── Type.kt                   # Typography
│   │   │       ├── components/
│   │   │       │   ├── VideoCard.kt              # Reusable video card composable
│   │   │       │   ├── VideoGrid.kt              # LazyVerticalGrid of cards
│   │   │       │   └── LoadingState.kt           # Loading/error/empty states
│   │   │       ├── setup/
│   │   │       │   ├── SetupScreen.kt            # Initial config (URL, secret)
│   │   │       │   └── SetupViewModel.kt
│   │   │       ├── home/
│   │   │       │   ├── HomeScreen.kt             # Feed tabs + video grid
│   │   │       │   └── HomeViewModel.kt
│   │   │       ├── search/
│   │   │       │   ├── SearchScreen.kt           # Search bar + results
│   │   │       │   └── SearchViewModel.kt
│   │   │       ├── player/
│   │   │       │   ├── PlayerScreen.kt           # ExoPlayer fullscreen
│   │   │       │   └── PlayerViewModel.kt
│   │   │       ├── downloads/
│   │   │       │   ├── DownloadsScreen.kt        # Phone + server downloads
│   │   │       │   └── DownloadsViewModel.kt
│   │   │       └── settings/
│   │   │           └── SettingsSheet.kt          # Bottom sheet settings
│   │   └── res/
│   │       ├── mipmap-*/ic_launcher.png          # Copy from shield-app
│   │       └── values/
│   │           ├── strings.xml
│   │           └── themes.xml
│   └── src/test/java/com/shieldtube/phone/       # Unit tests
├── build.gradle.kts                               # Root build file
├── settings.gradle.kts
└── gradle.properties
```

---

## Task 1: Project Scaffold + Gradle Setup

**Files:**
- Create: `shieldtube-phone/build.gradle.kts`
- Create: `shieldtube-phone/settings.gradle.kts`
- Create: `shieldtube-phone/gradle.properties`
- Create: `shieldtube-phone/app/build.gradle.kts`
- Create: `shieldtube-phone/app/src/main/AndroidManifest.xml`
- Copy: `shieldtube-phone/gradle/` from `shield-app/gradle/` (wrapper)
- Copy: `shieldtube-phone/gradlew`, `gradlew.bat` from `shield-app/`

- [ ] **Step 1: Create root build.gradle.kts**

```kotlin
// shieldtube-phone/build.gradle.kts
plugins {
    id("com.android.application") version "8.2.2" apply false
    id("org.jetbrains.kotlin.android") version "1.9.22" apply false
    id("com.google.dagger.hilt.android") version "2.50" apply false
    id("com.google.devtools.ksp") version "1.9.22-1.0.17" apply false
}
```

- [ ] **Step 2: Create settings.gradle.kts**

```kotlin
// shieldtube-phone/settings.gradle.kts
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolution {
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "ShieldTubePhone"
include(":app")
```

- [ ] **Step 3: Create gradle.properties**

```properties
android.useAndroidX=true
org.gradle.jvmargs=-Xmx2048m
android.nonTransitiveRClass=true
```

- [ ] **Step 4: Create app/build.gradle.kts with all dependencies**

```kotlin
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.google.dagger.hilt.android")
    id("com.google.devtools.ksp")
}

android {
    namespace = "com.shieldtube.phone"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.shieldtube.phone"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildFeatures {
        compose = true
    }

    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.8"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    // Compose
    val composeBom = platform("androidx.compose:compose-bom:2024.02.00")
    implementation(composeBom)
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.activity:activity-compose:1.8.2")
    implementation("androidx.navigation:navigation-compose:2.7.6")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.7.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.7.0")
    debugImplementation("androidx.compose.ui:ui-tooling")

    // Media3 ExoPlayer
    implementation("androidx.media3:media3-exoplayer:1.2.1")
    implementation("androidx.media3:media3-ui:1.2.1")
    implementation("androidx.media3:media3-datasource-okhttp:1.2.1")

    // Networking
    implementation("com.squareup.retrofit2:retrofit:2.9.0")
    implementation("com.squareup.retrofit2:converter-moshi:2.9.0")
    implementation("com.squareup.moshi:moshi-kotlin:1.15.0")
    ksp("com.squareup.moshi:moshi-kotlin-codegen:1.15.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")

    // Hilt DI
    implementation("com.google.dagger:hilt-android:2.50")
    ksp("com.google.dagger:hilt-android-compiler:2.50")
    implementation("androidx.hilt:hilt-navigation-compose:1.1.0")
    implementation("androidx.hilt:hilt-work:1.1.0")
    ksp("androidx.hilt:hilt-compiler:1.1.0")

    // Room
    implementation("androidx.room:room-runtime:2.6.1")
    implementation("androidx.room:room-ktx:2.6.1")
    ksp("androidx.room:room-compiler:2.6.1")

    // WorkManager
    implementation("androidx.work:work-runtime-ktx:2.9.0")

    // Image loading
    implementation("io.coil-kt:coil-compose:2.5.0")

    // DataStore
    implementation("androidx.datastore:datastore-preferences:1.0.0")

    // Core
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")

    // Testing
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.7.3")
    testImplementation("io.mockk:mockk:1.13.8")
}
```

- [ ] **Step 5: Create AndroidManifest.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />

    <application
        android:name=".ShieldTubeApp"
        android:allowBackup="true"
        android:icon="@mipmap/ic_launcher"
        android:label="ShieldTube"
        android:supportsRtl="true"
        android:theme="@style/Theme.ShieldTube"
        android:networkSecurityConfig="@xml/network_security_config"
        android:usesCleartextTraffic="false">

        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:configChanges="orientation|screenSize|screenLayout|smallestScreenSize">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
```

- [ ] **Step 6: Copy gradle wrapper and icon resources**

```bash
cp -r shield-app/gradle shieldtube-phone/
cp shield-app/gradlew shield-app/gradlew.bat shieldtube-phone/
mkdir -p shieldtube-phone/app/src/main/res/mipmap-{mdpi,hdpi,xhdpi,xxhdpi,xxxhdpi}
cp shield-app/app/src/main/res/mipmap-*/ic_launcher.png shieldtube-phone/app/src/main/res/mipmap-*/
mkdir -p shieldtube-phone/app/src/main/res/xml
cp shield-app/app/src/main/res/xml/network_security_config.xml shieldtube-phone/app/src/main/res/xml/
```

Create `res/values/strings.xml`:
```xml
<resources>
    <string name="app_name">ShieldTube</string>
</resources>
```

Create `res/values/themes.xml`:
```xml
<resources>
    <style name="Theme.ShieldTube" parent="android:Theme.Material.NoActionBar" />
</resources>
```

- [ ] **Step 7: Create ShieldTubeApp.kt and empty MainActivity.kt**

```kotlin
// ShieldTubeApp.kt
package com.shieldtube.phone

import android.app.Application
import dagger.hilt.android.HiltAndroidApp

@HiltAndroidApp
class ShieldTubeApp : Application()
```

```kotlin
// MainActivity.kt
package com.shieldtube.phone

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.shieldtube.phone.ui.theme.ShieldTubeTheme
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            ShieldTubeTheme {
                // TODO: Add navigation
            }
        }
    }
}
```

- [ ] **Step 8: Build to verify project compiles**

```bash
cd shieldtube-phone && ./gradlew assembleDebug
```

- [ ] **Step 9: Commit**

```bash
git add shieldtube-phone/
git commit -m "feat: scaffold ShieldTube phone app with Compose + Hilt + Media3"
```

---

## Task 2: Theme + API Layer + DI Module

**Files:**
- Create: `ui/theme/Theme.kt`, `ui/theme/Type.kt`
- Create: `data/api/ApiModels.kt`
- Create: `data/api/ShieldTubeApi.kt`
- Create: `data/api/AuthInterceptor.kt`
- Create: `data/preferences/AppPreferences.kt`
- Create: `di/AppModule.kt`

- [ ] **Step 1: Create NVIDIA theme**

```kotlin
// ui/theme/Theme.kt
package com.shieldtube.phone.ui.theme

import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val NvidiaGreen = Color(0xFF76B900)
val DarkBg = Color(0xFF121212)
val DarkSurface = Color(0xFF1E1E1E)
val DarkCard = Color(0xFF2A2A2A)

private val DarkScheme = darkColorScheme(
    primary = NvidiaGreen,
    background = DarkBg,
    surface = DarkSurface,
    surfaceVariant = DarkCard,
    onPrimary = DarkBg,
    onBackground = Color.White,
    onSurface = Color.White,
    onSurfaceVariant = Color(0xFFB0B0B0),
)

@Composable
fun ShieldTubeTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = DarkScheme, typography = ShieldTubeTypography, content = content)
}
```

```kotlin
// ui/theme/Type.kt
package com.shieldtube.phone.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

val ShieldTubeTypography = Typography(
    titleLarge = TextStyle(fontWeight = FontWeight.Bold, fontSize = 20.sp),
    titleMedium = TextStyle(fontWeight = FontWeight.SemiBold, fontSize = 16.sp),
    bodyMedium = TextStyle(fontSize = 14.sp),
    bodySmall = TextStyle(fontSize = 12.sp, color = androidx.compose.ui.graphics.Color(0xFFB0B0B0)),
    labelSmall = TextStyle(fontSize = 10.sp, fontWeight = FontWeight.Medium),
)
```

- [ ] **Step 2: Create API models (adapted from existing shield-app models.kt)**

```kotlin
// data/api/ApiModels.kt
package com.shieldtube.phone.data.api

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class VideoItem(
    val id: String,
    val title: String = "",
    @Json(name = "channel_name") val channelName: String = "",
    @Json(name = "channel_id") val channelId: String = "",
    @Json(name = "view_count") val viewCount: Long? = null,
    val duration: Int? = null,
    @Json(name = "published_at") val publishedAt: String? = null,
    @Json(name = "thumbnail_url") val thumbnailUrl: String = "",
)

@JsonClass(generateAdapter = true)
data class FeedResponse(
    @Json(name = "feed_type") val feedType: String,
    val videos: List<VideoItem>,
    @Json(name = "cached_at") val cachedAt: String? = null,
    @Json(name = "from_cache") val fromCache: Boolean = false,
)

@JsonClass(generateAdapter = true)
data class SponsorSegment(
    val start: Double,
    val end: Double,
    val category: String,
)

@JsonClass(generateAdapter = true)
data class SponsorResponse(
    @Json(name = "video_id") val videoId: String,
    val segments: List<SponsorSegment>,
)

@JsonClass(generateAdapter = true)
data class ProgressBody(
    @Json(name = "position_seconds") val positionSeconds: Int,
    val duration: Int,
    val event: String? = null,
)

@JsonClass(generateAdapter = true)
data class AuthStatusResponse(val authenticated: Boolean)

@JsonClass(generateAdapter = true)
data class EnqueueBody(@Json(name = "video_id") val videoId: String)

@JsonClass(generateAdapter = true)
data class EnqueueResponse(val status: String, @Json(name = "video_id") val videoId: String? = null)

@JsonClass(generateAdapter = true)
data class ActiveDownload(
    @Json(name = "video_id") val videoId: String,
    val title: String = "",
    @Json(name = "channel_name") val channelName: String = "",
    val status: String,
    val percent: Double,
    @Json(name = "bytes_downloaded") val bytesDownloaded: Long = 0,
    @Json(name = "bytes_total") val bytesTotal: Long = 0,
)

@JsonClass(generateAdapter = true)
data class ActiveDownloadsResponse(
    val active: List<ActiveDownload>,
    @Json(name = "queue_size") val queueSize: Int,
)

@JsonClass(generateAdapter = true)
data class LibraryVideo(
    val id: String,
    val title: String = "",
    @Json(name = "channel_name") val channelName: String = "",
    val duration: Int? = null,
    @Json(name = "cache_status") val cacheStatus: String = "",
    @Json(name = "download_source") val downloadSource: String = "",
    @Json(name = "cached_at") val cachedAt: String? = null,
    @Json(name = "file_size") val fileSize: Long = 0,
)

@JsonClass(generateAdapter = true)
data class LibraryResponse(val videos: List<LibraryVideo>)

@JsonClass(generateAdapter = true)
data class CastBody(val url: String)

@JsonClass(generateAdapter = true)
data class CacheStatusResponse(
    @Json(name = "used_gb") val usedGb: Double,
    @Json(name = "total_gb") val totalGb: Double,
)
```

- [ ] **Step 3: Create Retrofit interface**

```kotlin
// data/api/ShieldTubeApi.kt
package com.shieldtube.phone.data.api

import okhttp3.ResponseBody
import retrofit2.http.*

interface ShieldTubeApi {
    @GET("api/feed/{type}")
    suspend fun getFeed(@Path("type") type: String): FeedResponse

    @GET("api/search")
    suspend fun search(@Query("q") query: String): FeedResponse

    @GET("api/video/{id}/meta")
    suspend fun getVideoMeta(@Path("id") videoId: String): Map<String, Any?>

    @GET("api/sponsorblock/{id}")
    suspend fun getSponsorSegments(@Path("id") videoId: String): SponsorResponse

    @POST("api/video/{id}/progress")
    suspend fun reportProgress(@Path("id") videoId: String, @Body body: ProgressBody)

    @POST("api/download/enqueue")
    suspend fun enqueueServerDownload(@Body body: EnqueueBody): EnqueueResponse

    @GET("api/download/active")
    suspend fun getActiveDownloads(): ActiveDownloadsResponse

    @GET("api/download/library")
    suspend fun getDownloadLibrary(): LibraryResponse

    @POST("api/cast")
    suspend fun castToShield(@Body body: CastBody)

    @GET("api/auth/status")
    suspend fun authStatus(): AuthStatusResponse

    @GET("api/cache/status")
    suspend fun cacheStatus(): CacheStatusResponse
}
```

- [ ] **Step 4: Create auth interceptor**

```kotlin
// data/api/AuthInterceptor.kt
package com.shieldtube.phone.data.api

import com.shieldtube.phone.data.preferences.AppPreferences
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import okhttp3.Interceptor
import okhttp3.Response
import javax.inject.Inject

class AuthInterceptor @Inject constructor(
    private val prefs: AppPreferences,
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val secret = runBlocking { prefs.apiSecret.first() }
        val request = chain.request().newBuilder()
            .addHeader("X-ShieldTube-Secret", secret)
            .build()
        return chain.proceed(request)
    }
}
```

- [ ] **Step 5: Create AppPreferences (DataStore)**

```kotlin
// data/preferences/AppPreferences.kt
package com.shieldtube.phone.data.preferences

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.dataStore by preferencesDataStore("shieldtube_prefs")

@Singleton
class AppPreferences @Inject constructor(@ApplicationContext private val ctx: Context) {

    private val KEY_URL = stringPreferencesKey("backend_url")
    private val KEY_SECRET = stringPreferencesKey("api_secret")
    private val KEY_LAN_URL = stringPreferencesKey("lan_url")

    val backendUrl: Flow<String> = ctx.dataStore.data.map { it[KEY_URL] ?: "" }
    val apiSecret: Flow<String> = ctx.dataStore.data.map { it[KEY_SECRET] ?: "" }
    val lanUrl: Flow<String> = ctx.dataStore.data.map { it[KEY_LAN_URL] ?: "" }

    val isConfigured: Flow<Boolean> = ctx.dataStore.data.map {
        !it[KEY_URL].isNullOrBlank() && !it[KEY_SECRET].isNullOrBlank()
    }

    suspend fun save(url: String, secret: String, lanUrl: String = "") {
        ctx.dataStore.edit {
            it[KEY_URL] = url.trimEnd('/')
            it[KEY_SECRET] = secret
            it[KEY_LAN_URL] = lanUrl.trimEnd('/')
        }
    }
}
```

- [ ] **Step 6: Create Hilt AppModule**

```kotlin
// di/AppModule.kt
package com.shieldtube.phone.di

import android.content.Context
import com.shieldtube.phone.data.api.AuthInterceptor
import com.shieldtube.phone.data.api.ShieldTubeApi
import com.shieldtube.phone.data.db.AppDatabase
import com.shieldtube.phone.data.preferences.AppPreferences
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import java.security.SecureRandom
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.inject.Singleton
import javax.net.ssl.*

@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    fun provideMoshi(): Moshi = Moshi.Builder().build()

    @Provides
    @Singleton
    fun provideOkHttp(interceptor: AuthInterceptor): OkHttpClient {
        // Trust self-signed certs (backend uses self-signed HTTPS)
        val trustManager = object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {}
            override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {}
            override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
        }
        val sslContext = SSLContext.getInstance("TLS").apply {
            init(null, arrayOf<TrustManager>(trustManager), SecureRandom())
        }

        return OkHttpClient.Builder()
            .sslSocketFactory(sslContext.socketFactory, trustManager)
            .hostnameVerifier { _, _ -> true }
            .addInterceptor(interceptor)
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .writeTimeout(15, TimeUnit.SECONDS)
            .build()
    }

    @Provides
    @Singleton
    fun provideRetrofit(client: OkHttpClient, moshi: Moshi, prefs: AppPreferences): Retrofit {
        val baseUrl = runBlocking { prefs.backendUrl.first() }.ifBlank { "https://localhost" }
        return Retrofit.Builder()
            .baseUrl("$baseUrl/")
            .client(client)
            .addConverterFactory(MoshiConverterFactory.create(moshi))
            .build()
    }

    @Provides
    @Singleton
    fun provideApi(retrofit: Retrofit): ShieldTubeApi = retrofit.create(ShieldTubeApi::class.java)

    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext ctx: Context): AppDatabase =
        AppDatabase.create(ctx)
}
```

- [ ] **Step 7: Build and verify**

```bash
cd shieldtube-phone && ./gradlew assembleDebug
```

- [ ] **Step 8: Commit**

```bash
git add shieldtube-phone/
git commit -m "feat: add theme, API layer, DI module, and preferences"
```

---

## Task 3: Room Database + Repositories

**Files:**
- Create: `data/db/AppDatabase.kt`
- Create: `data/db/LocalDownloadDao.kt`
- Create: `data/db/LocalDownloadEntity.kt`
- Create: `data/repository/FeedRepository.kt`
- Create: `data/repository/DownloadRepository.kt`
- Create: `data/repository/SettingsRepository.kt`
- Create: `service/LanDetector.kt`

- [ ] **Step 1: Create Room entities and DAO**

```kotlin
// data/db/LocalDownloadEntity.kt
package com.shieldtube.phone.data.db

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "local_downloads")
data class LocalDownloadEntity(
    @PrimaryKey val videoId: String,
    val title: String = "",
    val channelName: String = "",
    val duration: Int? = null,
    val filePath: String? = null,
    val fileSize: Long = 0,
    val status: String = "pending", // pending, downloading, complete, error
    val progress: Int = 0,
    val createdAt: Long = System.currentTimeMillis(),
)
```

```kotlin
// data/db/LocalDownloadDao.kt
package com.shieldtube.phone.data.db

import androidx.room.*
import kotlinx.coroutines.flow.Flow

@Dao
interface LocalDownloadDao {
    @Query("SELECT * FROM local_downloads ORDER BY createdAt DESC")
    fun getAll(): Flow<List<LocalDownloadEntity>>

    @Query("SELECT * FROM local_downloads WHERE videoId = :id")
    suspend fun getById(id: String): LocalDownloadEntity?

    @Upsert
    suspend fun upsert(download: LocalDownloadEntity)

    @Query("UPDATE local_downloads SET status = :status, progress = :progress WHERE videoId = :id")
    suspend fun updateProgress(id: String, status: String, progress: Int)

    @Query("UPDATE local_downloads SET status = 'complete', filePath = :path, fileSize = :size WHERE videoId = :id")
    suspend fun markComplete(id: String, path: String, size: Long)

    @Query("DELETE FROM local_downloads WHERE videoId = :id")
    suspend fun delete(id: String)
}
```

```kotlin
// data/db/AppDatabase.kt
package com.shieldtube.phone.data.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(entities = [LocalDownloadEntity::class], version = 1)
abstract class AppDatabase : RoomDatabase() {
    abstract fun downloadDao(): LocalDownloadDao

    companion object {
        fun create(context: Context): AppDatabase =
            Room.databaseBuilder(context, AppDatabase::class.java, "shieldtube-phone.db")
                .fallbackToDestructiveMigration()
                .build()
    }
}
```

- [ ] **Step 2: Create repositories**

```kotlin
// data/repository/FeedRepository.kt
package com.shieldtube.phone.data.repository

import com.shieldtube.phone.data.api.FeedResponse
import com.shieldtube.phone.data.api.ShieldTubeApi
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class FeedRepository @Inject constructor(private val api: ShieldTubeApi) {
    suspend fun getFeed(type: String): FeedResponse = api.getFeed(type)
    suspend fun search(query: String): FeedResponse = api.search(query)
}
```

```kotlin
// data/repository/DownloadRepository.kt
package com.shieldtube.phone.data.repository

import com.shieldtube.phone.data.api.*
import com.shieldtube.phone.data.db.LocalDownloadDao
import com.shieldtube.phone.data.db.LocalDownloadEntity
import kotlinx.coroutines.flow.Flow
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class DownloadRepository @Inject constructor(
    private val api: ShieldTubeApi,
    private val dao: LocalDownloadDao,
) {
    // Server downloads
    suspend fun enqueueServer(videoId: String): EnqueueResponse =
        api.enqueueServerDownload(EnqueueBody(videoId))

    suspend fun getActiveDownloads(): ActiveDownloadsResponse = api.getActiveDownloads()
    suspend fun getLibrary(): LibraryResponse = api.getDownloadLibrary()

    // Local phone downloads
    fun getLocalDownloads(): Flow<List<LocalDownloadEntity>> = dao.getAll()

    suspend fun addLocalDownload(video: VideoItem) {
        dao.upsert(LocalDownloadEntity(
            videoId = video.id,
            title = video.title,
            channelName = video.channelName,
            duration = video.duration,
        ))
    }

    suspend fun deleteLocal(id: String) = dao.delete(id)
}
```

- [ ] **Step 3: Create LanDetector**

```kotlin
// service/LanDetector.kt
package com.shieldtube.phone.service

import com.shieldtube.phone.data.preferences.AppPreferences
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class LanDetector @Inject constructor(
    private val prefs: AppPreferences,
) {
    private val _isAvailable = MutableStateFlow(false)
    val isAvailable: StateFlow<Boolean> = _isAvailable.asStateFlow()

    private val probeClient = OkHttpClient.Builder()
        .connectTimeout(1, TimeUnit.SECONDS)
        .readTimeout(1, TimeUnit.SECONDS)
        .hostnameVerifier { _, _ -> true }
        .build()

    private var probeJob: Job? = null

    fun startProbing(scope: CoroutineScope) {
        probeJob?.cancel()
        probeJob = scope.launch {
            while (isActive) {
                probe()
                delay(60_000)
            }
        }
    }

    private suspend fun probe() {
        val lanUrl = prefs.lanUrl.first()
        if (lanUrl.isBlank()) {
            _isAvailable.value = false
            return
        }
        _isAvailable.value = withContext(Dispatchers.IO) {
            try {
                val req = Request.Builder().url("$lanUrl/api/auth/status").build()
                probeClient.newCall(req).execute().use { it.isSuccessful }
            } catch (e: Exception) {
                false
            }
        }
    }

    suspend fun getStreamBaseUrl(): String {
        val lanUrl = prefs.lanUrl.first()
        val backendUrl = prefs.backendUrl.first()
        return if (_isAvailable.value && lanUrl.isNotBlank()) lanUrl else backendUrl
    }
}
```

- [ ] **Step 4: Update AppModule to provide DAO**

Add to `AppModule.kt`:
```kotlin
@Provides
fun provideDownloadDao(db: AppDatabase): LocalDownloadDao = db.downloadDao()
```

- [ ] **Step 5: Build and verify**

```bash
cd shieldtube-phone && ./gradlew assembleDebug
```

- [ ] **Step 6: Commit**

```bash
git commit -am "feat: add Room DB, repositories, and LAN detector"
```

---

## Task 4: Setup Screen + Navigation Shell

**Files:**
- Create: `ui/navigation/AppNavigation.kt`
- Create: `ui/setup/SetupScreen.kt`
- Create: `ui/setup/SetupViewModel.kt`
- Create: `ui/components/LoadingState.kt`
- Modify: `MainActivity.kt`

- [ ] **Step 1: Create SetupViewModel**

```kotlin
// ui/setup/SetupViewModel.kt
package com.shieldtube.phone.ui.setup

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shieldtube.phone.data.preferences.AppPreferences
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class SetupViewModel @Inject constructor(
    private val prefs: AppPreferences,
) : ViewModel() {

    val isConfigured: StateFlow<Boolean> = prefs.isConfigured
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), false)

    fun save(url: String, secret: String, lanUrl: String) {
        viewModelScope.launch { prefs.save(url, secret, lanUrl) }
    }
}
```

- [ ] **Step 2: Create SetupScreen composable**

```kotlin
// ui/setup/SetupScreen.kt
package com.shieldtube.phone.ui.setup

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp

@Composable
fun SetupScreen(onConfigured: () -> Unit, viewModel: SetupViewModel) {
    var url by remember { mutableStateOf("") }
    var secret by remember { mutableStateOf("") }
    var lanUrl by remember { mutableStateOf("") }

    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("ShieldTube", style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.primary)
        Spacer(Modifier.height(32.dp))

        OutlinedTextField(value = url, onValueChange = { url = it }, label = { Text("Backend URL") },
            placeholder = { Text("https://shieldtube.example.com") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(12.dp))

        OutlinedTextField(value = secret, onValueChange = { secret = it }, label = { Text("API Secret") },
            visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(12.dp))

        OutlinedTextField(value = lanUrl, onValueChange = { lanUrl = it }, label = { Text("LAN URL (optional)") },
            placeholder = { Text("https://192.168.0.26:9443") }, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(24.dp))

        Button(
            onClick = { viewModel.save(url, secret, lanUrl); onConfigured() },
            enabled = url.isNotBlank() && secret.isNotBlank(),
            modifier = Modifier.fillMaxWidth(),
        ) { Text("Connect") }
    }
}
```

- [ ] **Step 3: Create AppNavigation with bottom nav shell**

```kotlin
// ui/navigation/AppNavigation.kt
package com.shieldtube.phone.ui.navigation

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.compose.*

enum class Screen(val route: String, val label: String, val icon: ImageVector) {
    Home("home", "Home", Icons.Default.Home),
    Search("search", "Search", Icons.Default.Search),
    Downloads("downloads", "Downloads", Icons.Default.Download),
    Settings("settings", "Settings", Icons.Default.Settings),
}

@Composable
fun AppNavigation() {
    val navController = rememberNavController()
    val currentRoute = navController.currentBackStackEntryAsState().value?.destination?.route

    Scaffold(
        bottomBar = {
            NavigationBar {
                Screen.entries.forEach { screen ->
                    NavigationBarItem(
                        selected = currentRoute == screen.route,
                        onClick = {
                            navController.navigate(screen.route) {
                                popUpTo(Screen.Home.route) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Icon(screen.icon, screen.label) },
                        label = { Text(screen.label) },
                    )
                }
            }
        }
    ) { padding ->
        NavHost(navController, startDestination = Screen.Home.route, Modifier.padding(padding)) {
            composable(Screen.Home.route) { Text("Home — TODO") }
            composable(Screen.Search.route) { Text("Search — TODO") }
            composable(Screen.Downloads.route) { Text("Downloads — TODO") }
            composable(Screen.Settings.route) { Text("Settings — TODO") }
        }
    }
}
```

- [ ] **Step 4: Wire up MainActivity with setup gate**

```kotlin
// MainActivity.kt
package com.shieldtube.phone

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.*
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
                val setupVm: SetupViewModel = hiltViewModel()
                val isConfigured by setupVm.isConfigured.collectAsState()

                if (isConfigured) {
                    AppNavigation()
                } else {
                    SetupScreen(onConfigured = {}, viewModel = setupVm)
                }
            }
        }
    }
}
```

- [ ] **Step 5: Build, install, verify setup screen shows**

```bash
cd shieldtube-phone && ./gradlew installDebug
```

- [ ] **Step 6: Commit**

```bash
git commit -am "feat: add setup screen and navigation shell"
```

---

## Task 5: Home Screen (Feed Browsing)

**Files:**
- Create: `ui/components/VideoCard.kt`
- Create: `ui/components/VideoGrid.kt`
- Create: `ui/home/HomeScreen.kt`
- Create: `ui/home/HomeViewModel.kt`
- Modify: `ui/navigation/AppNavigation.kt` — wire Home

- [ ] **Step 1: Create VideoCard composable**

Displays thumbnail (Coil), title, channel name, duration badge. Click handler passed as parameter.

- [ ] **Step 2: Create VideoGrid composable**

`LazyVerticalGrid` of `VideoCard` items with pull-to-refresh.

- [ ] **Step 3: Create HomeViewModel**

Loads feed via `FeedRepository.getFeed(type)`. Exposes `StateFlow<HomeUiState>` with loading/success/error states. Supports tab switching (recommended, home, history).

- [ ] **Step 4: Create HomeScreen**

Tab row (For You, Home, History) + VideoGrid. Pull-to-refresh triggers reload.

- [ ] **Step 5: Wire into navigation, build, install, test**

- [ ] **Step 6: Commit**

---

## Task 6: Search Screen

**Files:**
- Create: `ui/search/SearchScreen.kt`
- Create: `ui/search/SearchViewModel.kt`
- Modify: `ui/navigation/AppNavigation.kt`

- [ ] **Step 1: Create SearchViewModel**

Debounced search (300ms) via `FeedRepository.search(query)`. Exposes results as StateFlow.

- [ ] **Step 2: Create SearchScreen**

Search bar with auto-focus + VideoGrid results. Empty state when no query.

- [ ] **Step 3: Wire into navigation, build, test**

- [ ] **Step 4: Commit**

---

## Task 7: Player Screen (ExoPlayer)

**Files:**
- Create: `ui/player/PlayerScreen.kt`
- Create: `ui/player/PlayerViewModel.kt`
- Modify: `ui/navigation/AppNavigation.kt` — add player route with videoId arg

- [ ] **Step 1: Create PlayerViewModel**

Loads SponsorBlock segments. Reports progress every 10s. Resolves stream URL via `LanDetector.getStreamBaseUrl()`.

- [ ] **Step 2: Create PlayerScreen**

Full-screen Media3 ExoPlayer. Stream URL = `{streamBaseUrl}/api/video/{id}/stream`. Auto-skip sponsor segments with Snackbar. Cast button triggers `/api/cast`. System UI hidden during playback.

- [ ] **Step 3: Add player route to navigation**

`composable("player/{videoId}") { ... }` — launched from VideoCard click.

- [ ] **Step 4: Build, install, test playback on LAN**

- [ ] **Step 5: Commit**

---

## Task 8: Downloads Screen

**Files:**
- Create: `ui/downloads/DownloadsScreen.kt`
- Create: `ui/downloads/DownloadsViewModel.kt`
- Create: `service/VideoDownloadWorker.kt`
- Modify: `ui/navigation/AppNavigation.kt`

- [ ] **Step 1: Create VideoDownloadWorker (WorkManager)**

Downloads video stream to phone storage via OkHttp. Reports progress via `setProgress()`. Uses foreground service with notification for long downloads.

- [ ] **Step 2: Create DownloadsViewModel**

Two tabs: "On Phone" (Room Flow) and "On Server" (API polling). Exposes combined state. Actions: start phone download, delete local, play local/server.

- [ ] **Step 3: Create DownloadsScreen**

Two-tab layout. Phone tab shows local downloads with progress. Server tab shows NAS library. Tap to play. Swipe to delete (phone only).

- [ ] **Step 4: Add download actions to VideoCard (long-press menu)**

Bottom sheet: Play, Cast, Download to Phone, Download to Server.

- [ ] **Step 5: Build, install, test downloads**

- [ ] **Step 6: Commit**

---

## Task 9: Settings + Polish

**Files:**
- Create: `ui/settings/SettingsSheet.kt`
- Modify: `ui/navigation/AppNavigation.kt`

- [ ] **Step 1: Create SettingsSheet**

Shows: Backend URL, LAN URL, LAN status (green/red dot), server cache usage, app version. Edit backend config. Logout (clear preferences).

- [ ] **Step 2: Wire into navigation**

- [ ] **Step 3: Final build + install**

```bash
cd shieldtube-phone && ./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

- [ ] **Step 4: Commit**

```bash
git commit -am "feat: complete ShieldTube phone app V1"
```

---

## Verification Checklist

- [ ] App installs and shows setup screen on first launch
- [ ] After entering backend URL + secret, feeds load with thumbnails
- [ ] Search returns results with debounce
- [ ] Tapping a video opens ExoPlayer and streams from LAN (fast) or tunnel (slower)
- [ ] SponsorBlock segments auto-skip with toast
- [ ] Cast button sends video to Shield TV
- [ ] Phone download works in background (screen off)
- [ ] Downloaded videos play offline from phone storage
- [ ] Server downloads tab shows NAS library
- [ ] Settings shows LAN status and cache usage
- [ ] NVIDIA theme consistent throughout (dark bg, green accents)
