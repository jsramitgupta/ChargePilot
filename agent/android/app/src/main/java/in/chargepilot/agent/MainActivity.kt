package `in`.chargepilot.agent

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.work.WorkManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.UUID

private val Pine = Color(0xFF244C3B)
private val Leaf = Color(0xFF4D8060)
private val Copper = Color(0xFFBD704E)
private val Canvas = Color(0xFFF3F6F1)
private val Ink = Color(0xFF1D3028)
private val Muted = Color(0xFF64736A)
private val ErrorRed = Color(0xFF9A3F35)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val store = AgentStore(applicationContext)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = Canvas) {
                    AgentScreen(store)
                }
            }
        }
    }
}

@Composable
private fun AgentScreen(store: AgentStore) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val scope = rememberCoroutineScope()
    val lifecycleOwner = LocalLifecycleOwner.current
    var revision by remember { mutableIntStateOf(0) }
    val configuration = remember(revision) { store.configuration() }
    var serverOrigin by remember { mutableStateOf(configuration?.serverOrigin ?: "https://api-chargepilot.endusercompute.in") }
    var label by remember { mutableStateOf(configuration?.label ?: "") }
    var enrollmentToken by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var statusMessage by remember { mutableStateOf("") }
    var statusIsError by remember { mutableStateOf(false) }
    var lastSuccess by remember(revision) { mutableStateOf(store.lastSuccess()) }
    var lastError by remember(revision) { mutableStateOf(store.lastError()) }
    var reading by remember { mutableStateOf<BatteryReading?>(null) }

    fun refreshSavedState() {
        revision += 1
        reading = runCatching { BatteryReader.read(context) }.getOrNull()
    }

    LaunchedEffect(Unit) {
        reading = runCatching { BatteryReader.read(context) }.getOrNull()
        if (configuration != null) TelemetryWorker.schedulePeriodic(context)
    }
    androidx.compose.runtime.DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) refreshSavedState()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 22.dp, vertical = 26.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text("ChargePilot", color = Pine, fontSize = 27.sp, fontWeight = FontWeight.Bold)
            Text("Battery telemetry", color = Muted, fontSize = 15.sp)
        }

        if (configuration == null) {
            EnrollmentForm(
                serverOrigin = serverOrigin,
                onServerOriginChange = { serverOrigin = it },
                label = label,
                onLabelChange = { label = it },
                enrollmentToken = enrollmentToken,
                onEnrollmentTokenChange = { enrollmentToken = it },
                busy = busy,
                onEnroll = {
                    if (label.isBlank() || enrollmentToken.isBlank()) {
                        statusMessage = "Enter a device label and enrollment token."
                        statusIsError = true
                    } else {
                        busy = true
                        statusMessage = ""
                        val submittedToken = enrollmentToken
                        enrollmentToken = ""
                        scope.launch {
                            try {
                                val installationId = UUID.randomUUID().toString()
                                val deviceClass = if (
                                    context.resources.configuration.smallestScreenWidthDp >= 600
                                ) "tablet" else "phone"
                                val (endpointId, credential) = withContext(Dispatchers.IO) {
                                    AgentApi.enroll(
                                        serverOrigin = serverOrigin,
                                        enrollmentToken = submittedToken,
                                        label = label.trim(),
                                        installationId = installationId,
                                        deviceClass = deviceClass,
                                    )
                                }
                                withContext(Dispatchers.IO) {
                                    store.saveEnrollment(
                                        AgentConfiguration(
                                            serverOrigin = serverOrigin.trimEnd('/'),
                                            installationId = installationId,
                                            endpointId = endpointId,
                                            label = label.trim(),
                                        ),
                                        credential,
                                    )
                                }
                                revision += 1
                                TelemetryWorker.schedulePeriodic(context)
                                TelemetryWorker.sendNow(context)
                                statusMessage = "This device is enrolled. Its first report is being sent."
                                statusIsError = false
                            } catch (error: Exception) {
                                statusMessage = error.message ?: "Enrollment failed. Check the server and token."
                                statusIsError = true
                            } finally {
                                busy = false
                            }
                        }
                    }
                },
            )
        } else {
            EnrolledStatus(
                configuration = configuration,
                reading = reading,
                lastSuccess = lastSuccess,
                lastError = lastError,
                busy = busy,
                statusMessage = statusMessage,
                statusIsError = statusIsError,
                onSync = {
                    busy = true
                    statusMessage = "Reading the battery and contacting ChargePilot…"
                    statusIsError = false
                    scope.launch {
                        try {
                            val workId = TelemetryWorker.sendNow(context)
                            repeat(30) {
                                delay(1_000)
                                val workInfo = withContext(Dispatchers.IO) {
                                    WorkManager.getInstance(context).getWorkInfoById(workId).get()
                                }
                                refreshSavedState()
                                when (workInfo?.state) {
                                    androidx.work.WorkInfo.State.SUCCEEDED -> {
                                        statusMessage = "Reading sent to ChargePilot."
                                        statusIsError = false
                                        return@launch
                                    }
                                    androidx.work.WorkInfo.State.FAILED -> {
                                        statusMessage = store.lastError() ?: "ChargePilot could not accept this reading."
                                        statusIsError = true
                                        return@launch
                                    }
                                    else -> Unit
                                }
                            }
                            statusMessage = "Sync is queued. Android may delay background work."
                            statusIsError = false
                        } catch (_: Exception) {
                            statusMessage = "Could not check sync status. Reopen the app to refresh."
                            statusIsError = true
                        } finally {
                            busy = false
                        }
                    }
                },
                onRefresh = { refreshSavedState() },
            )
        }

        if (statusMessage.isNotBlank() && configuration == null) {
            StatusNotice(statusMessage, statusIsError)
        }
        Text(
            "New endpoints are telemetry-only. ChargePilot keeps automation decisions on the server.",
            color = Muted,
            fontSize = 13.sp,
            lineHeight = 19.sp,
        )
    }
}

