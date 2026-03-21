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
