package com.shieldtube.phone.service

import com.shieldtube.phone.data.preferences.AppPreferences
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import java.security.SecureRandom
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

@Singleton
class LanDetector @Inject constructor(
    private val prefs: AppPreferences,
) {
    private val _isAvailable = MutableStateFlow(false)
    val isAvailable: StateFlow<Boolean> = _isAvailable.asStateFlow()

    private val trustAllCerts = arrayOf<TrustManager>(object : X509TrustManager {
        override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) = Unit
        override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) = Unit
        override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
    })

    private val probeClient: OkHttpClient by lazy {
        val sslContext = SSLContext.getInstance("TLS").apply {
            init(null, trustAllCerts, SecureRandom())
        }
        OkHttpClient.Builder()
            .sslSocketFactory(sslContext.socketFactory, trustAllCerts[0] as X509TrustManager)
            .hostnameVerifier { _, _ -> true }
            .connectTimeout(1, TimeUnit.SECONDS)
            .readTimeout(1, TimeUnit.SECONDS)
            .build()
    }

    fun startProbing(scope: CoroutineScope) {
        scope.launch {
            while (true) {
                probe()
                delay(60_000L)
            }
        }
    }

    private suspend fun probe() {
        val lanUrl = prefs.lanUrl.first().takeIf { it.isNotBlank() } ?: return
        _isAvailable.value = try {
            val request = Request.Builder()
                .url("$lanUrl/api/auth/status")
                .build()
            val response = probeClient.newCall(request).execute()
            response.isSuccessful.also { response.close() }
        } catch (e: Exception) {
            false
        }
    }

    suspend fun getStreamBaseUrl(): String {
        // Prefer LAN URL when configured (probe may not be running)
        return prefs.lanUrl.first().takeIf { it.isNotBlank() }
            ?: prefs.backendUrl.first()
    }
}
