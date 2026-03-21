package com.shieldtube.phone.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.ForegroundInfo
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import com.shieldtube.phone.data.db.LocalDownloadDao
import com.shieldtube.phone.data.preferences.AppPreferences
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import kotlinx.coroutines.flow.first
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.security.SecureRandom
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

@HiltWorker
class VideoDownloadWorker @AssistedInject constructor(
    @Assisted ctx: Context,
    @Assisted params: WorkerParameters,
    private val prefs: AppPreferences,
    private val lanDetector: LanDetector,
    private val downloadDao: LocalDownloadDao,
) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result {
        val videoId = inputData.getString("video_id") ?: return Result.failure()

        setForeground(createForegroundInfo(videoId))

        val baseUrl = lanDetector.getStreamBaseUrl()
        val streamUrl = "$baseUrl/api/video/$videoId/stream"
        val secret = prefs.apiSecret.first()

        val videosDir = applicationContext.getExternalFilesDir("videos")
            ?: return Result.failure()
        val file = File(videosDir, "$videoId.mp4")

        val client = buildTrustAllClient()
        val request = Request.Builder()
            .url(streamUrl)
            .addHeader("X-ShieldTube-Secret", secret)
            .build()

        return try {
            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) return Result.failure()
                val body = response.body ?: return Result.failure()
                val totalBytes = body.contentLength()

                file.outputStream().use { out ->
                    val buffer = ByteArray(262144) // 256 KB
                    var downloaded = 0L
                    body.byteStream().use { input ->
                        while (true) {
                            val read = input.read(buffer)
                            if (read == -1) break
                            out.write(buffer, 0, read)
                            downloaded += read
                            val progress = if (totalBytes > 0) {
                                ((downloaded * 100) / totalBytes).toInt()
                            } else {
                                0
                            }
                            setProgress(workDataOf("percent" to progress))
                            downloadDao.updateProgress(videoId, progress, "downloading")
                        }
                    }
                }
            }

            downloadDao.markComplete(videoId, file.absolutePath, file.length())
            Result.success()
        } catch (e: Exception) {
            downloadDao.updateProgress(videoId, 0, "error")
            Result.failure()
        }
    }

    private fun createForegroundInfo(videoId: String): ForegroundInfo {
        val channelId = "downloads"
        val nm = applicationContext.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            nm.createNotificationChannel(
                NotificationChannel(channelId, "Downloads", NotificationManager.IMPORTANCE_LOW),
            )
        }
        val notification = NotificationCompat.Builder(applicationContext, channelId)
            .setContentTitle("Downloading video")
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setOngoing(true)
            .build()
        return ForegroundInfo(videoId.hashCode(), notification)
    }

    private fun buildTrustAllClient(): OkHttpClient {
        val trustAllCerts = arrayOf<TrustManager>(object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) = Unit
            override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) = Unit
            override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
        })
        val sslContext = SSLContext.getInstance("TLS").apply {
            init(null, trustAllCerts, SecureRandom())
        }
        return OkHttpClient.Builder()
            .sslSocketFactory(sslContext.socketFactory, trustAllCerts[0] as X509TrustManager)
            .hostnameVerifier { _, _ -> true }
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(0, TimeUnit.SECONDS) // no read timeout for large downloads
            .build()
    }
}
