package com.shieldtube.api

import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

object ApiClient {
    // Must be public — CardPresenter references ApiClient.BASE_URL for thumbnail URLs
    const val BASE_URL = "http://192.168.1.100:8080"

    val api: ShieldTubeApi by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ShieldTubeApi::class.java)
    }
}
