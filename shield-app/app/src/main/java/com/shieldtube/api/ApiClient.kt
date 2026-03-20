package com.shieldtube.api

import okhttp3.Interceptor
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

object ApiClient {
    // Must be public — CardPresenter references ApiClient.BASE_URL for thumbnail URLs
    const val BASE_URL = "https://192.168.1.100:8443"

    private val okHttpClient: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .addInterceptor(Interceptor { chain ->
                val secret = com.shieldtube.BuildConfig.API_SECRET
                val request = if (secret.isNotEmpty()) {
                    chain.request().newBuilder()
                        .addHeader("X-ShieldTube-Secret", secret)
                        .build()
                } else {
                    chain.request()
                }
                chain.proceed(request)
            })
            .build()
    }

    val api: ShieldTubeApi by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ShieldTubeApi::class.java)
    }
}