@Composable
private fun EnrollmentForm(
    serverOrigin: String,
    onServerOriginChange: (String) -> Unit,
    label: String,
    onLabelChange: (String) -> Unit,
    enrollmentToken: String,
    onEnrollmentTokenChange: (String) -> Unit,
    busy: Boolean,
    onEnroll: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text(
            "Connect this device",
            color = Ink,
            fontSize = 22.sp,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            "Use a workspace enrollment token. It expires after 24 hours and can be used for multiple devices.",
            color = Muted,
            fontSize = 14.sp,
            lineHeight = 21.sp,
        )
        OutlinedTextField(
            value = serverOrigin,
            onValueChange = onServerOriginChange,
            label = { Text("ChargePilot API origin") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = label,
            onValueChange = onLabelChange,
            label = { Text("Device label") },
            placeholder = { Text("For example, Travel phone") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = enrollmentToken,
            onValueChange = onEnrollmentTokenChange,
            label = { Text("24-hour enrollment token") },
            visualTransformation = PasswordVisualTransformation(),
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Button(
            onClick = onEnroll,
            enabled = !busy,
            colors = ButtonDefaults.buttonColors(containerColor = Pine),
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier.fillMaxWidth().height(52.dp),
        ) {
            if (busy) CircularProgressIndicator(color = Color.White, strokeWidth = 2.dp)
            else Text("Enroll this device", fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
private fun EnrolledStatus(
    configuration: AgentConfiguration,
    reading: BatteryReading?,
    lastSuccess: String?,
    lastError: String?,
    busy: Boolean,
    statusMessage: String,
    statusIsError: Boolean,
    onSync: () -> Unit,
    onRefresh: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text(configuration.label, color = Ink, fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
                Text("Android · enrolled", color = Leaf, fontSize = 14.sp)
            }
            TextButton(onClick = onRefresh) { Text("Refresh", color = Pine) }
        }

        Surface(
            color = Pine,
            shape = RoundedCornerShape(topStart = 28.dp, topEnd = 12.dp, bottomEnd = 28.dp, bottomStart = 12.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Column(
                modifier = Modifier.padding(horizontal = 22.dp, vertical = 24.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                Text("Current battery", color = Color(0xFFD6E3D8), fontSize = 14.sp)
                Row(verticalAlignment = Alignment.Bottom) {
                    Text(
                        reading?.let { "${it.percentage}" } ?: "—",
                        color = Color.White,
                        fontSize = 54.sp,
                        fontWeight = FontWeight.Light,
                    )
                    Text("%", color = Color(0xFFD6E3D8), fontSize = 22.sp, modifier = Modifier.padding(bottom = 9.dp))
                    Spacer(Modifier.width(10.dp))
                    Text(
                        when {
                            reading == null -> "Reading unavailable"
                            reading.charging -> "Charging"
                            reading.acConnected == true -> "Connected"
                            else -> "On battery"
                        },
                        color = Color.White,
                        fontSize = 14.sp,
                        modifier = Modifier.padding(bottom = 12.dp),
                    )
                }
                Surface(
                    color = Color(0xFF456B57),
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth().height(8.dp),
                ) {
                    if (reading != null) {
                        Surface(
                            color = Copper,
                            shape = RoundedCornerShape(8.dp),
                            modifier = Modifier.fillMaxWidth(reading.percentage / 100f),
                        ) {}
                    }
                }
            }
        }

        Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Text("Last successful report", color = Muted, fontSize = 13.sp)
            Text(
                lastSuccess?.let(::formatTimestamp) ?: "No report yet",
                color = Ink,
                fontSize = 16.sp,
                fontWeight = FontWeight.Medium,
            )
        }

        if (!lastError.isNullOrBlank()) StatusNotice(lastError, true)
        if (statusMessage.isNotBlank()) StatusNotice(statusMessage, statusIsError)

        Button(
            onClick = onSync,
            enabled = !busy,
            colors = ButtonDefaults.buttonColors(containerColor = Leaf),
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier.fillMaxWidth().height(52.dp),
        ) {
            if (busy) CircularProgressIndicator(color = Color.White, strokeWidth = 2.dp)
            else Text("Send reading now", fontWeight = FontWeight.SemiBold)
        }
        Text(
            "Background reports are best-effort. Android may delay them during Doze or battery optimization.",
            color = Muted,
            fontSize = 13.sp,
            lineHeight = 19.sp,
        )
    }
}

@Composable
private fun StatusNotice(message: String, isError: Boolean) {
    Surface(
        color = if (isError) Color(0xFFFBECE8) else Color(0xFFE5EEE5),
        shape = RoundedCornerShape(10.dp),
    ) {
        Text(
            message,
            color = if (isError) ErrorRed else Pine,
            fontSize = 14.sp,
            lineHeight = 20.sp,
            modifier = Modifier.fillMaxWidth().padding(13.dp),
        )
    }
}

private fun formatTimestamp(value: String): String =
    runCatching {
        val instant = Instant.parse(value)
        DateTimeFormatter.ofPattern("MMM d, yyyy 'at' h:mm a")
            .withZone(ZoneId.systemDefault())
            .format(instant)
    }.getOrDefault(value)
