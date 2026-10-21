package `in`.chargepilot.agent

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Build
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.time.Instant
import java.util.UUID
import java.util.concurrent.TimeUnit

data class BatteryReading(
    val percentage: Int,
    val charging: Boolean,
    val acConnected: Boolean?,
)

object BatteryReader {
    fun read(context: Context): BatteryReading {
        val intent = context.registerReceiver(
            null,
            IntentFilter(Intent.ACTION_BATTERY_CHANGED),
        ) ?: throw BatteryUnavailableException()
        val level = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
        val scale = intent.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
        if (level < 0 || scale <= 0) throw BatteryUnavailableException()

        val status = intent.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
        if (status !in setOf(
                BatteryManager.BATTERY_STATUS_CHARGING,
                BatteryManager.BATTERY_STATUS_DISCHARGING,
                BatteryManager.BATTERY_STATUS_FULL,
                BatteryManager.BATTERY_STATUS_NOT_CHARGING,
            )
        ) {
            throw BatteryUnavailableException()
        }
        val plugType = intent.getIntExtra(BatteryManager.EXTRA_PLUGGED, -1)
        return BatteryReading(
            percentage = ((level.toDouble() / scale) * 100).toInt().coerceIn(0, 100),
            charging = status == BatteryManager.BATTERY_STATUS_CHARGING,
            acConnected = if (plugType < 0) null else plugType != 0,
        )
    }
}

object AgentApi {
    fun enroll(
        serverOrigin: String,
        enrollmentToken: String,
        label: String,
        installationId: String,
        deviceClass: String,
    ): Pair<String, String> {
        val body = JSONObject()
            .put("code", enrollmentToken)
            .put("platform", "android")
            .put("installation_id", installationId)
            .put("hostname", label)
            .put("device_class", deviceClass)
        val response = request(
            origin = validateOrigin(serverOrigin),
            path = "/api/v1/endpoint-enrollment/exchange",
            body = body,
        )
        val credential = response.optString("credential")
        val endpointId = response.optString("endpoint_id")
        val returnedInstallationId = response.optString("installation_id")
        if (
            credential.isBlank() ||
            endpointId.isBlank() ||
            returnedInstallationId != installationId
        ) {
            throw IOException("The server returned an incomplete enrollment response.")
        }
        return endpointId to credential
    }

    fun sendTelemetry(
        context: Context,
        configuration: AgentConfiguration,
        credential: String,
        reading: BatteryReading,
    ) {
        val body = JSONObject()
            .put("hostname", configuration.label)
            .put("installation_id", configuration.installationId)
            .put("platform", "android")
            .put(
                "device_class",
                if (context.resources.configuration.smallestScreenWidthDp >= 600) "tablet" else "phone",
            )
            .put("battery_percentage", reading.percentage)
            .put("charging", reading.charging)
            .put("timestamp", Instant.now().toString())
            .put("agent_version", BuildConfig.VERSION_NAME)
        reading.acConnected?.let { body.put("ac_connected", it) }
        request(
            origin = validateOrigin(configuration.serverOrigin),
            path = "/api/v1/telemetry",
            body = body,
            credential = credential,
        )
    }

    private fun request(
        origin: String,
        path: String,
        body: JSONObject,
        credential: String? = null,
    ): JSONObject {
        val connection = (URL("$origin$path").openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 15_000
            readTimeout = 15_000
            doOutput = true
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            credential?.let { setRequestProperty("Authorization", "Bearer $it") }
        }
        try {
            connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val status = connection.responseCode
            if (status !in 200..299) {
                throw ApiRejectedException(status)
            }
            val responseText = connection.inputStream.bufferedReader().use { it.readText() }
            return if (responseText.isBlank()) JSONObject() else JSONObject(responseText)
        } finally {
            connection.disconnect()
        }
    }

    private fun validateOrigin(rawOrigin: String): String {
        val uri = try {
            URI(rawOrigin.trim())
        } catch (_: Exception) {
            throw IllegalArgumentException("Enter a valid ChargePilot API origin.")
        }
        val host = uri.host?.lowercase()
        if (
            host.isNullOrBlank() ||
            uri.scheme != "https" ||
            (uri.path.isNotEmpty() && uri.path != "/") ||
            uri.query != null ||
            uri.fragment != null
        ) {
            throw IllegalArgumentException("Use an HTTPS API origin without a path, query, or fragment.")
        }
        return uri.toString().trimEnd('/')
    }

}

class TelemetryWorker(context: Context, parameters: WorkerParameters) : Worker(context, parameters) {
    private val store = AgentStore(context)

    override fun doWork(): Result {
        val configuration = store.configuration()
            ?: return fail("Enroll this device before sending telemetry.")
        return try {
            val reading = BatteryReader.read(applicationContext)
            AgentApi.sendTelemetry(applicationContext, configuration, store.credential(), reading)
            store.recordSuccess(Instant.now().toString())
            Result.success()
        } catch (error: ApiRejectedException) {
            val message = "ChargePilot rejected the report (HTTP ${error.statusCode})."
            store.recordError(message)
            if (error.statusCode >= 500 && runAttemptCount < MAX_RETRIES) Result.retry() else Result.failure()
        } catch (error: BatteryUnavailableException) {
            fail("A usable battery reading is unavailable; no sample was sent.")
        } catch (error: IOException) {
            val message = "The report could not reach ChargePilot. Check the connection and try again."
            store.recordError(message)
            if (runAttemptCount < MAX_RETRIES) Result.retry() else Result.failure()
        } catch (_: Exception) {
            fail("The report could not be prepared. Check enrollment and device storage.")
        }
    }

    private fun fail(message: String): Result {
        store.recordError(message)
        return Result.failure()
    }

    companion object {
        private const val MAX_RETRIES = 3
        private const val PERIODIC_REPORT = "chargepilot-periodic-telemetry"

        fun schedulePeriodic(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()
            val request = PeriodicWorkRequestBuilder<TelemetryWorker>(15, TimeUnit.MINUTES)
                .setConstraints(constraints)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                PERIODIC_REPORT,
                ExistingPeriodicWorkPolicy.UPDATE,
                request,
            )
        }

        fun sendNow(context: Context): UUID {
            val request = OneTimeWorkRequestBuilder<TelemetryWorker>()
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build(),
                )
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()
            WorkManager.getInstance(context).enqueue(request)
            return request.id
        }
    }
}

class ApiRejectedException(val statusCode: Int) : IOException()
class BatteryUnavailableException : IOException()
