package com.shieldtube.phone.ui.setup

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel

@Composable
fun SetupScreen(
    onConfigured: () -> Unit,
    viewModel: SetupViewModel = hiltViewModel(),
) {
    var backendUrl by remember { mutableStateOf("") }
    var apiSecret by remember { mutableStateOf("") }
    var lanUrl by remember { mutableStateOf("") }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(text = "ShieldTube Setup")

        Spacer(modifier = Modifier.height(24.dp))

        OutlinedTextField(
            value = backendUrl,
            onValueChange = { backendUrl = it },
            label = { Text("Backend URL") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
        )

        Spacer(modifier = Modifier.height(12.dp))

        OutlinedTextField(
            value = apiSecret,
            onValueChange = { apiSecret = it },
            label = { Text("API Secret") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
        )

        Spacer(modifier = Modifier.height(12.dp))

        OutlinedTextField(
            value = lanUrl,
            onValueChange = { lanUrl = it },
            label = { Text("LAN URL (optional)") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
        )

        Spacer(modifier = Modifier.height(24.dp))

        Button(
            onClick = {
                viewModel.save(backendUrl, apiSecret, lanUrl)
                onConfigured()
            },
            enabled = backendUrl.isNotBlank() && apiSecret.isNotBlank(),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Connect")
        }
    }
}
